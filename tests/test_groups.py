"""Group (vignette) placement: members are placed relative to their anchor and mirror its orientation."""
import math
import unittest
from shapely.geometry import Polygon
from ffxiv_furniture.design import place as P
from ffxiv_furniture.design.plan import clean_placement
from tests.test_model_directed import geo, entry, run


def grp(zone, role, item_id, g, count=1, **spec):
    return entry(zone, role, item_id, g, count=count, placement=spec)


class GroupTests(unittest.TestCase):
    def test_flank_places_symmetric_pieces_on_both_sides_with_the_anchor_orientation(self):
        res = [grp(0, 'storage', 1, geo('Bookshelf', 2.0, 0.6, 3.0), group='wall', arrangement='wall_row', wall='W'),
               grp(0, 'decor', 2, geo('Planter', 0.6, 0.6, 1.2, 'Furniture/Table'), count=2, group='wall', relation='flank')]
        scene = run(res); a = Polygon(scene.placements[0]['footprint_poly']).centroid
        ps = [Polygon(p['footprint_poly']).centroid for p in scene.placements[1:]]
        self.assertEqual(len(ps), 2); self.assertTrue(all('flank' in p['note'] for p in scene.placements[1:]))
        ys = sorted(p.y - a.y for p in ps); self.assertLess(ys[0], -0.8); self.assertGreater(ys[1], 0.8); self.assertAlmostEqual(ys[0], -ys[1], delta=0.3)   # mirrored about the anchor
        self.assertEqual({round(p['yaw_degrees']) for p in scene.placements}, {round(scene.placements[0]['yaw_degrees'])})

    def test_on_top_uses_the_anchors_support_surfaces_by_height(self):
        shelf = geo('Shelf', 1.6, 0.4, 1.8, supports_top=True, top_z_local=1.8)
        shelf['surfaces'] = [{'z': 0.4, 'min_x': -.8, 'min_y': -.2, 'max_x': .8, 'max_y': .2}, {'z': 0.9, 'min_x': -.8, 'min_y': -.2, 'max_x': .8, 'max_y': .2}, {'z': 1.8, 'min_x': -.8, 'min_y': -.2, 'max_x': .8, 'max_y': .2}]
        res = [grp(0, 'storage', 1, shelf, group='s'), grp(0, 'decor', 2, geo('Book', 0.2, 0.15, 0.2, 'Item/Misc', small=True), count=3, group='s', relation='on_top')]
        scene = run(res); tops = [p for p in scene.placements if p['layer'] == 'top']
        self.assertEqual(len(tops), 3); self.assertEqual(sorted(round(p['location_m'][2], 2) for p in tops), [0.4, 0.9, 1.8])   # one per board

    def test_above_hangs_a_wall_item_over_the_anchor_on_its_wall(self):
        res = [grp(0, 'storage', 1, geo('Cabinet', 1.4, 0.5, 1.0), group='c', arrangement='wall_row', wall='W'),
               grp(0, 'wall-art', 2, geo('Scroll', 0.8, 0.05, 1.5, 'Furniture/Wall-Mounted', ptype='wall', mount_bottom_z=1.3), group='c', relation='above')]
        scene = run(res); a = Polygon(scene.placements[0]['footprint_poly']).centroid; w = Polygon(scene.placements[1]['footprint_poly']).centroid
        self.assertEqual(scene.placements[1]['layer'], 'wall'); self.assertAlmostEqual(w.y, a.y, delta=0.4)

    def test_front_faces_the_anchor_and_missing_anchor_falls_back_instead_of_dropping(self):
        res = [grp(0, 'storage', 1, geo('Desk', 1.4, 0.7, 0.8), group='d', arrangement='wall_row', wall='W'), grp(0, 'seating', 2, geo('Chair', 0.5, 0.5, 0.9, 'Furniture/Chair'), group='d', relation='front')]
        scene = run(res); a, c = scene.placements
        self.assertLess(abs(P.wrap((c['front_deg'] + c['yaw_degrees']) - (a['front_deg'] + a['yaw_degrees'] + 180))), 1.0)
        scene = run([grp(0, 'decor', 3, geo('Vase', .3, .3, .5, 'Furniture/Table'), group='nobody', relation='flank')]); self.assertEqual(len(scene.placements), 1)

    def test_schema_accepts_group_fields_and_drops_bad_ones(self):
        out, notes = clean_placement({'group': 'tea', 'relation': 'Flank', 'gap_m': 0.1}); self.assertEqual(out, {'group': 'tea', 'relation': 'flank', 'gap_m': 0.1})
        out, notes = clean_placement({'group': '', 'relation': 'beside', 'gap_m': 'x'}); self.assertEqual(out, {}); self.assertEqual(len(notes), 3)


if __name__ == '__main__':
    unittest.main()
