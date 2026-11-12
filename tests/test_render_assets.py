"""Native mesh/material decoding, fixture textures, composite doors and resource caches."""

import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from ffxiv_furniture.config import load_sources, source_path
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from ffxiv_furniture.rendering.assets import Assets, mesh_materials, sections
from ffxiv_furniture.rendering.native import material_instance
from ffxiv_furniture.rendering.resources import DecodedAssetCache
from tests.support import ROOT

GAME_ASSETS = ROOT / "data/gameassets-legacy/MakePlace/Content/GameAssets"
PHASMASCAPE = GAME_ASSETS / "Furniture/Others/LavenderBedsPhasmascape"
ROOF_NAME = "HighlandCottageRoof0x28Wood0x29"
ROOF_SOURCE = (
    source_path("materials") / "HouseAssets/Roof" / ROOF_NAME / (ROOF_NAME + ".uexp")
)
SOFA_SOURCE = (
    ROOT
    / "data/geometry-legacy/MakePlace/Content/GameAssets/Furniture/Chair/LeatherSofa"
)
spike_spec = importlib.util.spec_from_file_location(
    "material_spike", ROOT / "spikes/002-native-material-render/extract.py"
)
material_spike = importlib.util.module_from_spec(spike_spec)
spike_spec.loader.exec_module(material_spike)


def frame_path(style):
    relative = Path("GameAssets/Fixture") / style / (style + ".uexp")
    return next(
        (
            Path(root) / relative
            for root in load_sources()["furniture_roots"]
            if (Path(root) / relative).is_file()
        ),
        None,
    )


def load_material_mesh(folder):
    directory = next(GAME_ASSETS.glob(f"**/{folder}"))
    record = read_static_mesh_bounds(directory / f"{folder}.uexp")
    record["item_id"] = -11
    assets = Assets([record], ROOT / "outputs/render-pipeline/cache", mi_tint=True)
    return assets.load(-11)


@unittest.skipUnless(
    (ROOT / "outputs/geometry/fill-result.json").exists(), "Local assets absent"
)
class NativeMeshDecodeTests(unittest.TestCase):

    def test_all57_material_slot_and_section_ranges(self):
        records = json.loads((ROOT / "outputs/geometry/fill-result.json").read_text())[
            "records"
        ]
        for r in records:
            v, t = read_static_mesh_triangles(r)
            m = mesh_materials(Path(r["source"]).with_suffix(".uasset"))
            s = sections(r, t, len(m))
            self.assertEqual(sum(x["triangle_count"] for x in s), len(t))

    def test_scalar_vector_texture_fields_do_not_overwrite_outer_header(self):
        p = (
            ROOT
            / "data/geometry-legacy/MakePlace/Content/GameAssets/Furniture/Chair/LeatherSofa/MI_LeatherSofa_0.uasset"
        )
        m = material_instance(p)
        self.assertTrue({"Base", "Normal", "Specular", "Tint"} <= set(m["parameters"]))


@unittest.skipUnless(PHASMASCAPE.exists(), "Local Phasmascape assets not present")
class PhasmascapeSceneTests(unittest.TestCase):

    def test_uv_scroll_mi_exposes_both_diffuse_layers(self):
        from ffxiv_furniture.rendering import native

        mi = native.material_instance(
            PHASMASCAPE / "0_fun_b0_m1374_0c_bguv_const/fun_b0_m1373_0c.uasset"
        )
        self.assertTrue(mi["parent"].endswith("M_bgUvScroll"))
        self.assertIn("fun_b0_m1373_0c_d", mi["parameters"]["DiffuseA"]["value"])
        self.assertIn("fun_b0_m1374_0d_d", mi["parameters"]["DiffuseB"]["value"])
        self.assertIn(
            "fun_b0_m1374_0d_d", mi["parameters"]["Normal"]["value"]
        )  # unchanged existing key

    def test_scene_slot_textured_with_diffuse_b(self):
        for folder in (
            PHASMASCAPE,
            GAME_ASSETS / "Fixture/SunsetPhasmascape",
            GAME_ASSETS / "Furniture/Others/MistPhasmascape",
        ):
            with self.subTest(folder=folder.name):
                rec = read_static_mesh_bounds(folder / (folder.name + ".uexp"))
                rec["item_id"] = -5
                a = Assets([rec], ROOT / "outputs/render-pipeline/cache", mi_tint=True)
                m = a.load(-5)
                cov = a.coverage[-1]
                self.assertEqual(
                    cov["textured_slots"], cov["material_slots"], cov["materials"]
                )
                scene = [d for d in m["materials"] if d.get("uv_scroll_layer")]
                self.assertEqual(len(scene), 1)
                self.assertEqual(scene[0]["uv_scroll_layer"], "DiffuseB")
                self.assertIn("static DiffuseB", scene[0]["warning"])
                self.assertGreater(
                    np.asarray(scene[0]["texture"])[..., :3].std(),
                    20,
                    "scene must be a picture, not a flat fill",
                )


