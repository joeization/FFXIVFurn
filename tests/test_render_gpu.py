"""Raster depth, clipping, transparency, cutaway roles and GPU resource ownership."""

import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from ffxiv_furniture.rendering.raster import render
from ffxiv_furniture.rendering.raster_gpu import render_gpu

try:
    import moderngl

    moderngl.create_standalone_context(require=330).release()
    GPU_AVAILABLE = True
except Exception as error:
    GPU_AVAILABLE = False
    GPU_UNAVAILABLE_REASON = f"GPU rendering not available: {error!r}"


class RasterOutputTests(unittest.TestCase):

    def test_depth_id16_and_near_clipping(self):
        near = np.array([[-1, 2, -1], [1, 2, -1], [0, 2, 1]])
        far = near * 2
        camera = {"position": [0, 0, 0], "target": [0, 1, 0]}
        with tempfile.TemporaryDirectory() as temp:
            for meshes in [
                [
                    {"id": 300, "vertices": near, "triangles": [(0, 1, 2)]},
                    {"id": 400, "vertices": far, "triangles": [(0, 1, 2)]},
                ],
                [
                    {"id": 400, "vertices": far, "triangles": [(0, 1, 2)]},
                    {"id": 300, "vertices": near, "triangles": [(0, 1, 2)]},
                ],
            ]:
                path = Path(temp) / "view.png"
                render(meshes, camera, path, size=(160, 120), debug_buffers=True)
                with Image.open(Path(temp) / "view-ids.png") as im:
                    self.assertEqual(np.asarray(im)[60, 80], 300)
                self.assertAlmostEqual(
                    float(np.load(Path(temp) / "view-depth.npy")[60, 80]), 2
                )
            vertices = np.array(
                [[-0.05, 0.05, -0.05], [0.1, 0.3, -0.05], [0, 0.3, 0.15]]
            )
            result = render(
                [{"id": 1, "vertices": vertices, "triangles": [(0, 1, 2)]}],
                camera,
                Path(temp) / "clip.png",
                size=(160, 120),
            )
            self.assertEqual(result["near_clipped_triangles"], 1)
            self.assertTrue(result["visible_object_pixels"])

    def test_only_requested_image_is_written(self):
        mesh = [
            {
                "id": 300,
                "vertices": np.array([[-1, 2, -1], [1, 2, -1], [0, 2, 1]]),
                "triangles": [(0, 1, 2)],
                "role": "furniture",
            }
        ]
        camera = {"position": [0, 0, 0], "target": [0, 1, 0]}
        for fn in (render,):
            for labels in (False, True):
                with self.subTest(
                    backend=fn.__name__, labels=labels
                ), tempfile.TemporaryDirectory() as tmp:
                    result = fn(
                        mesh,
                        camera,
                        Path(tmp) / "view.jpg",
                        size=(160, 120),
                        labels=labels,
                    )
                    files = {f.name for f in Path(tmp).iterdir()}
                    expected = "view-labeled.jpg" if labels else "view.jpg"
                    self.assertEqual(files, {expected})
                    self.assertEqual(Path(result["image"]).name, expected)
                    with Image.open(result["image"]) as im:
                        self.assertEqual(im.format, "JPEG")
                    self.assertEqual("labeled" in result, labels)
                    self.assertNotIn("ids", result)
                    self.assertNotIn("depth", result)
                    self.assertGreater(result["visible_object_pixels"]["300"], 0)

    def test_debug_buffers_are_explicit_and_do_not_add_plain_duplicate(self):
        mesh = [
            {
                "id": 300,
                "vertices": np.array([[-1, 2, -1], [1, 2, -1], [0, 2, 1]]),
                "triangles": [(0, 1, 2)],
                "role": "furniture",
            }
        ]
        camera = {"position": [0, 0, 0], "target": [0, 1, 0]}
        with tempfile.TemporaryDirectory() as tmp:
            result = render(
                mesh,
                camera,
                Path(tmp) / "view.jpg",
                size=(160, 120),
                labels=True,
                debug_buffers=True,
            )
            self.assertEqual(
                {f.name for f in Path(tmp).iterdir()},
                {"view-labeled.jpg", "view-ids.png", "view-depth.npy"},
            )  # ID buffer stays lossless PNG
            self.assertEqual(np.asarray(Image.open(result["ids"]))[60, 80], 300)
            self.assertAlmostEqual(float(np.load(result["depth"])[60, 80]), 2)


