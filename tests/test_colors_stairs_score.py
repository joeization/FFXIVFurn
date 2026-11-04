import json
import unittest
from pathlib import Path
try:
    import numpy as np
    from shapely.geometry import Polygon, box
except ImportError:
    raise unittest.SkipTest('numpy/shapely not installed')
ROOT = Path(__file__).resolve().parents[1]


class DyeTests(unittest.TestCase):
    def test_default_dye_follows_alpha_mask_in_linear_light(self):
        from ffxiv_furniture.rendering.assets import apply_default_dye
        rgba = np.zeros((2, 2, 4), np.uint8); rgba[..., :3] = 200
        rgba[0, :, 3] = 255; rgba[1, :, 3] = 0           # top row dyeable, bottom row masked out (trim keeps its own colour)
        out = apply_default_dye(rgba, (201, 145, 86))
        self.assertTrue((out[1, :, :3] == 200).all())                       # untouched where mask is 0
        self.assertTrue((out[0, :, 0] < 200).all() and (out[0, :, 2] < out[0, :, 0]).all())   # tinted warm where mask is 255
        self.assertTrue((out[..., 3] == 255).all())                         # alpha is a mask, never transparency

    def test_white_base_with_cork_brown_matches_app_sample_within_tolerance(self):
        from ffxiv_furniture.rendering.assets import apply_default_dye
        base = np.zeros((1, 1, 4), np.uint8); base[..., :3] = 223; base[..., 3] = 255
        got = apply_default_dye(base, (201, 145, 86))[0, 0, :3].astype(int)       # app screenshot rug median was (196,135,73) after its lighting
        self.assertLess(abs(int(got[0]) - 176), 6); self.assertLess(abs(int(got[1]) - 126), 8); self.assertLess(abs(int(got[2]) - 74), 8)


@unittest.skipUnless((ROOT / 'outputs/house-layouts/medium-stair-transforms.json').exists(), 'decoded stairs absent')
class StairOrientationRegression(unittest.TestCase):
    def test_stairs_use_yaw_only_and_stay_inside_the_walls(self):
        t = json.loads((ROOT / 'outputs/house-layouts/medium-stair-transforms.json').read_text(encoding='utf-8'))
        for name in ('Stairs', 'Stairs2_9'):
            a = t['actors'][name]; self.assertEqual(a['scale'], [1.0, 1.0, 1.0]); self.assertEqual(a['scale_stored'][0], -1.0); self.assertFalse(a['scale_applied'])
            x0, y0, x1, y1 = t['footprints'][name]['bounds_xy_m']
            self.assertGreaterEqual(x0, -12.1); self.assertLessEqual(x1, 12.1); self.assertGreaterEqual(y0, -8.1); self.assertLessEqual(y1, 8.1)   # applying scale.x=-1 broke this by 0.9 m

    def test_keepouts_cover_the_decoded_footprints(self):
        from ffxiv_furniture.house_profiles import room_keepouts
        ground = room_keepouts(ROOT, 'Medium', 'ground'); t = json.loads((ROOT / 'outputs/house-layouts/medium-stair-transforms.json').read_text(encoding='utf-8'))
        for name in ('Stairs', 'Stairs2_9'):
            x0, y0, x1, y1 = t['footprints'][name]['bounds_xy_m']; probe = box(x0 + 1.0, y0 + 1.5, x1 - 1.0, y1 - 1.5)
            self.assertTrue(any(k.intersects(probe) for k in ground), name)


class NoScoreTests(unittest.TestCase):
    def test_measure_states_it_is_not_a_score_and_lists_what_it_cannot_judge(self):
        from ffxiv_furniture.design import place as P, refine as R
        room = {'polygon': Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), 'ceiling_z': 6.5, 'corridor': None, 'keepouts': []}
        def geo(n, w, d, h, c, **i): return {'name': n, 'length': w, 'width': d, 'height': h, 'category': c, 'lo': [-w / 2, -d / 2, 0.0], 'hi': [w / 2, d / 2, h], **i}
        res = [{'zone_index': 0, 'zone': 'z', 'area_fraction': 1.0, 'role': 'storage', 'count': 3, 'query': 'q', 'item_id': 1, 'geometry': geo('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf', ptype='floor')}]
        scene, _ = P.place_all(room, res); solids = [s[2] for s in scene.solid]; pls = [p for p in scene.placements if p['layer'] in ('solid', 'seat')]
        objs = [R.Obj(i, p, it) for i, (p, it) in enumerate(zip(pls, solids))]; m = R.measure(scene, objs)
        for banned in ('total', 'weighted_average', 'weakest', 'weakest_penalty'): self.assertNotIn(banned, m)
        self.assertIn('NOT a quality score', m['kind']); self.assertTrue(any('looks good' in u for u in m['not_measured'])); self.assertEqual(set(m['components']), set(R.COMPONENTS))


if __name__ == '__main__':
    unittest.main()