class MaterialInstanceCacheTests(unittest.TestCase):
    def test_same_size_restored_mtime_invalidates_both_packages(self):
        import os
        from ffxiv_furniture.rendering import native
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'material.uasset'
            export = path.with_suffix('.uexp')
            path.write_bytes(b'head'); export.write_bytes(b'body')
            def decode(p):
                return {'bytes': p.read_bytes() + p.with_suffix('.uexp').read_bytes()}
            with patch.object(native, '_material_instance_uncached', side_effect=decode):
                previous = native.material_instance(path)
                for target in (path, export):
                    stat = target.stat()
                    target.write_bytes(b'next')
                    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                    current = native.material_instance(path)
                    self.assertNotEqual(previous, current)
                    self.assertEqual(current, decode(path))
                    previous = current


class PartitionDoorComponentTests(unittest.TestCase):

    def test_minimalist_partition_includes_native_hinged_leaf(self):
        path = frame_path("MinimalistPartitionDoor")
        if path is None:
            self.skipTest("proprietary native partition mesh unavailable")
        leaf_path = path.with_name(path.stem + "_Door.uexp")
        self.assertTrue(
            leaf_path.is_file(),
            "a missing movable leaf is not a passing frame-only render",
        )
        record = read_static_mesh_bounds(path)
        record["item_id"] = 48135
        frame_vertices, frame_triangles = read_static_mesh_triangles(record)
        leaf_record = read_static_mesh_bounds(leaf_path)
        leaf_vertices, leaf_triangles = read_static_mesh_triangles(leaf_record)
        with tempfile.TemporaryDirectory() as tmp:
            loader = Assets([record], Path(tmp), mi_tint=True)
            mesh = loader.load(48135)
        self.assertTrue("components" in mesh, "movable door mesh is currently omitted")
        self.assertEqual(len(mesh["components"]), 1)
        component = mesh["components"][0]
        self.assertEqual(component["socket"], "DoorHinge")
        self.assertTrue(
            component["source"].endswith("MinimalistPartitionDoor_Door.uexp")
        )
        self.assertEqual(component["source_sha256"], leaf_record["source_sha256"])
        self.assertEqual(component["translation_m"], [-0.67, 0.0, 0.0])
        self.assertEqual(component["yaw_degrees"], -90.0)
        self.assertFalse(component["app_verified"])
        self.assertEqual(
            len(mesh["vertices"]), len(frame_vertices) + len(leaf_vertices)
        )
        self.assertEqual(
            len(mesh["triangles"]), len(frame_triangles) + len(leaf_triangles)
        )
        np.testing.assert_array_equal(
            mesh["vertices"][: len(frame_vertices)], frame_vertices
        )
        # Independently apply the decoded native -90 degree hinge pose.
        expected = np.asarray(leaf_vertices) @ np.array(
            [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
        ) + [-0.67, 0, 0]
        np.testing.assert_allclose(
            mesh["vertices"][len(frame_vertices) :], expected, atol=1e-8
        )
        self.assertEqual(len(mesh["uv"]), len(mesh["vertices"]))
        self.assertEqual(loader.coverage[0]["material_slots"], 6)
        self.assertEqual(loader.coverage[0]["textured_slots"], 6)
        self.assertEqual(loader.coverage[0]["components"], mesh["components"])

    def test_log_partition_has_both_native_hinged_leaves(self):
        path = frame_path("LogPartitionDoor")
        if path is None:
            self.skipTest("proprietary native partition mesh unavailable")
        record = read_static_mesh_bounds(path)
        record["item_id"] = 1
        leaf_record = read_static_mesh_bounds(path.with_name(path.stem + "_Door.uexp"))
        with tempfile.TemporaryDirectory() as tmp:
            mesh = Assets([record], Path(tmp), mi_tint=True).load(1)
        self.assertEqual(
            [c["socket"] for c in mesh["components"]], ["DoorHinge", "DoorHinge2"]
        )
        self.assertEqual(
            [c["translation_m"] for c in mesh["components"]],
            [[-0.9, 0, 0], [0.9, 0, 0]],
        )
        self.assertEqual([c["yaw_degrees"] for c in mesh["components"]], [-90, 90])
        self.assertEqual(
            len(mesh["vertices"]),
            record["vertex_count"] + 2 * leaf_record["vertex_count"],
        )

    def test_all_available_partition_families_have_valid_composite_geometry(self):
        paths = set()
        for root in load_sources()["furniture_roots"]:
            paths.update(
                (Path(root) / "GameAssets/Fixture").glob(
                    "*PartitionDoor/*PartitionDoor.uexp"
                )
            )
        if not paths:
            self.skipTest("proprietary native partition meshes unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            for path in sorted(paths):
                with self.subTest(style=path.stem):
                    record = read_static_mesh_bounds(path)
                    record["item_id"] = 1
                    loader = Assets([record], Path(tmp), mi_tint=True)
                    mesh = loader.load(1)
                    self.assertGreater(len(mesh["vertices"]), record["vertex_count"])
                    self.assertEqual(len(mesh["vertices"]), len(mesh["uv"]))
                    self.assertGreaterEqual(int(mesh["triangles"].min()), 0)
                    self.assertLess(int(mesh["triangles"].max()), len(mesh["vertices"]))
                    self.assertEqual(
                        sum(g["triangle_count"] for g in mesh["groups"]),
                        len(mesh["triangles"]),
                    )
                    self.assertTrue(
                        all(
                            -1 <= g["material_index"] < len(mesh["materials"])
                            for g in mesh["groups"]
                        )
                    )
                    self.assertEqual(
                        loader.coverage[0]["material_slots"], len(mesh["materials"])
                    )
                    self.assertTrue(
                        all(c["pose"] == "native-socket" for c in mesh["components"])
                    )

    def test_cached_composite_preserves_leaf_dependencies_and_provenance(self):
        path = frame_path("MinimalistPartitionDoor")
        if path is None:
            self.skipTest("proprietary native partition mesh unavailable")
        record = read_static_mesh_bounds(path)
        record["item_id"] = 48135
        cache = DecodedAssetCache()
        with tempfile.TemporaryDirectory() as tmp:
            cold = Assets([record], Path(tmp), mi_tint=True, resource_cache=cache)
            first = cold.load(48135)
            warm = Assets([record], Path(tmp), mi_tint=True, resource_cache=cache)
            second = warm.load(48135)
        self.assertIs(first, second)
        self.assertEqual(warm.coverage, cold.coverage)
        self.assertEqual(warm.dependencies, cold.dependencies)
        for ext in (".uasset", ".uexp", ".ubulk"):
            leaf = path.with_name(path.stem + "_Door" + ext)
            self.assertIn(str(leaf.resolve()), warm.dependencies)


@unittest.skipUnless(
    (
        ROOT
        / "data/house-legacy/MakePlace/Content/HouseAssets/InteriorStyles/Shirogane/Material"
    ).exists()
    and (
        ROOT
        / "data/house-materials-legacy/MakePlace/Content/HouseAssets/Flooring/GladeFlooring"
    ).exists(),
    "extracted game assets absent",
)
class StructureTextureTests(unittest.TestCase):

    def test_structure_meshes_resolve_native_textures_and_fixture_textures(self):
        from ffxiv_furniture.rendering.house_materials import fixture_texture

        recs = json.loads(
            (ROOT / "outputs/house-layouts/native-bounds.json").read_text(
                encoding="utf-8"
            )
        )["records"]
        rec = next(
            r
            for r in recs
            if r["source"]
            .replace(chr(92), "/")
            .endswith("InteriorStyles/Shirogane/Stair/Stair1.uexp")
        )
        a = Assets([], ROOT / "outputs/render-pipeline/cache")
        a.records[-1] = {**rec, "item_id": -1}
        mesh = a.load(-1)
        textured = [m for m in mesh["materials"] if m["texture"] is not None]
        self.assertGreaterEqual(
            len(textured), 7
        )  # stair/frame/ceiling slots decode their own Base texture
        self.assertEqual(textured[0]["texture"].shape[2], 4)
        fx = [
            {
                "type": "Floor",
                "level": "Ground Floor",
                "name": "Glade Flooring",
                "itemId": 6459,
            }
        ]
        t = fixture_texture("Floor", fx)
        self.assertEqual(t["texture"].dtype, np.uint8)
        self.assertEqual(t["provenance"]["item_id"], 6459)
        with self.assertRaises(ValueError):
            fixture_texture("Wall", fx)  # no silent substitution

    def test_unextracted_fixture_is_refused_not_guessed(self):
        from ffxiv_furniture.rendering.house_materials import fixture_texture

        with self.assertRaises(FileNotFoundError):
            fixture_texture(
                "Floor",
                [
                    {
                        "type": "Floor",
                        "level": "Ground Floor",
                        "name": "No Such Flooring",
                        "itemId": 1,
                    }
                ],
            )


@unittest.skipUnless(
    (GAME_ASSETS.exists() and any(GAME_ASSETS.glob("**/ArmamentShowcase"))),
    "native furniture assets not extracted",
)
class MaterialEffectTests(unittest.TestCase):

    def test_glass_slot_is_translucent_not_missing(self):
        m = load_material_mesh("ArmamentShowcase")
        glass = [d for d in m["materials"] if "M_MasterGlass" in d["native_reference"]]
        self.assertEqual(len(glass), 1)
        self.assertTrue(glass[0].get("glass"))
        self.assertGreater(glass[0]["glass_alpha"], 0.0)
        self.assertLess(glass[0]["glass_alpha"], 0.5)
        self.assertNotIn("No such file", glass[0].get("warning") or "")

    def test_waterfall_partition_water_is_visible_translucent_water(self):
        # Waterfall Partition: curtain slot binds M_Rain, basin glow binds a standalone M_BrightWater material.
        # Both used to vanish (alpha 0.12) or turn into an opaque brown fallback block.
        m = load_material_mesh("WaterfallPartition")
        by = {
            d["native_reference"].rsplit("/", 1)[-1].split(".")[0]: d
            for d in m["materials"]
        }
        rain, water = by["M_Rain"], by["M_BrightWater"]
        self.assertTrue(rain.get("glass"))
        self.assertGreaterEqual(rain["glass_alpha"], 0.25)
        self.assertTrue(water.get("glass"))
        self.assertGreaterEqual(water["glass_alpha"], 0.4)
        r, g, b = water["flat_color"]
        self.assertGreater(b, r + 0.2, "water reads blue, not the brown fallback")
        self.assertTrue(water.get("emissive"))

    def test_masked_masters_are_cut_out(self):
        for folder, slot in (("WalnutFlowerVases", 0), ("BluebirdMobile", 0)):
            with self.subTest(folder=folder):
                self.assertTrue(
                    load_material_mesh(folder)["materials"][slot].get("cutout")
                )

    def test_emissive_only_on_emissive_slots(self):
        m = load_material_mesh("ClassicTableLamp")
        par = [str(d.get("parent", "")).split(".")[-1] for d in m["materials"]]
        glow = [i for i, d in enumerate(m["materials"]) if d.get("emissive")]
        self.assertTrue(glow)
        self.assertTrue(
            all(par[i].startswith("M_MasterEmissive") for i in glow), par
        )  # lamp body (Tint/Mat slots) does not glow
        full = [i for i in glow if par[i] == "M_MasterEmissive"]
        masked = [i for i in glow if par[i] != "M_MasterEmissive"]
        self.assertTrue(full and masked, par)
        e = m["materials"][full[0]]["emissive"]
        self.assertEqual(len(e), 3)
        self.assertGreater(e[0], e[2])  # warm tint, not white
        self.assertLess(max(m["materials"][masked[0]]["emissive"]), max(e))

    def test_tint_mi_without_tint_uses_master_default(self):
        if not (
            ROOT
            / "data/gameassets-legacy/MakePlace/Content/Materials/M_MasterTint.uexp"
        ).exists():
            self.skipTest("master materials not extracted")
        from ffxiv_furniture.rendering import native

        self.assertEqual(
            [
                round(x, 4)
                for x in native.master_default_tint(
                    ROOT
                    / "data/gameassets-legacy/MakePlace/Content/Materials/M_MasterTint.uasset"
                )
            ],
            [0.3613, 0.2423, 0.107],
        )
        d = load_material_mesh("WalnutFlowerVases")["materials"][
            2
        ]  # walnut vase bodies: M_MasterTint MI with no Tint (rendered white before)
        self.assertEqual(d.get("mi_tint_source"), "parent-default")
        rgb = np.asarray(d["texture"])[..., :3].reshape(-1, 3).mean(0)
        self.assertGreater(rgb[0], rgb[2] + 20, rgb)

    def test_unsupported_mi_layout_gets_guessed_base(self):
        m = load_material_mesh("CarbuncleLantern")
        d = m["materials"][1]
        self.assertIsNotNone(d["texture"])
        self.assertIn("guessed", d["warning"])


@unittest.skipUnless(ROOF_SOURCE.is_file(), "Local native Highland roof absent")
class HighlandRoofTests(unittest.TestCase):

    def test_all_native_roof_sections_have_real_textures(self):
        record = read_static_mesh_bounds(ROOF_SOURCE)
        record["item_id"] = "roof-regression"
        with tempfile.TemporaryDirectory() as cache:
            assets = Assets([record], Path(cache), mi_tint=True)
            loaded = assets.load("roof-regression")
            coverage = assets.coverage[0]
            self.assertEqual(coverage["material_slots"], 5)
            self.assertEqual(coverage["textured_slots"], 5, coverage["materials"])
            self.assertFalse(coverage["notes"])
            for material in loaded["materials"]:
                self.assertIsNotNone(material["texture"])
                self.assertIsNone(material["warning"])
                self.assertGreater(float(material["texture"][..., :3].std()), 1.0)


class MaterialSpikeHeaderTests(unittest.TestCase):

    def test_zero_mask_and_truncation(self):
        r = material_spike.Reader(struct.pack("<H", 0x0780) + bytes([6]), [])
        self.assertEqual(r.header(), ([0, 1, 2], {1, 2}))
        with self.assertRaises(ValueError):
            material_spike.Reader(struct.pack("<H", 0x0780), []).header()


@unittest.skipUnless(SOFA_SOURCE.exists(), "Local native sofa assets not present")
class NativeMaterialSpikeTests(unittest.TestCase):

    def test_native_material_binding(self):
        result = material_spike.material_instance(
            SOFA_SOURCE / "MI_LeatherSofa_0.uasset"
        )
        self.assertTrue(result["parent"].endswith("M_MasterTint.M_MasterTint"))
        self.assertEqual(result["parameters"]["Base"]["kind"], "texture")
        self.assertIn("fun_b0_m0899_1a_d", result["parameters"]["Base"]["value"])
        self.assertEqual(result["parameters"]["Tint"]["value"][3], 1)
        self.assertGreater(result["remaining_native_properties_not_decoded"], 0)

    def test_external_and_inline_mips_all_checked(self):
        for suffix in ("d", "n", "s"):
            image, meta = material_spike.decode_texture(
                SOFA_SOURCE / ("fun_b0_m0899_1a_" + suffix + ".uasset")
            )
            self.assertEqual(image.size, (512, 512))
            self.assertEqual(len(meta["mips"]), 10)
            self.assertEqual(meta["mips"][-1]["dimensions"], [1, 1])
            self.assertEqual(len(meta["source_file_hashes"]), 3)

    def test_wrong_resource_index_rejected_without_source_write(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "texture.uasset"
            for suffix in (".uasset", ".uexp", ".ubulk"):
                shutil.copyfile(
                    SOFA_SOURCE / ("fun_b0_m0899_1a_d" + suffix),
                    target.with_suffix(suffix),
                )
            data = bytearray(target.with_suffix(".uexp").read_bytes())
            struct.pack_into("<i", data, 106, 1)
            target.with_suffix(".uexp").write_bytes(data)
            with self.assertRaisesRegex(ValueError, "resource index"):
                material_spike.decode_texture(target)


class AssetReuseTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.content = self.root / "Content"
        self.content.mkdir()
        record = {
            "item_id": 42,
            "source": str(self.content / "Mesh.uexp"),
            "source_sha256": "source",
        }
        self.assets = Assets([record], self.root / "cache", mi_tint=True)
        self.geometry = self.patch(
            "ffxiv_furniture.rendering.assets.read_static_mesh_triangles",
            return_value=(
                np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]),
                np.array([[0, 1, 2]]),
            ),
        )
        self.patch(
            "ffxiv_furniture.rendering.assets.uvs", return_value=np.zeros((3, 2))
        )
        self.patch(
            "ffxiv_furniture.rendering.assets.mesh_materials",
            return_value=[{"resolved": "/Game/Material.MI"}],
        )
        self.patch(
            "ffxiv_furniture.rendering.assets.sections",
            return_value=[
                {"material_index": 0, "first_triangle": 0, "triangle_count": 1}
            ],
        )
        self.patch(
            "ffxiv_furniture.rendering.assets.native.material_instance",
            return_value={
                "parent": "/Game/M_MasterTint",
                "parameters": {
                    "Base": {"kind": "texture", "value": "/Game/Base"},
                    "Tint": {"value": [1, 1, 1, 1]},
                },
                "source_sha256": "material",
            },
        )
        self.decode = self.patch(
            "ffxiv_furniture.rendering.assets.native.decode_texture",
            side_effect=lambda p: (
                Image.new("RGBA", (2, 2), (255, 255, 255, 255)),
                {"source_file_hashes": {"Base.uexp": "texture"}},
            ),
        )

    def patch(self, *args, **kwargs):
        p = patch(*args, **kwargs)
        m = p.start()
        self.addCleanup(p.stop)
        return m

    def test_same_asset_returns_same_decoded_mesh(self):
        a = self.assets.load(42)
        b = self.assets.load(42)
        self.assertIs(a, b)
        self.assertEqual(self.geometry.call_count, 1)
        self.assertEqual(self.decode.call_count, 1)
        self.assertEqual(len(self.assets.coverage), 1)

    def test_dye_variants_are_independent_and_reused(self):
        red = self.assets.load(42, (255, 0, 0))
        green = self.assets.load(42, (0, 255, 0))
        red2 = self.assets.load(42, (255, 0, 0))
        self.assertIs(red, red2)
        self.assertIsNot(red, green)
        self.assertFalse(
            np.array_equal(
                red["materials"][0]["texture"], green["materials"][0]["texture"]
            )
        )
        self.assertEqual(self.geometry.call_count, 2)
        self.assertEqual(len(self.assets.coverage), 2)

    def shared(self):
        import inspect
        from ffxiv_furniture.rendering import assets

        self.assertIn(
            "resource_cache",
            inspect.signature(Assets).parameters,
            "cross-view decoded resource reuse is missing",
        )
        return assets.DecodedAssetCache(max_bytes=1024 * 1024, max_entries=4)

    def clone(self, cache):
        return Assets(
            list(self.assets.records.values()),
            self.root / "cache",
            mi_tint=True,
            resource_cache=cache,
        )

    def test_cross_view_resource_reuse_and_source_invalidation(self):
        cache = self.shared()
        a = self.clone(cache).load(42)
        b = self.clone(cache).load(42)
        self.assertIs(a, b)
        self.assertEqual(self.geometry.call_count, 1)
        (self.content / "Mesh.uexp").write_bytes(b"changed source")
        c = self.clone(cache).load(42)
        self.assertIsNot(a, c)
        self.assertEqual(self.geometry.call_count, 2)

    def test_missing_material_creation_invalidates_cached_fallback(self):
        cache = self.shared()
        a = self.clone(cache).load(42)
        (self.content / "Material.uasset").write_bytes(b"new higher-priority asset")
        b = self.clone(cache).load(42)
        self.assertIsNot(a, b)

    def test_resource_cache_detects_same_size_rewrite_with_identical_mtime(self):
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.uexp'
            path.write_bytes(b'old bytes')
            stamp = path.stat()
            cache = DecodedAssetCache()
            result = {'vertices': np.zeros((3, 3))}
            cache.put('mesh', result, {}, [path])
            cached = cache.get('mesh')
            assert cached is not None
            self.assertIs(cached[0], result)
            path.write_bytes(b'new bytes')
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            # Simulate filesystems where even ctime/inode are unchanged.
            with patch.object(Path, 'stat', return_value=stamp):
                self.assertIsNone(cache.get('mesh'))

    def test_resource_cache_is_bounded(self):
        from ffxiv_furniture.rendering import assets

        self.shared()
        cache = assets.DecodedAssetCache(max_bytes=1, max_entries=4)
        self.clone(cache).load(42)
        self.clone(cache).load(42)
        self.assertEqual(cache.stats()["entries"], 0)
        self.assertEqual(self.geometry.call_count, 2)

    def test_cross_view_dye_variants_do_not_alias(self):
        cache = self.shared()
        a = self.clone(cache).load(42, (255, 0, 0))
        b = self.clone(cache).load(42, (0, 255, 0))
        c = self.clone(cache).load(42, (255, 0, 0))
        self.assertIs(a, c)
        self.assertIsNot(a, b)


class ProjectionReuseTests(unittest.TestCase):

    def api(self):
        import importlib

        try:
            return importlib.import_module("ffxiv_furniture.rendering.projection")
        except ModuleNotFoundError:
            self.fail("camera-independent exact projection cache is missing")

    def ring(self):
        v = np.array(
            [
                [-2, -2, 0],
                [2, -2, 0],
                [2, 2, 0],
                [-2, 2, 0],
                [-1, -1, 0],
                [1, -1, 0],
                [1, 1, 0],
                [-1, 1, 0],
            ],
            float,
        )
        t = np.array(
            [
                (0, 1, 4),
                (1, 5, 4),
                (1, 2, 5),
                (2, 6, 5),
                (2, 3, 6),
                (3, 7, 6),
                (3, 0, 7),
                (0, 4, 7),
            ]
        )
        return v, t

    def test_exact_hole_and_concavity_not_a_bbox(self):
        from shapely.geometry import Point

        api = self.api()
        v, t = self.ring()
        p = api.projected_footprint(v, t)
        self.assertAlmostEqual(p.area, 12)
        self.assertFalse(p.covers(Point(0, 0)))
        self.assertTrue(p.covers(Point(1.5, 0)))

    def test_identical_content_reuses_projection_but_edits_do_not(self):
        api = self.api()
        v, t = self.ring()
        p = api.projected_footprint(v, t)
        self.assertIs(p, api.projected_footprint(v.copy(), t.copy()))
        changed = v.copy()
        changed[:, 0] += 10
        q = api.projected_footprint(changed, t)
        self.assertAlmostEqual(q.bounds[0], 8)
        self.assertIsNot(p, q)

    def test_tilted_geometry_and_degenerate_triangles(self):
        api = self.api()
        v, t = self.ring()
        original_y = v[:, 1].copy()
        v[:, 1] *= 0.5
        v[:, 2] = original_y * np.sqrt(3) / 2
        self.assertAlmostEqual(api.projected_footprint(v, t).area, 6)
        self.assertTrue(
            api.projected_footprint(
                np.array([[0, 0, 0], [0, 0, 1], [0, 0, 2]]), [(0, 1, 2)]
            ).is_empty
        )


class FixtureFolderTests(unittest.TestCase):

    def test_folder_resolves_special_characters(self):
        from ffxiv_furniture.rendering.house_materials import fixture_folder
        from ffxiv_furniture.config import catalog_path

        with sqlite3.connect(catalog_path().as_uri() + "?mode=ro", uri=True) as db:
            self.assertEqual(
                fixture_folder(
                    db,
                    "CeilingLight",
                    dict(name="Flame Ceiling Fan & Lamp", itemId=6471),
                ),
                "FlameCeilingFan0x26Lamp",
            )
            self.assertEqual(
                fixture_folder(
                    db, "CeilingLight", dict(name="Watcher's Palace Ceiling Lamp")
                ),
                "Watcher_sPalaceCeilingLamp",
            )
            self.assertEqual(
                fixture_folder(
                    db, "Wallpaper", dict(name="Palace of the Dead Interior Wall")
                ),
                "PalaceOfTheDeadInteriorWall",
            )
        self.assertEqual(
            fixture_folder(None, "CeilingLight", dict(name="Flame Ceiling Fan & Lamp")),
            "FlameCeilingFan0x26Lamp",
        )