class MirrorViewTests(unittest.TestCase):

    def test_mirror_is_exact_horizontal_flip_of_raw_projection(self):
        mesh = [
            {
                "id": 1,
                "vertices": np.array([[0.5, 4, 0], [2.5, 4, 0], [1.0, 4, 2]], float),
                "triangles": np.array([[0, 1, 2]]),
                "role": "furniture",
            }
        ]
        cam = {"position": [0, 0, 1], "target": [0, 4, 1], "fov": 70}
        with tempfile.TemporaryDirectory() as tmp:
            render(mesh, cam, Path(tmp) / "a.png", size=(96, 64), debug_buffers=True)
            render(
                mesh,
                {**cam, "mirror_x": True},
                Path(tmp) / "b.png",
                size=(96, 64),
                debug_buffers=True,
            )
            a = np.asarray(Image.open(Path(tmp) / "a-ids.png"))
            b = np.asarray(Image.open(Path(tmp) / "b-ids.png"))
        self.assertTrue(
            (a != a[:, ::-1]).any(),
            "scene must be asymmetric for the test to mean anything",
        )
        self.assertTrue(
            np.array_equal(b, a[:, ::-1]),
            "object-ID mask must be an exact left-right flip",
        )


def scene():
    rng = np.random.default_rng(3)
    tex = rng.integers(0, 255, (8, 8, 4), dtype=np.uint8)
    quad = np.array([[-1.5, 4, -1], [1.5, 4, -1], [1.5, 4, 1.2], [-1.5, 4, 1.2]], float)
    uv = np.array([[0, 0], [2.3, 0], [2.3, 1.7], [0, 1.7]], float)
    tri = np.array([[-3, 6, -1], [-1, 6, -1], [-2, 6, 2]], float)
    box = np.array([[1, 3, -1], [3, 3, -1], [2, 3.5, 1]], float)
    near = np.array([[-0.3, -0.2, -0.3], [0.3, 1.5, -0.3], [0, 1.5, 0.4]], float)
    return [
        {
            "id": 300,
            "vertices": quad,
            "triangles": [(0, 1, 2), (0, 2, 3)],
            "uv": uv,
            "material": {"texture": tex, "tint": np.array([0.9, 0.6, 0.5])},
            "role": "furniture",
        },
        {
            "id": 301,
            "vertices": tri,
            "triangles": [(0, 1, 2)],
            "flat_color": [0.8, 0.3, 0.2],
            "role": "furniture",
        },
        {"id": 302, "vertices": box, "triangles": [(0, 1, 2)], "role": "furniture"},
        {"id": 303, "vertices": near, "triangles": [(0, 1, 2)], "role": "furniture"},
        {
            "id": 304,
            "vertices": quad + [0, -1, 0],
            "triangles": [(0, 1, 2)],
            "role": "enclosure",
        },
    ]


def ids_of(camera, meshes=None, **kw):
    with tempfile.TemporaryDirectory() as t:
        r = render_gpu(
            meshes or scene(),
            camera,
            Path(t) / "v.png",
            size=(320, 240),
            debug_buffers=True,
            **kw,
        )
        return (
            r,
            np.asarray(Image.open(Path(t) / "v-ids.png")).astype(int)[45:],
            np.load(Path(t) / "v-depth.npy")[45:],
        )


