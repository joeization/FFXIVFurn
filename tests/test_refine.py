import math
import unittest
try:
    from shapely.geometry import Polygon, box
except ImportError:
    raise unittest.SkipTest('shapely not installed')
from ffxiv_furniture.design import place as P, refine as R

ROOM = {'polygon': Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), 'ceiling_z': 6.5, 'corridor': None, 'keepouts': [box(9, 4, 12, 8)]}


def geo(name, w, d, h, category, **info):
    g = {'name': name, 'length': w, 'width': d, 'height': h, 'category': category, 'lo': [-w / 2, -d / 2, 0.0], 'hi': [w / 2, d / 2, h]}
    g.update(info); return g


def entry(zone, role, item_id, g, count=1):
    return {'zone_index': zone, 'zone': f'z{zone}', 'area_fraction': 1.0, 'role': role, 'count': count, 'query': 'q', 'item_id': item_id, 'geometry': g}


def build():
    res = [entry(0, 'table', 1, geo('Round Table', 1.8, 1.8, 0.7, 'Furniture/Table', ptype='floor', supports_top=True, top_z_local=0.7, round_top=True)),
           entry(0, 'seating', 2, geo('Chair', 0.5, 0.5, 0.9, 'Furniture/Chair', ptype='floor', front_deg=90.0), 3),
           entry(0, 'storage', 3, geo('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf', ptype='floor', front_deg=90.0), 2)]
    scene, _ = P.place_all(ROOM, res)
    solids = [s[2] for s in scene.solid]; pls = [p for p in scene.placements if p['layer'] in ('solid', 'seat')]
    return scene, [R.Obj(i, p, it) for i, (p, it) in enumerate(zip(pls, solids))]


class FreeRotationTests(unittest.TestCase):
    def test_round_table_seats_use_non_right_angles_and_face_the_table(self):
        scene, objs = build(); seats = [o for o in objs if o.role == 'seating']; table = next(o for o in objs if o.role == 'table')
        self.assertEqual(len(seats), 3)
        tc = table.poly.centroid
        for o in seats:
            c = o.poly.centroid; want = math.degrees(math.atan2(tc.y - c.y, tc.x - c.x)) % 360
            self.assertLess(abs(P.wrap(o.facing - want)), 1.0, o.label())
        self.assertTrue(any(abs(o.yaw % 90) > 1 for o in seats), 'ring placement must produce true free angles, not only multiples of 90')

    def test_front_deg_is_per_item(self):
        it = P.make_item({'item_id': 1, 'role': 'seating', 'zone': 'z'}, geo('Side Couch', 2, 1, 1, 'Furniture/Chair', ptype='floor', front_deg=0.0), 0)
        self.assertEqual(P.face_yaw(it, 90), 90.0)        # front is +X, so facing +Y needs a 90 deg turn
        it2 = P.make_item({'item_id': 1, 'role': 'seating', 'zone': 'z'}, geo('Chair', 1, 1, 1, 'Furniture/Chair', ptype='floor', front_deg=90.0), 0)
        self.assertEqual(P.face_yaw(it2, 90), 0.0)

    def test_wall_item_uses_measured_mount_height_and_ceiling_clamp(self):
        scene = P.Scene(ROOM)
        low = P.make_item({'item_id': 1, 'role': 'wall-art', 'zone': 'z'}, geo('Wall Shelf', 1.0, 0.3, 0.6, 'Furniture/Wall-Mounted', ptype='wall', mount_bottom_z=1.3), 0)
        self.assertAlmostEqual(P.wall_item_z(scene, low), 1.3, places=6)
        tall = P.make_item({'item_id': 2, 'role': 'wall-art', 'zone': 'z'}, geo('Huge', 1.0, 0.3, 6.4, 'Furniture/Wall-Mounted', ptype='wall', mount_bottom_z=1.3), 0)
        self.assertIsNone(P.wall_item_z(scene, tall))     # cannot hang below the ceiling: refused, not squeezed


class RefineTests(unittest.TestCase):
    def test_check_flags_overlap_outside_and_keepout(self):
        scene, objs = build(); self.assertEqual(R.check(scene, objs), [])
        a, b = objs[1], objs[2]; b.pivot = a.pivot
        self.assertFalse(any('overlaps' in v for v in R.check(scene, objs)))      # overlap is legal in FFXIV: scored softly, never a hard violation
        scene, objs = build(); objs[1].pivot = (-5, -5); self.assertTrue(any('outside' in v for v in R.check(scene, objs)))
        scene, objs = build(); objs[1].pivot = (10.5, 6.0); self.assertTrue(any('stair' in v for v in R.check(scene, objs)))

    def test_try_op_is_gated_by_physics_only_not_by_any_score(self):
        scene, objs = build(); seat = next(o for o in objs if o.role == 'seating')
        self.assertNotIn('total', R.measure(scene, objs)); self.assertFalse(hasattr(R, 'optimise')); self.assertFalse(hasattr(R, 'score'))
        r = R.try_op(scene, objs, {'op': 'rotate', 'instance': seat.i, 'yaw_delta': 180}); self.assertTrue(r['accepted'])          # a "worse" facing is the model's call
        r = R.try_op(scene, objs, {'op': 'move', 'instance': seat.i, 'dx': 7, 'dy': 0}); self.assertFalse(r['accepted']); self.assertIn('exceeds', r['reason'])
        before = (seat.pivot, seat.yaw)
        r = R.try_op(scene, objs, {'op': 'place', 'instance': seat.i, 'x': 10.5, 'y': 6.0}); self.assertFalse(r['accepted']); self.assertIn('stair', r['reason'])   # physics still refuses
        self.assertEqual((seat.pivot, seat.yaw), before, 'refused ops must be fully undone')
        r = R.try_op(scene, objs, {'op': 'place', 'instance': seat.i, 'x': 3.0, 'y': 2.0, 'yaw': 45}); self.assertTrue(r['accepted'])
        c = seat.poly.centroid; self.assertAlmostEqual(c.x, 3.0, places=3); self.assertAlmostEqual(c.y, 2.0, places=3); self.assertAlmostEqual(seat.yaw, 45.0)

    def test_removal_is_allowed_by_default_in_the_review_loop(self):
        import inspect
        from ffxiv_furniture.design.visual import critique_loop
        self.assertTrue(inspect.signature(critique_loop).parameters['allow_remove'].default)


if __name__ == '__main__':
    unittest.main()
