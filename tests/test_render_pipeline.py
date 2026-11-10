"""Pipeline output contracts, room enclosures, fixtures, cameras and exterior views."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from ffxiv_furniture.interiors import BASE
from ffxiv_furniture.rendering.pipeline import (
    apply_patch,
    quaternion_matrix,
    run_pipeline,
)
from tests.support import ROOT, SIZES, needs_meshes, needs_seed, read_layout, seed

OUTPUT_CAMERA = dict(name="entry", position=[0, 5, 1.65], target=[0, -4, 1.65], fov=85)
SWEEP_SIZE = (96, 64)
SWEEP_CAMERAS = [dict(name="o", position=[0, -20, 12], target=[0, 0, 0], fov=60)]


def layout_for(size):
    """Use the apartment fixture template with the requested house-size envelope."""
    layout = seed("Apartment")
    layout["houseSize"] = size
    return layout


def run_scene(layout, cameras=SWEEP_CAMERAS, **kwargs):
    """Render a small real scene and return its manifest after temporary cleanup."""
    with tempfile.TemporaryDirectory() as directory:
        return run_pipeline(
            layout,
            Path(directory),
            size=SWEEP_SIZE,
            cameras=cameras,
            mirror_view=False,
            **kwargs,
        )


def instance_ids(manifest):
    return [obj.get("instance_id") for obj in manifest["objects"].values()]


class LayoutPatchTests(unittest.TestCase):

    def layout(self):
        return {
            "houseSize": "Medium",
            "interiorScale": 100,
            "interiorFurniture": [
                {
                    "itemId": 1,
                    "name": "fixture",
                    "transform": {
                        "location": [400, -300, 0],
                        "rotation": [0, 0, 0, 1],
                        "scale": [1, 1, 1],
                    },
                }
            ],
            "unknown": "keep",
        }

    def test_free_yaw_patch_preserves_source(self):
        layout = self.layout()
        before = deepcopy(layout)
        result = apply_patch(
            layout,
            {
                "base_layout_sha256": "a",
                "changes": [
                    {"instance_id": "furniture-0001", "yaw_delta_degrees": 17.5}
                ],
            },
            "a",
        )
        self.assertEqual(layout, before)
        self.assertEqual(result["unknown"], "keep")
        q = result["interiorFurniture"][0]["transform"]["rotation"]
        m = quaternion_matrix(q)
        self.assertAlmostEqual(np.linalg.det(m), 1)
        self.assertGreater(abs(q[2]), 0)

    def test_bad_patch_bounds_and_identity_rejected(self):
        for patch in [
            {"base_layout_sha256": "wrong", "changes": []},
            {
                "base_layout_sha256": "a",
                "changes": [{"instance_id": "furniture-0001", "item_id": 999}],
            },
            {
                "base_layout_sha256": "a",
                "changes": [
                    {"instance_id": "furniture-0001", "delta_translation_m": [3, 0, 0]}
                ],
            },
            {
                "base_layout_sha256": "a",
                "changes": [
                    {"instance_id": "furniture-0001", "yaw_delta_degrees": float("nan")}
                ],
            },
        ]:
            with self.assertRaises(ValueError):
                apply_patch(self.layout(), patch, "a")


@unittest.skipUnless(
    (ROOT / "outputs/geometry/fill-result.json").exists(), "Local assets absent"
)
class PipelineArtifactTests(unittest.TestCase):

    def test_actual_layout_to_artifacts(self):
        p = ROOT / "outputs/opus-one-floor/Opus_GroundFloor.json"
        if not p.exists():
            self.skipTest("Sample layout absent")
        layout = json.loads(p.read_bytes())
        item = next(i for i in layout["interiorFurniture"] if i["itemId"] == 28639)
        layout["interiorFurniture"] = [item]
        item["transform"]["location"] = [450, -300, 2.0934982299804688]
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.json"
            source.write_text(json.dumps(layout), encoding="utf-8")
            out = Path(temp) / "out"
            db = ROOT / "data/furniture-test.sqlite3"
            before_hash = hashlib.sha256(db.read_bytes()).hexdigest()
            m = run_pipeline(
                source,
                out,
                cameras=[{"position": [0, 7, 1.65], "target": [4.5, -3, 0.7]}],
                size=(160, 120),
                artifacts=True,
            )
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before_hash)
            self.assertTrue(Path(m["views"][0]["image"]).exists())
            self.assertNotIn("ids", m["views"][0])
            self.assertNotIn("labeled", m["views"][0])
            self.assertFalse(list(out.glob("*-ids.png")))
            self.assertFalse(list(out.glob("*-labeled.png")))
            self.assertEqual(m["geometry_assets"], 1)
            self.assertEqual(m["textured_slots"], 1)
            self.assertTrue((out / "review-request.json").exists())
            self.assertEqual(
                json.loads((out / "layout.json").read_bytes())["interiorFurniture"][0][
                    "name"
                ],
                "Leather Sofa",
            )
            with self.assertRaises(ValueError):
                run_pipeline(source, out)


@unittest.skipUnless(
    (ROOT / "data/furniture.sqlite3").exists()
    and (ROOT / "outputs/render-pipeline/multi-size/Large.json").exists(),
    "real DB / demo layouts absent",
)
class DbGeometryRenderTests(unittest.TestCase):

    def test_non_57_furniture_in_large_house_from_db_geometry(self):
        known = {
            r["item_id"]
            for r in json.loads(
                (ROOT / "outputs/geometry/fill-result.json").read_text()
            )["records"]
        }
        source = ROOT / "outputs/render-pipeline/multi-size/Large.json"
        layout = read_layout(source)
        self.assertTrue(
            {i["itemId"] for i in layout["interiorFurniture"]} - known,
            "demo must use furniture outside the original 57",
        )
        with tempfile.TemporaryDirectory() as tmp:
            m = run_pipeline(
                source,
                Path(tmp) / "run",
                db_path=ROOT / "data/furniture.sqlite3",
                size=(160, 120),
            )
            self.assertEqual(len(m["views"]), 4)
            self.assertGreater(m["material_slots"], 0)
            self.assertTrue(any("auto-framed" in w for w in m["warnings"]))

    def test_unknown_house_size_refused(self):
        layout = read_layout(ROOT / "outputs/render-pipeline/multi-size/Large.json")
        layout["houseSize"] = "Gigantic"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "l.json"
            p.write_text(json.dumps(layout), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_pipeline(
                    p, Path(tmp) / "run", db_path=ROOT / "data/furniture.sqlite3"
                )


class MinimalRenderOutputTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.layout = seed("Apartment", furniture=True)
        self.layout.update(houseSize="Small", interiorFurniture=[])
        self.source.write_text(json.dumps(self.layout), encoding="utf-8")

    def run_scene(self, out, **kwargs):
        return run_pipeline(
            self.source,
            out,
            room_context=True,
            db_path=ROOT / "data/furniture.sqlite3",
            cameras=[OUTPUT_CAMERA],
            size=(96, 64),
            mirror_view=False,
            **kwargs,
        )

    def test_default_writes_only_requested_jpeg(self):
        out = self.root / "renders"
        m = self.run_scene(out)
        self.assertEqual({p.name for p in out.iterdir()}, {"view-01.jpg"})
        self.assertIsNone(m["rendered_layout"])
        self.assertTrue(m["views"][0]["visible_object_pixels"])
        with Image.open(m["views"][0]["image"]) as im:
            self.assertEqual(im.format, "JPEG")

    def test_different_prefixes_share_one_flat_directory(self):
        out = self.root / "renders"
        a = self.run_scene(out, image_prefix="r0-entry-abc")
        b = self.run_scene(out, image_prefix="r0-north-def")
        self.assertEqual(
            {p.name for p in out.iterdir()},
            {"r0-entry-abc-01.jpg", "r0-north-def-01.jpg"},
        )
        self.assertNotEqual(a["views"][0]["image"], b["views"][0]["image"])
        with self.assertRaises(ValueError):
            self.run_scene(out, image_prefix="r0-entry-abc")

    def test_explicit_artifacts_preserve_diagnostics_and_pixels(self):
        out = self.root / "renders"
        a = self.run_scene(out, image_prefix="plain")
        b = self.run_scene(out, image_prefix="debug", artifacts=True)
        self.assertEqual(
            {p.name for p in out.iterdir()},
            {
                "plain-01.jpg",
                "debug-01.jpg",
                "debug-layout.json",
                "debug-manifest.json",
                "debug-review-request.json",
            },
        )
        self.assertTrue(
            np.array_equal(
                np.asarray(Image.open(a["views"][0]["image"])),
                np.asarray(Image.open(b["views"][0]["image"])),
            )
        )
        self.assertEqual(
            json.loads((out / "debug-manifest.json").read_text(encoding="utf-8"))[
                "rendered_layout"
            ],
            b["rendered_layout"],
        )

    def test_in_memory_layout_needs_no_source_file(self):
        before = deepcopy(self.layout)
        out = self.root / "renders"
        m = run_pipeline(
            self.layout,
            out,
            room_context=True,
            db_path=ROOT / "data/furniture.sqlite3",
            cameras=[OUTPUT_CAMERA],
            size=(96, 64),
        )
        self.assertEqual(self.layout, before)
        self.assertIsNone(m["input_layout"])
        self.assertEqual({p.name for p in out.iterdir()}, {"view-01.jpg"})

    def test_unsafe_prefix_is_refused_before_output(self):
        out = self.root / "renders"
        for prefix in ("../escape", "a/b", "a\\b", "", "dot.name"):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                self.run_scene(out, image_prefix=prefix)
        self.assertFalse(out.exists())

    def test_cli_explicit_prefix_defaults_to_jpeg_only(self):
        out = self.root / "renders"
        cams = self.root / "cameras.json"
        cams.write_text(json.dumps([OUTPUT_CAMERA]), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ffxiv_furniture.rendering",
                "--layout",
                str(self.source),
                "--output-dir",
                str(out),
                "--cameras",
                str(cams),
                "--room-context",
                "--image-prefix",
                "entry",
                "--width",
                "96",
                "--height",
                "64",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({p.name for p in out.iterdir()}, {"entry-01.jpg"})


class MainEntranceRenderTests(unittest.TestCase):

    def _run(self, size, selected_door=None):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"{size}.json"
            layout = layout_for(size)
            if selected_door:
                layout["exteriorFixture"] = [dict(type="Door", name=selected_door)]
            src.write_text(json.dumps(layout), encoding="utf-8")
            return run_pipeline(
                src,
                Path(tmp) / f"run-{size}",
                db_path=ROOT / "data/furniture-test.sqlite3",
                # Keep doorway pixels below the fixed 40-row diagnostic banner.
                room_context=True,
                size=(192, 128),
                mirror_view=False,
                cameras=[
                    dict(name="entry", position=[0, 4, 2.2], target=[0, 8, 1.2], fov=80)
                ],
            )

    def test_cutaway_plan_views_keep_main_door(self):
        """User-reported: overview/top cutaways dropped the door with the walls, so plan views hid the entrance
        and the arrival area was misjudged. The door is an entrance marker, not wall: keep it in cutaways.
        """
        cams = [
            dict(
                name="overview",
                position=[12, -12, 16],
                target=[1, 0, 0],
                fov=60,
                cutaway=True,
            ),
            dict(
                name="top",
                position=[0.5, 0, 38],
                target=[0, 0, 0],
                fov=34,
                cutaway=True,
            ),
        ]
        for size, door in (
            ("Small", None),
            ("Small", "Riviera Wooden Door"),
            ("Apartment", None),
        ):
            with self.subTest(
                size=size, door=door
            ), tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / f"{size}.json"
                layout = layout_for(size)
                if door:
                    layout["exteriorFixture"] = [dict(type="Door", name=door)]
                src.write_text(json.dumps(layout), encoding="utf-8")
                m = run_pipeline(
                    src,
                    Path(tmp) / "run",
                    db_path=ROOT / "data/furniture-test.sqlite3",
                    room_context=True,
                    size=(192, 128),
                    mirror_view=False,
                    cameras=cams,
                )
                did = str(m["objects"]["main-door"]["render_id"])
                for view in m["views"]:
                    self.assertGreater(
                        view["visible_object_pixels"].get(did, 0),
                        0,
                        f"{view.get('camera', view)}: cutaway must still show the entrance door",
                    )

    def test_small_stairwell_ceiling_is_cut_in_plan_views(self):
        # user-visible: the Small stairwell ceiling drew as a grey slab over the landing in top views
        from collections import defaultdict
        from ffxiv_furniture.rendering import pipeline

        roles = defaultdict(set)
        original = pipeline.render

        def audited(meshes, *a, **k):
            for mesh in meshes:
                roles[mesh["id"]].add(mesh["role"])
            return original(meshes, *a, **k)

        with patch.object(pipeline, "render", audited):
            m = self._run("Small")
        ceil = [
            k
            for k, v in m["objects"].items()
            if k.isdigit() and v.get("instance_id") == "stairceiling"
        ]
        self.assertEqual(len(ceil), 1)
        self.assertEqual(roles[int(ceil[0])], {"enclosure"})
        stair = [
            k
            for k, v in m["objects"].items()
            if k.isdigit() and v.get("instance_id") == "stair-down"
        ]
        self.assertEqual(roles[int(stair[0])], {"stair"})

    def test_every_house_size_renders_main_door(self):
        NORTH_WALL_Y = {"Small": 6.0, "Medium": 8.0, "Large": 12.0, "Apartment": 8.0}
        for size in SIZES:
            with self.subTest(size=size):
                m = self._run(size)
                self.assertIn(
                    "main-door",
                    m["objects"],
                    "main entrance door must be part of the room context",
                )
                door = m["objects"]["main-door"]
                self.assertFalse(door["app_verified"])
                self.assertIn(
                    "MakePlace/Content/HouseAssets/MainDoor/",
                    str(door["mesh_source"]).replace("\\", "/"),
                    "door geometry must come from a converted native MainDoor mesh, never a synthetic box",
                )
                self.assertTrue(str(door["mesh_source"]).lower().endswith(".uexp"))
                for v in m["views"]:
                    self.assertFalse(v.get("cache_hit"))
                hits = [w for w in m["warnings"] if "main entrance door" in w.lower()]
                self.assertTrue(
                    hits, "door placement assumption must be disclosed as a warning"
                )
                world = np.asarray(m["objects"]["main-door"]["world_bounds_m"], float)
                (x0, y0, z0), (x1, y1, z1) = world
                wall = NORTH_WALL_Y[size]
                self.assertGreater(
                    y0,
                    wall - 1.5,
                    f"{size}: door must stand against the north wall (y={wall})",
                )
                self.assertLessEqual(
                    y1,
                    wall + 0.05,
                    f"{size}: door must not poke through the north wall",
                )
                self.assertLess(
                    abs((x0 + x1) / 2),
                    0.25,
                    f"{size}: door must sit on the documented centre entrance",
                )
                self.assertGreaterEqual(
                    z0, -0.05, f"{size}: door must not sink below the floor"
                )
                self.assertGreater(
                    z1, 1.8, f"{size}: a house entrance is at least ~2 m tall"
                )

    def test_structural_ids_separate_door_from_railings(self):
        from collections import defaultdict
        from ffxiv_furniture.rendering import pipeline

        for size in SIZES:
            with self.subTest(size=size):
                roles = defaultdict(set)
                original_render = pipeline.render

                def audited_render(meshes, *args, **kwargs):
                    for mesh in meshes:
                        roles[mesh["id"]].add(mesh["role"])
                    return original_render(meshes, *args, **kwargs)

                with patch.object(pipeline, "render", audited_render):
                    manifest = self._run(size)
                collisions = {
                    key: sorted(value) for key, value in roles.items() if len(value) > 1
                }
                self.assertEqual(
                    collisions, {}, "different structural objects must not share an ID"
                )
                door = manifest["objects"]["main-door"]
                self.assertIn("render_id", door)
                door_id = door["render_id"]
                self.assertEqual(manifest["objects"][str(door_id)], door)
                self.assertEqual(roles[door_id], {"door"})
                self.assertGreater(
                    manifest["views"][0]["visible_object_pixels"].get(str(door_id), 0),
                    0,
                    "door pixels must resolve to door metadata, not a railing",
                )
                for render_id in roles:
                    self.assertIn(str(render_id), manifest["objects"])

    def test_non_small_rooms_render_the_selected_door(self):
        """Changing Door must change the native mesh, not only the exported fixture."""
        north_wall = {"Medium": 8.0, "Large": 12.0, "Apartment": 8.0}
        for size, wall_y in north_wall.items():
            with self.subTest(size=size):
                manifest = self._run(size, "Riviera Wooden Door")
                door = manifest["objects"]["main-door"]
                self.assertIn("RivieraWoodenDoor", door["mesh_source"])
                self.assertEqual(door.get("name"), "Riviera Wooden Door")
                doors = [
                    (k, v)
                    for k, v in manifest["objects"].items()
                    if k.isdigit() and v["instance_id"] in ("main-door", "native-door")
                ]
                self.assertEqual(
                    len(doors), 1, "do not draw both selected and fallback doors"
                )
                self.assertEqual(doors[0][1], door)
                self.assertEqual(str(door["render_id"]), doors[0][0])
                self.assertGreater(
                    manifest["views"][0]["visible_object_pixels"].get(doors[0][0], 0), 0
                )
                lo, hi = np.asarray(door["world_bounds_m"])
                self.assertAlmostEqual(hi[1], wall_y, places=2)
                self.assertAlmostEqual(lo[2], 0.0, places=2)
                self.assertAlmostEqual((lo[0] + hi[0]) / 2, 0.0, places=2)
                self.assertFalse(door["app_verified"])

    def test_small_selected_door_has_no_duplicate_fallback(self):
        manifest = self._run("Small", "Riviera Wooden Door")
        doors = [
            (k, v)
            for k, v in manifest["objects"].items()
            if k.isdigit() and v["instance_id"] in ("main-door", "native-door")
        ]
        self.assertEqual(
            len(doors), 1, "selected and fallback doors must not both render"
        )
        key, door = doors[0]
        self.assertEqual(door["name"], "Riviera Wooden Door")
        self.assertEqual(manifest["objects"]["main-door"], door)
        self.assertEqual(str(door["render_id"]), key)
        self.assertGreater(manifest["views"][0]["visible_object_pixels"].get(key, 0), 0)
        self.assertIn("native_material_diagnostics", manifest)
        diagnostics = manifest["native_material_diagnostics"]
        self.assertIn("native decode only", diagnostics["scope"])
        for kind in ("furniture", "structure", "fixtures"):
            group = diagnostics[kind]
            self.assertEqual(group["decoded_entries"], len(group["coverage"]))
            self.assertEqual(
                group["material_slots"],
                sum(a["material_slots"] for a in group["coverage"]),
            )
            self.assertEqual(
                group["textured_slots"],
                sum(a["textured_slots"] for a in group["coverage"]),
            )
            self.assertEqual(
                group["untextured_slots"],
                group["material_slots"] - group["textured_slots"],
            )
            for row in group["coverage"]:
                self.assertIn("source", row)
                self.assertIn("source_sha256", row)
                self.assertIn("notes", row)
                self.assertTrue(all("warning" in m for m in row["materials"]))
        fixtures = diagnostics["fixtures"]["coverage"]
        self.assertTrue(any("MainDoor" in Path(a["source"]).parts for a in fixtures))
        self.assertTrue(
            any("CeilingLight" in Path(a["source"]).parts for a in fixtures)
        )
        self.assertGreater(diagnostics["structure"]["decoded_entries"], 0)
        self.assertEqual(
            manifest["asset_coverage"], diagnostics["furniture"]["coverage"]
        )

    def test_small_missing_or_absent_selected_door_uses_fallback(self):
        manifest = self._run(
            "Small", "Missing Door Asset For Regression"
        )  # selected door asset cannot be loaded
        doors = [
            (k, v)
            for k, v in manifest["objects"].items()
            if k.isdigit() and v["instance_id"] in ("main-door", "native-door")
        ]
        self.assertEqual(len(doors), 1)
        key, door = doors[0]
        self.assertEqual(door["instance_id"], "main-door")
        self.assertTrue(any("Native Door not drawn" in w for w in manifest["warnings"]))
        self.assertGreater(manifest["views"][0]["visible_object_pixels"].get(key, 0), 0)
        layout = layout_for("Small")
        layout["exteriorFixture"] = []  # no door fixture at all
        with patch(__name__ + ".layout_for", return_value=layout):
            manifest = self._run("Small")
        doors = [
            v
            for k, v in manifest["objects"].items()
            if k.isdigit() and v["instance_id"] in ("main-door", "native-door")
        ]
        self.assertEqual([d["instance_id"] for d in doors], ["main-door"])

    def test_no_room_context_keeps_scene_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "apt.json"
            lay = layout_for("Apartment")
            template = seed("Apartment", furniture=True)
            item = (
                dict(template["interiorFurniture"][0])
                if template.get("interiorFurniture")
                else None
            )
            if item is None:
                self.skipTest("seed has no furniture sample")
            lay["interiorFurniture"] = [item]
            src.write_text(json.dumps(lay), encoding="utf-8")
            m = run_pipeline(
                src,
                Path(tmp) / "run-nc",
                db_path=ROOT / "data/furniture-test.sqlite3",
                size=(96, 64),
                mirror_view=False,
                cameras=[
                    dict(name="top", position=[0, 0, 40], target=[0, 0, 0], fov=32)
                ],
            )
            self.assertNotIn("main-door", m["objects"])


@unittest.skipUnless(
    (BASE / "Mist/Small/BasementFrame.uexp").exists(),
    "native Small interiors not extracted",
)
class BasementVoidOverlayTests(unittest.TestCase):

    def _run(self, style, cutaway):
        lay = seed("Small")
        for fx in lay["interiorFixture"]:
            if fx["type"] == "District":
                fx["name"] = style
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "l.json"
            src.write_text(json.dumps(lay), encoding="utf-8")
            cam = dict(
                name="bs_top",
                position=[2.5, 4, 30],
                target=[2, 4, -7],
                fov=40,
                basement=True,
                hide_above_z=-0.6,
                cutaway=cutaway,
            )
            return run_pipeline(
                src,
                Path(tmp) / "r",
                db_path=ROOT / "data/furniture-test.sqlite3",
                room_context=True,
                basement_context=True,
                size=(160, 160),
                mirror_view=False,
                cameras=[cam],
            )

    def test_mist_plan_marks_walled_off_floor(self):
        m = self._run("Mist", True)
        void = [
            k
            for k, v in m["objects"].items()
            if k.isdigit() and v.get("instance_id") == "basement-walled-off"
        ]
        self.assertEqual(len(void), 1)
        self.assertGreater(m["objects"][void[0]]["area_m2"], 40)
        self.assertGreater(m["views"][0]["visible_object_pixels"].get(void[0], 0), 0)

    def test_open_style_and_eye_views_unchanged(self):
        m = self._run("Minimalist", True)
        void = [
            k
            for k, v in m["objects"].items()
            if k.isdigit() and v.get("instance_id") == "basement-walled-off"
        ]
        self.assertTrue(not void or m["objects"][void[0]]["area_m2"] < 5)
        m = self._run("Mist", False)
        void = [
            k
            for k, v in m["objects"].items()
            if k.isdigit() and v.get("instance_id") == "basement-walled-off"
        ]
        self.assertTrue(
            not void or m["views"][0]["visible_object_pixels"].get(void[0], 0) == 0,
            "overlay is for cutaway plans only",
        )


@needs_meshes
@needs_seed("Medium", "Large")
class HouseSizeRenderTests(unittest.TestCase):

    def render(self, size, cameras, **kw):
        lay = seed(size, furniture=True)
        with tempfile.TemporaryDirectory() as t:
            return run_pipeline(
                lay,
                Path(t),
                room_context=True,
                size=(160, 120),
                cameras=cameras,
                mirror_view=False,
                **kw,
            )

    def test_medium_basement_context_renders_frame_floor_and_down_stair(self):
        cam = dict(
            name="bs",
            position=[14, -10, 6],
            target=[0, 0, -7],
            fov=60,
            cutaway=True,
            hide_above_z=-0.6,
        )
        m = self.render("Medium", [cam], basement_context=True)
        ids = {o.get("instance_id") for o in m["objects"].values()}
        self.assertTrue(
            {"bs-room-frame", "bs-pillars", "bs-floor-synthetic"} <= ids, ids
        )
        self.assertGreater(sum(m["views"][0]["visible_object_pixels"].values()), 5000)

    def test_large_renders_all_three_floors_stairs_and_door(self):
        cams = [
            dict(name="g", position=[0, 11, 2.0], target=[0, -12, 1.2], fov=85),
            dict(
                name="u",
                position=[0, 10, 9.0],
                target=[0, -12, 8.2],
                fov=85,
                upper=True,
            ),
            dict(
                name="b",
                position=[16, 10, -5.0],
                target=[-10, -8, -6.0],
                fov=85,
                basement=True,
            ),
        ]
        m = self.render("Large", cams, basement_context=True, upper_context=True)
        ids = {o.get("instance_id") for o in m["objects"].values()}
        for need in ("room-frame", "up-room-frame", "bs-room-frame"):
            self.assertIn(need, ids)
        self.assertIn("main-door", m["objects"])
        actors = {o.get("source_actor") for o in m["objects"].values()}
        self.assertTrue({"MainStairs", "BasementStairs"} <= actors, actors)
        for v in m["views"]:
            self.assertGreater(
                sum(v["visible_object_pixels"].values()), 5000, v.get("camera")
            )


@needs_meshes
@needs_seed("Medium")
class WindowRenderTests(unittest.TestCase):

    def test_medium_and_large_draw_their_decoded_windows(self):
        for size, n in (("Medium", 8), ("Large", 14)):
            lay = seed(size, furniture=True)
            with tempfile.TemporaryDirectory() as t:
                m = run_pipeline(
                    lay,
                    Path(t),
                    room_context=True,
                    upper_context=True,
                    size=(96, 64),
                    mirror_view=False,
                    cameras=[
                        dict(name="o", position=[0, -30, 30], target=[0, 0, 0], fov=60)
                    ],
                )
            wins = [
                o
                for o in m["objects"].values()
                if str(o.get("instance_id", "")).startswith("native-window")
            ]
            self.assertEqual(len(wins), n, (size, len(wins)))


class RendererVersionTests(unittest.TestCase):

    def test_helper_code_changes_invalidate_image_cache(self):
        import os
        from ffxiv_furniture.deco import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "ffxiv_furniture/rendering"
            d.mkdir(parents=True)
            for name in (
                "pipeline",
                "raster",
                "raster_gpu",
                "house_materials",
                "assets",
                "native",
                "projection",
                "resources",
            ):
                (d / (name + ".py")).write_text("# fixture")
            for name in (
                "interiors.py",
                "geometry_mesh.py",
                "house_profiles.py",
                "deco/server.py",
                "deco/core.py",
                "deco/exterior.py",
                "exteriors.py",
                "rendering/exterior.py",
            ):
                p = root / "ffxiv_furniture" / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("# fixture")
            for size in ("Small", "Medium", "Large"):
                for ext in (".umap", ".uexp"):
                    p = (
                        root
                        / "data/house-legacy/MakePlace/Content/Maps"
                        / ("XIV" + size + "Exterior" + ext)
                    )
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("# fixture")
            with patch.object(server, "ROOT", root):
                before = server._renderer_version()
                p = d / "projection.py"
                st = p.stat()
                os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000000))
                after = server._renderer_version()
            self.assertNotEqual(
                before,
                after,
                "new render helpers must invalidate completed image caches",
            )


class ExteriorLightingRenderTests(unittest.TestCase):

    def test_exterior_accepts_true_and_dict_moods(self):
        layout = seed("Medium", furniture=True)
        for mood in (
            True,
            "warm",
            dict(lo=(0.1, 0.1, 0.1), hi=(0.2, 0.2, 0.2), exposure=1.2, scale=1.0),
        ):
            m = run_scene(layout, cameras=None, scope="exterior", lighting=mood)
            self.assertTrue(m["views"][0]["camera"]["lighting"] is not None, mood)


class CeilingLightTests(unittest.TestCase):

    def test_point_lights_follow_spot_xy(self):
        m = run_scene(seed("Large", furniture=True), room_context=True, lighting="dusk")
        lights = m["views"][0]["camera"]["lighting"]["lights"]
        xs = sorted(round(l["pos"][0]) for l in lights)
        self.assertIn(14, xs)
        self.assertIn(-14, xs)
        for l in lights:
            if abs(l["pos"][0]) > 13:
                self.assertAlmostEqual(l["pos"][2], 6.5 - 1.2, places=3)

    def test_no_ceiling_light_for_absent_levels(self):
        for size, kw in (
            ("Small", dict(upper_context=True)),
            ("Apartment", dict(upper_context=True, basement_context=True)),
        ):
            m = run_scene(seed(size, furniture=True), room_context=True, **kw)
            names = instance_ids(m)
            self.assertFalse(
                [n for n in names if n and n.startswith("ceiling-light-upper")],
                (size, names),
            )
            if size == "Apartment":
                self.assertFalse(
                    [n for n in names if n and n.startswith("ceiling-light-basement")],
                    names,
                )
            self.assertTrue(
                any("no upper" in w.lower() for w in m["warnings"]), m["warnings"]
            )

    def test_structure_ids_are_size_independent(self):
        for size in ("Medium", "Large"):
            names = set(
                instance_ids(run_scene(seed(size, furniture=True), room_context=True))
            )
            self.assertTrue(
                {"stair-up", "stair-down", "railing-ground", "railing-upper"} <= names,
                (size, sorted(n for n in names if n)),
            )
        lights = [
            n
            for n in instance_ids(
                run_scene(
                    seed("Large", furniture=True), room_context=True, upper_context=True
                )
            )
            if n and n.startswith("ceiling-light")
        ]
        self.assertTrue(len(lights) >= 5, lights)
        self.assertEqual(len(set(lights)), len(lights))
        self.assertTrue(
            all(
                re.fullmatch(r"ceiling-light-(ground|upper|basement)-\d+", n)
                for n in lights
            ),
            lights,
        )


class StairSectionTests(unittest.TestCase):

    def test_cut_stairs_default_is_relative_to_plan_level(self):
        cams = [
            dict(
                name="up",
                position=[0, 0.01, 40],
                target=[0, 0, 7],
                fov=40,
                cutaway=True,
                hide_below_z=6.9,
            ),
            dict(
                name="gr",
                position=[0, 0.01, 40],
                target=[0, 0, 0],
                fov=40,
                cutaway=True,
            ),
            dict(
                name="bs",
                position=[0, 0.01, 40],
                target=[0, 0, -7],
                fov=40,
                cutaway=True,
                hide_above_z=-0.6,
            ),
            dict(
                name="explicit",
                position=[0, 0.01, 40],
                target=[0, 0, 0],
                fov=40,
                cutaway=True,
                cut_stairs_z=1.5,
            ),
        ]
        m = run_scene(
            seed("Medium", furniture=True),
            cameras=cams,
            room_context=True,
            upper_context=True,
            basement_context=True,
        )
        cut = {v["camera"]["name"]: v["camera"].get("cut_stairs_z") for v in m["views"]}
        self.assertAlmostEqual(cut["up"], 10.0)
        self.assertAlmostEqual(cut["gr"], 3.0)
        self.assertAlmostEqual(cut["bs"], -4.0)
        self.assertAlmostEqual(cut["explicit"], 1.5)


class DefaultCameraTests(unittest.TestCase):

    def test_entry_camera_is_inside_the_room(self):
        for size in ("Small", "Large", "Apartment"):
            m = run_scene(seed(size, furniture=True), cameras=None, room_context=True)
            entry = next(v for v in m["views"] if v["camera"]["name"] == "entry")
            pixels = entry["visible_object_pixels"]
            total = sum(pixels.values())
            walls = sum(
                n
                for k, n in pixels.items()
                if m["objects"][k].get("instance_id")
                in ("walls", "room-frame", "ceiling")
            )
            floor = sum(
                n
                for k, n in pixels.items()
                if m["objects"][k].get("instance_id") in ("floor", "floor-synthetic")
            )
            self.assertLess(walls / total, 0.9, (size, pixels))
            self.assertGreater(floor, 0, size)


class CameraValidationTests(unittest.TestCase):

    def test_bad_cameras_raise_valueerror_before_any_render(self):
        layout = seed("Medium", furniture=True)
        for bad in (
            dict(name="x", position=[0, 0, 1], target=[1, 0, 1]),
            [],
            [SWEEP_CAMERAS[0]] * 9,
            [1],
            "x",
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run_scene(layout, cameras=bad, room_context=True)
        with self.assertRaises(ValueError):
            run_scene(
                seed("Medium", furniture=True), cameras=dict(name="x"), scope="exterior"
            )


class FallbackTests(unittest.TestCase):

    def test_missing_floor_wall_fixture_falls_back_with_warning(self):
        layout = seed("Medium", furniture=True)
        layout["interiorFixture"] = [
            f
            for f in layout["interiorFixture"]
            if not (f["type"] == "Wall" and f["level"] == "Ground Floor")
        ]
        m = run_scene(layout, room_context=True, rough_room_finish=True)
        self.assertTrue(
            any(
                "finish" in w.lower() and "unavailable" in w.lower()
                for w in m["warnings"]
            ),
            m["warnings"],
        )

    def test_substituted_levels_are_warned_and_marked(self):
        layout = seed("Medium", furniture=True)
        layout["interiorFixture"] = [
            f
            for f in layout["interiorFixture"]
            if not (
                f["type"] in ("Floor", "Wall")
                and f["level"] in ("Basement", "Upper Floor")
            )
        ]
        m = run_scene(
            layout,
            room_context=True,
            rough_room_finish=True,
            basement_context=True,
            upper_context=True,
        )
        joined = " ".join(m["warnings"])
        self.assertIn("Basement", joined)
        self.assertIn("Upper Floor", joined)
        self.assertIn("substitut", joined)
        marked = [
            o
            for o in m["objects"].values()
            if str(o.get("instance_id", "")).startswith(("bs-", "up-"))
            and "texture" in o
        ]
        self.assertTrue(marked)
        self.assertTrue(
            all(
                o["texture"].get("substituted_from") == "Ground Floor"
                for o in marked
                if o["instance_id"] in ("bs-floor", "bs-walls", "up-floor", "up-walls")
            )
        )
        synth = [
            o
            for o in m["objects"].values()
            if o.get("instance_id") == "bs-floor-synthetic"
        ]  # Medium basement floor is synthesised
        self.assertEqual(len(synth), 1)
        self.assertIn("texture", synth[0])

    def test_missing_window_fixture_warns(self):
        layout = seed("Small", furniture=True)
        layout["exteriorFixture"] = [
            f for f in layout["exteriorFixture"] if f["type"] != "Window"
        ]
        m = run_scene(layout, room_context=True)
        self.assertTrue(
            any(
                "window" in w.lower() and "no window" in w.lower()
                for w in m["warnings"]
            ),
            m["warnings"],
        )

    def test_missing_item_colors_table_is_reported(self):
        from ffxiv_furniture.rendering.common import load_fallback_colours

        db = sqlite3.connect(":memory:")
        warnings = []
        self.assertEqual(load_fallback_colours(db, warnings), {})
        self.assertTrue(any("item_colors" in w for w in warnings))

    def test_decode_failures_aggregate_into_one_warning(self):
        from ffxiv_furniture.rendering.common import coverage_warnings

        coverage = [
            dict(
                item_id=1,
                notes=["No unique cross-validated section layout"],
                material_slots=2,
                textured_slots=1,
                materials=[
                    dict(warning="No explicit Base texture parameter"),
                    dict(warning=None),
                ],
            ),
            dict(
                item_id=2,
                notes=[],
                material_slots=1,
                textured_slots=1,
                materials=[dict(warning=None)],
            ),
        ]
        out = coverage_warnings(coverage)
        self.assertEqual(len(out), 1)
        self.assertIn("1 of 3", out[0])
        self.assertIn("No explicit Base texture parameter", out[0])
        self.assertIn("section layout", out[0])
        self.assertEqual(coverage_warnings([coverage[1]]), [])


class ManifestTests(unittest.TestCase):

    def test_pixel_counts_are_not_called_triangle_updates(self):
        m = run_scene(seed("Medium", furniture=True), room_context=True)
        for v in m["views"]:
            self.assertNotIn("visible_triangle_updates", v)
            self.assertNotIn("textured_triangle_updates", v)

    def test_exterior_manifest_matches_interior_keys_and_flags_default_dye(self):
        interior = run_scene(seed("Medium", furniture=True), room_context=True)
        exterior = run_scene(
            seed("Medium", furniture=True),
            cameras=None,
            scope="exterior",
            dye_mode="default",
        )
        self.assertFalse(
            set(interior) - set(exterior), sorted(set(interior) - set(exterior))
        )
        self.assertTrue(
            exterior["mirror_view"] is False and exterior["display_gamma"] == 0.7
        )
        self.assertEqual(exterior["dye_mode"], "default")
        self.assertTrue(
            any("dye_mode" in w and "default" in w for w in exterior["warnings"]),
            exterior["warnings"],
        )