@unittest.skipUnless(
    GPU_AVAILABLE, globals().get("GPU_UNAVAILABLE_REASON", "GPU available")
)
class GpuRasterTests(unittest.TestCase):

    CAM = {"position": [0, 0, 0], "target": [0, 1, 0], "fov": 70}

    def test_objects_are_visible_and_near_triangle_is_clipped(self):
        r, ids, depth = ids_of(self.CAM, approximate_tint=True)
        self.assertGreater((ids > 0).sum(), 2000)
        self.assertTrue({300, 301, 302} <= set(np.unique(ids)))
        self.assertGreaterEqual(r["near_clipped_triangles"], 1)

    def test_mirror_flips_horizontally_and_cutaway_skips_enclosure(self):
        _, a, _ = ids_of(dict(self.CAM))
        _, b, _ = ids_of(dict(self.CAM, mirror_x=True))
        self.assertGreater(((a > 0) != (b > 0)).sum(), 500)
        self.assertEqual(set(np.unique(a[:, ::-1])) - {0}, set(np.unique(b)) - {0})
        _, c, _ = ids_of(dict(self.CAM, cutaway=True))
        self.assertNotIn(304, set(np.unique(c)))

    def test_depth_order_is_independent_of_submission_order(self):
        near = np.array([[-1, 2, -1], [1, 2, -1], [0, 2, 1]], float)
        far = near * 2
        for ms in (
            [
                {"id": 300, "vertices": near, "triangles": [(0, 1, 2)]},
                {"id": 400, "vertices": far, "triangles": [(0, 1, 2)]},
            ],
            [
                {"id": 400, "vertices": far, "triangles": [(0, 1, 2)]},
                {"id": 300, "vertices": near, "triangles": [(0, 1, 2)]},
            ],
        ):
            _, ids, depth = ids_of({"position": [0, 0, 0], "target": [0, 1, 0]}, ms)
            self.assertEqual(ids[75, 160], 300)
            self.assertAlmostEqual(float(depth[75, 160]), 2, places=3)

    def test_cutout_discards_transparent_texels(self):
        tex = np.zeros((4, 4, 4), np.uint8)
        tex[..., :3] = 200
        tex[:, :2, 3] = 255  # left half opaque, right half transparent
        quad = np.array([[-1, 2, -1], [1, 2, -1], [1, 2, 1], [-1, 2, 1]], float)
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        widths = {}
        for cut in (True, False):
            ms = [
                {
                    "id": 300,
                    "vertices": quad,
                    "triangles": [(0, 1, 2), (0, 2, 3)],
                    "uv": uv,
                    "material": {"texture": tex, "cutout": cut},
                    "role": "furniture",
                }
            ]
            _, ids, _ = ids_of(
                {"position": [0, 0, 0], "target": [0, 1, 0], "fov": 70}, ms
            )
            xs = np.where(ids[75] == 300)[0]
            widths[cut] = xs.max() - xs.min()
        self.assertGreater(widths[False], 150)
        self.assertLess(
            widths[True], 0.6 * widths[False]
        )  # the transparent right half is discarded only with cutout


class GlassRasterTests(unittest.TestCase):

    def test_glass_blends_and_keeps_object_behind_in_id_buffer(self):
        quad = lambda y, i, extra: dict(
            id=i,
            vertices=np.array([[-1, y, -1], [1, y, -1], [1, y, 1], [-1, y, 1]], float),
            triangles=np.array([[0, 1, 2], [0, 2, 3]]),
            uv=None,
            role="furniture",
            **{"material": None, **extra},
        )
        back = quad(2.0, 1, dict(flat_color=(0.9, 0.1, 0.1)))
        glass = quad(
            1.0,
            2,
            dict(
                flat_color=(0.8, 0.9, 0.95),
                material={"glass": True, "glass_alpha": 0.25, "texture": None},
            ),
        )
        cam = dict(position=[0, -3, 0], target=[0, 0, 0], fov=40)
        with tempfile.TemporaryDirectory() as tmp:
            r = render_gpu([back, glass], cam, Path(tmp) / "g.png", size=(160, 160))
            px = np.asarray(Image.open(Path(tmp) / "g.png").convert("RGB"))[
                100, 80
            ].astype(int)
            r2 = render_gpu([back], cam, Path(tmp) / "b.png", size=(160, 160))
            px2 = np.asarray(Image.open(Path(tmp) / "b.png").convert("RGB"))[
                100, 80
            ].astype(int)
        self.assertGreater(
            px[1] + px[2], px2[1] + px2[2] + 20, "glass must tint what is behind it"
        )
        self.assertGreater(px[0], 80, "red object must stay visible through glass")


