"""GPU rasterizer behaviour (the only rasterizer); skipped when no OpenGL 3.3 context is available."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
try:
    import moderngl
    moderngl.create_standalone_context(require=330).release()
    from ffxiv_furniture.rendering.raster_gpu import render_gpu
except Exception as e:   # no moderngl / no GL driver
    raise unittest.SkipTest(f'GPU rendering not available: {e!r}')


def scene():
    rng = np.random.default_rng(3); tex = rng.integers(0, 255, (8, 8, 4), dtype=np.uint8)
    quad = np.array([[-1.5, 4, -1], [1.5, 4, -1], [1.5, 4, 1.2], [-1.5, 4, 1.2]], float); uv = np.array([[0, 0], [2.3, 0], [2.3, 1.7], [0, 1.7]], float)
    tri = np.array([[-3, 6, -1], [-1, 6, -1], [-2, 6, 2]], float); box = np.array([[1, 3, -1], [3, 3, -1], [2, 3.5, 1]], float); near = np.array([[-.3, -.2, -.3], [.3, 1.5, -.3], [0, 1.5, .4]], float)
    return [{'id': 300, 'vertices': quad, 'triangles': [(0, 1, 2), (0, 2, 3)], 'uv': uv, 'material': {'texture': tex, 'tint': np.array([.9, .6, .5])}, 'role': 'furniture'},
            {'id': 301, 'vertices': tri, 'triangles': [(0, 1, 2)], 'flat_color': [.8, .3, .2], 'role': 'furniture'},
            {'id': 302, 'vertices': box, 'triangles': [(0, 1, 2)], 'role': 'furniture'},
            {'id': 303, 'vertices': near, 'triangles': [(0, 1, 2)], 'role': 'furniture'},
            {'id': 304, 'vertices': quad + [0, -1, 0], 'triangles': [(0, 1, 2)], 'role': 'enclosure'}]


def ids_of(camera, meshes=None, **kw):
    with tempfile.TemporaryDirectory() as t:
        r = render_gpu(meshes or scene(), camera, Path(t) / 'v.png', size=(320, 240), debug_buffers=True, **kw)
        return r, np.asarray(Image.open(Path(t) / 'v-ids.png')).astype(int)[45:], np.load(Path(t) / 'v-depth.npy')[45:]


class GpuTests(unittest.TestCase):
    CAM = {'position': [0, 0, 0], 'target': [0, 1, 0], 'fov': 70}

    def test_objects_are_visible_and_near_triangle_is_clipped(self):
        r, ids, depth = ids_of(self.CAM, approximate_tint=True)
        self.assertGreater((ids > 0).sum(), 2000); self.assertTrue({300, 301, 302} <= set(np.unique(ids))); self.assertGreaterEqual(r['near_clipped_triangles'], 1)

    def test_mirror_flips_horizontally_and_cutaway_skips_enclosure(self):
        _, a, _ = ids_of(dict(self.CAM)); _, b, _ = ids_of(dict(self.CAM, mirror_x=True))
        self.assertGreater(((a > 0) != (b > 0)).sum(), 500); self.assertEqual(set(np.unique(a[:, ::-1])) - {0}, set(np.unique(b)) - {0})
        _, c, _ = ids_of(dict(self.CAM, cutaway=True)); self.assertNotIn(304, set(np.unique(c)))

    def test_depth_order_is_independent_of_submission_order(self):
        near = np.array([[-1, 2, -1], [1, 2, -1], [0, 2, 1]], float); far = near * 2
        for ms in ([{'id': 300, 'vertices': near, 'triangles': [(0, 1, 2)]}, {'id': 400, 'vertices': far, 'triangles': [(0, 1, 2)]}],
                   [{'id': 400, 'vertices': far, 'triangles': [(0, 1, 2)]}, {'id': 300, 'vertices': near, 'triangles': [(0, 1, 2)]}]):
            _, ids, depth = ids_of({'position': [0, 0, 0], 'target': [0, 1, 0]}, ms); self.assertEqual(ids[75, 160], 300); self.assertAlmostEqual(float(depth[75, 160]), 2, places=3)

    def test_cutout_discards_transparent_texels(self):
        tex = np.zeros((4, 4, 4), np.uint8); tex[..., :3] = 200; tex[:, :2, 3] = 255   # left half opaque, right half transparent
        quad = np.array([[-1, 2, -1], [1, 2, -1], [1, 2, 1], [-1, 2, 1]], float); uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        widths = {}
        for cut in (True, False):
            ms = [{'id': 300, 'vertices': quad, 'triangles': [(0, 1, 2), (0, 2, 3)], 'uv': uv, 'material': {'texture': tex, 'cutout': cut}, 'role': 'furniture'}]
            _, ids, _ = ids_of({'position': [0, 0, 0], 'target': [0, 1, 0], 'fov': 70}, ms); xs = np.where(ids[75] == 300)[0]; widths[cut] = xs.max() - xs.min()
        self.assertGreater(widths[False], 150); self.assertLess(widths[True], 0.6 * widths[False])   # the transparent right half is discarded only with cutout


if __name__ == '__main__':
    unittest.main()
