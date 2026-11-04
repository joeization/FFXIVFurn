"""Model-directed placement: overlap is soft, orientation/arrangement/region come from the model, stairs stay hard."""
import math
import unittest
from shapely.geometry import Polygon, box
from ffxiv_furniture.design import place as P, refine as R
from ffxiv_furniture.design.plan import validate_plan, clean_placement

ROOM = {'polygon': Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), 'ceiling_z': 6.5, 'corridor': None, 'keepouts': [box(9, 4, 12, 8)]}
VOCAB = {'color:red'}


def geo(name, w, d, h, category='Furniture/Shelf', **info):
    g = {'name': name, 'length': w, 'width': d, 'height': h, 'category': category, 'lo': [-w / 2, -d / 2, 0.0], 'hi': [w / 2, d / 2, h], 'ptype': 'floor', 'front_deg': 90.0}
    g.update(info); return g


def entry(zone, role, item_id, g, count=1, placement=None, key=None, region=None, frac=1.0):
    return {'zone_index': zone, 'zone': f'z{zone}', 'area_fraction': frac, 'role': role, 'count': count, 'query': 'q', 'item_id': item_id, 'geometry': g, 'placement': placement or {}, 'entry_key': key or f'{zone}:{item_id}', 'region': region}


def run(res, room=ROOM): return P.place_all(room, res)[0]


class OverlapTests(unittest.TestCase):
    def test_full_floor_places_everything_by_relaxing_overlap_instead_of_dropping(self):
        small = {'polygon': Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]), 'ceiling_z': 6.5, 'corridor': None}
        scene = run([entry(0, 'storage', 1, geo('Big Cabinet', 2.0, 1.0, 2.0), count=12)], small)
        self.assertEqual(len(scene.unplaced), 0); self.assertEqual(len(scene.placements), 12)
        self.assertTrue(any('overlap' in p['note'] for p in scene.placements))

    def test_allow_overlap_is_honoured_from_the_start_and_never_enters_stairs(self):
        scene = run([entry(0, 'architecture', 1, geo('Screen', 2.0, 0.1, 2.0, 'Fixture'), count=20, placement={'allow_overlap': True, 'arrangement': 'cluster'})])
        stairs = box(9, 4, 12, 8)
        for p in scene.placements: self.assertFalse(Polygon(p['footprint_poly']).intersects(stairs), p)
        self.assertEqual(len(scene.placements), 20)

    def test_overlap_is_not_a_hard_violation_but_is_scored(self):
        res = [entry(0, 'storage', 3, geo('Shelf', 1.5, 0.5, 2.0), count=2)]
        scene = run(res); solids = [s[2] for s in scene.solid]; pls = [p for p in scene.placements if p['layer'] in ('solid', 'seat')]
        objs = [R.Obj(i, p, it) for i, (p, it) in enumerate(zip(pls, solids))]; base = R.measure(scene, objs)
        objs[1].pivot = objs[0].pivot
        after = R.measure(scene, objs)
        self.assertEqual(R.check(scene, objs), []); self.assertGreater(after['components']['overlap'], base['components']['overlap'])


class OrientationTests(unittest.TestCase):
    def test_default_free_pieces_do_not_all_face_one_way(self):
        scene = run([entry(0, 'architecture', 1, geo('Screen', 2.0, 0.1, 2.0, 'Fixture'), count=8)])
        self.assertGreaterEqual(len({round(p['yaw_degrees']) % 180 for p in scene.placements}), 2)

    def test_model_facing_numbers_and_compass_are_applied(self):
        for f, want in ((45, 45.0), ('N', 90.0), ('W', 180.0)):
            scene = run([entry(0, 'decor', 1, geo('Vase', 0.3, 0.3, 0.5, 'Furniture/Table'), placement={'facing': f, 'arrangement': 'grid'})])
            p = scene.placements[0]; self.assertAlmostEqual(P.wrap((p['front_deg'] + p['yaw_degrees']) - want), 0.0, places=1, msg=str(f))

    def test_alternate_facing_staggers_a_line(self):
        scene = run([entry(0, 'architecture', 1, geo('Screen', 1.5, 0.1, 2.0, 'Fixture'), count=4, placement={'arrangement': 'line', 'facing': 'alternate'})])
        self.assertEqual(len({round((p['front_deg'] + p['yaw_degrees']) % 180) for p in scene.placements}), 2)

    def test_model_facing_is_not_penalised_by_the_default_facing_rule(self):
        res = [entry(0, 'storage', 3, geo('Shelf', 1.5, 0.5, 2.0), count=1, placement={'facing': 'along_wall'})]
        scene = run(res); it = scene.solid[0][2]; o = R.Obj(0, scene.placements[0], it)
        self.assertIsNone(R.desired_facing(scene, o, [o]))