class CeilingLightCutawayTests(unittest.TestCase):

    def test_plan_cutaway_drops_pendants_and_windows_but_eye_level_keeps_them(self):
        from pathlib import Path as _P

        quad = lambda i, z, role: {
            "id": i,
            "vertices": np.array(
                [[-1, -1, z], [1, -1, z], [1, 1, z], [-1, 1, z]], float
            )
            * [3 if z == 0 else 1, 3 if z == 0 else 1, 1],
            "triangles": np.array([[0, 1, 2], [0, 2, 3]]),
            "role": role,
            "flat_color": [0.5, 0.5, 0.5],
        }
        cam = {"position": [0, -0.01, 10], "target": [0, 0, 0], "fov": 60}
        for role in ("ceiling_light", "window"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as t:
                scene = [quad(1, 0, "furniture"), quad(2, 2, role)]
                plan = render(
                    scene, dict(cam, cutaway=True), _P(t) / "a.jpg", size=(96, 64)
                )
                eye = render(scene, cam, _P(t) / "b.jpg", size=(96, 64))
                self.assertNotIn("2", plan["visible_object_pixels"])
                self.assertIn("2", eye["visible_object_pixels"])


class GpuTextureReuseTests(unittest.TestCase):

    def test_repeated_material_uploads_texture_only_once(self):
        import inspect
        from types import SimpleNamespace
        from ffxiv_furniture.rendering.raster_gpu import _prepare

        self.assertIn(
            "texture_pool",
            inspect.signature(_prepare).parameters,
            "per-scene GPU texture reuse is missing",
        )

        class Context:
            def __init__(self):
                self.uploads = 0

            def buffer(self, data):
                return SimpleNamespace()

            def vertex_array(self, *args):
                return SimpleNamespace()

            def texture(self, *args, **kwargs):
                self.uploads += 1
                return SimpleNamespace()

        ctx = Context()
        pool = {}
        tex = np.full((4, 4, 4), 255, np.uint8)
        mesh = {
            "id": 1,
            "vertices": np.array([[0, 1, 0], [1, 1, 0], [0, 1, 1]], float),
            "triangles": [(0, 1, 2)],
            "material": {"texture": tex},
        }
        a = _prepare(ctx, None, mesh, None, texture_pool=pool)
        b = _prepare(ctx, None, {**mesh, "id": 2}, None, texture_pool=pool)
        self.assertIs(a["texture"], b["texture"])
        self.assertEqual(ctx.uploads, 1)
        c = _prepare(
            ctx,
            None,
            {**mesh, "material": {"texture": tex, "cutout": True}},
            None,
            texture_pool=pool,
        )
        self.assertIsNot(a["texture"], c["texture"])
        self.assertEqual(ctx.uploads, 2)


class RasterPixelCountTests(unittest.TestCase):

    def test_banner_pixels_are_not_counted(self):
        from ffxiv_furniture.rendering.raster import BANNER_HEIGHT

        mesh = [
            dict(
                id=5,
                vertices=np.array([[-50, 2, -50], [50, 2, -50], [0, 2, 80]], float),
                triangles=[(0, 1, 2)],
                role="furniture",
            )
        ]
        with tempfile.TemporaryDirectory() as t:
            r = render(
                mesh,
                dict(position=[0, 0, 0], target=[0, 1, 0], fov=70),
                Path(t) / "v.jpg",
                size=(96, 64),
                debug_buffers=True,
            )
            idm = np.asarray(Image.open(Path(t) / "v-ids.png"))
        self.assertEqual(
            r["visible_object_pixels"]["5"], int((idm[BANNER_HEIGHT:] == 5).sum())
        )
        self.assertLess(r["visible_object_pixels"]["5"], int((idm == 5).sum()))


class GpuResourceTests(unittest.TestCase):

    def test_framebuffer_released_when_draw_raises(self):
        import ffxiv_furniture.rendering.raster_gpu as g

        ctx, _ = g._Gpu.context()
        bad = [
            dict(
                id=0,
                vertices=np.array([[0, 2, 0], [1, 2, 0], [0, 2, 1]], float),
                triangles=[(0, 1, 2)],
            )
        ]  # id 0 -> ValueError mid-render
        before = len(ctx.objects) if hasattr(ctx, "objects") else None
        from unittest.mock import patch

        allocated = []
        original = ctx.framebuffer

        def track(*args, **kwargs):
            fbo = original(*args, **kwargs)
            allocated.append((fbo, (*fbo.color_attachments, fbo.depth_attachment)))
            return fbo

        with patch.object(ctx, "framebuffer", side_effect=track):
            for _ in range(3):
                with tempfile.TemporaryDirectory() as t, self.assertRaises(ValueError):
                    g.render_gpu(
                        bad,
                        dict(position=[0, 0, 0], target=[0, 1, 0]),
                        Path(t) / "v.jpg",
                        size=(64, 64),
                    )
        self.assertEqual(len(allocated), 3)
        for fbo, textures in allocated:
            for resource in (fbo, *textures):
                self.assertEqual(type(resource.mglo).__name__, "InvalidObject")
        if before is not None:
            self.assertEqual(len(ctx.objects), before)
        self.assertEqual(g._Gpu.live_framebuffers, 0)