class ArrangementTests(unittest.TestCase):
    def test_wall_row_is_contiguous_on_the_requested_wall(self):
        scene = run([entry(0, 'storage', 1, geo('Bookshelf', 2.0, 0.6, 3.0), count=3, placement={'arrangement': 'wall_row', 'wall': 'W', 'spacing_m': 0.0})])
        ps = sorted(scene.placements, key=lambda p: p['footprint_m'][1])
        self.assertEqual(len(ps), 3)
        for p in ps: self.assertLess(p['footprint_m'][0], 0.2)                       # all against the west wall
        gaps = [b['footprint_m'][1] - a['footprint_m'][3] for a, b in zip(ps, ps[1:])]; self.assertTrue(all(abs(g) < 0.1 for g in gaps), gaps)

    def test_ring_surrounds_the_zone_table_facing_it(self):
        res = [entry(0, 'table', 1, geo('Table', 1.6, 1.6, 0.7, 'Furniture/Table', supports_top=True, top_z_local=0.7)), entry(0, 'decor', 2, geo('Cushion', 0.5, 0.5, 0.3, 'Furniture/Chair'), count=4, placement={'arrangement': 'ring'})]
        scene = run(res); t = scene.tables[0][0].centroid
        for p in scene.placements[1:]:
            c = Polygon(p['footprint_poly']).centroid; want = math.degrees(math.atan2(t.y - c.y, t.x - c.x)) % 360
            self.assertLess(abs(P.wrap(p['front_deg'] + p['yaw_degrees'] - want)), 1.0)

    def test_region_hint_puts_the_zone_where_the_model_said(self):
        res = [entry(0, 'storage', 1, geo('Shelf', 1.0, 0.5, 1.5), count=2, region='west', frac=0.5), entry(1, 'storage', 2, geo('Shelf2', 1.0, 0.5, 1.5), count=2, region='north', frac=0.5)]
        scene = run(res)
        for p in scene.placements:
            cx = sum(p['footprint_m'][0::2]) / 2; cy = sum(p['footprint_m'][1::2]) / 2
            if p['zone'] == 'z0': self.assertLess(cx, 6.6)
            else: self.assertGreater(cy, 3.5)

    def test_decor_goes_on_any_flat_surface_not_only_tables(self):
        res = [entry(0, 'storage', 1, geo('Counter', 2.0, 0.6, 0.9, supports_top=True, top_z_local=0.9)), entry(0, 'decor', 2, geo('Teacup', 0.15, 0.15, 0.12, 'Item/Misc', small=True))]
        scene = run(res); self.assertEqual(scene.placements[1]['layer'], 'top')


class SchemaTests(unittest.TestCase):
    def test_placement_fields_are_validated_and_bad_ones_dropped_not_fatal(self):
        e = {'facing': 'alternate', 'arrangement': 'wall_row', 'wall': 'w', 'spacing_m': -0.2, 'allow_overlap': True}
        out, notes = clean_placement(e); self.assertEqual(out, {'facing': 'alternate', 'arrangement': 'wall_row', 'wall': 'W', 'spacing_m': -0.2, 'allow_overlap': True}); self.assertEqual(notes, [])
        out, notes = clean_placement({'facing': 'sideways', 'arrangement': 'spiral', 'wall': 'up', 'spacing_m': 'x', 'allow_overlap': 'yes'}); self.assertEqual(out, {}); self.assertEqual(len(notes), 5)
        out, _ = clean_placement({'facing': 135}); self.assertEqual(out['facing'], 135.0)
        p = validate_plan({'title': 't', 'theme': 'x', 'used_floors': ['ground'], 'fixtures': {'floor': 'a', 'wall': 'b', 'light': 'c'},
                           'zones': [{'name': 'a', 'region': 'Northwest', 'items': [{'role': 'architecture', 'query': 'screen', 'count': 6, 'facing': 'alternate', 'arrangement': 'line'}]}]}, vocab_keys=VOCAB, max_items=100)
        self.assertEqual(p['zones'][0]['items'][0]['placement'], {'facing': 'alternate', 'arrangement': 'line'}); self.assertEqual(p['zones'][0]['region'], 'northwest')


if __name__ == '__main__':
    unittest.main()
