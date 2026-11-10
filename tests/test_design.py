"""Design planning, placement, groups, model direction, palettes, dye and stair regressions."""

import colorsys
import json
import math
import struct
import tempfile
import unittest
from ffxiv_furniture.design import place as P, refine as R, concept as C, rerank as RR
from ffxiv_furniture.design.plan import validate_plan, clean_placement
from pathlib import Path
from shapely.geometry import Polygon, box
from unittest import mock
from tests.support import ROOT


try:
    from shapely.geometry import Polygon, box
except ImportError:  # optional render/design dependency
    raise unittest.SkipTest('shapely not installed')


L_SHAPE = Polygon([(0, 0), (12, 0), (12, 8), (4, 8), (4, 4), (0, 4)])  # notch x0..4, y4..8 is NOT floor


L_SHAPED_ROOM = {'polygon': L_SHAPE, 'ceiling_z': 6.5, 'corridor': None}


PLAN_VOCAB = {'color:red', 'material:wood-like appearance'}


def plan_geometry(name, w, d, h, category, z0=0.0, **info):
    g = {'name': name, 'length': w, 'width': d, 'height': h, 'category': category, 'lo': [-w / 2, -d / 2, z0], 'hi': [w / 2, d / 2, z0 + h]}
    g.update(info); return g


def plan_entry(zone, role, item_id, g, count=1):
    return {'zone_index': zone, 'zone': f'z{zone}', 'area_fraction': 0.5, 'role': role, 'count': count, 'query': 'q', 'item_id': item_id, 'geometry': g}


def plan(**kw):
    p = {'title': 't', 'theme': 'th', 'used_floors': ['ground'], 'fixtures': {'floor': 'a', 'wall': 'b', 'light': 'c'},
         'zones': [{'name': 'a', 'area_fraction': 1, 'items': [{'role': 'seating', 'query': 'red chair', 'count': 2, 'tags': ['color:red', 'bogus:tag']}]}]}
    p.update(kw); return p


class DesignPlanTests(unittest.TestCase):
    def test_valid_and_unknown_tags_dropped_not_invented(self):
        out = validate_plan(plan(), vocab_keys=PLAN_VOCAB, max_items=10)
        self.assertEqual(out['zones'][0]['items'][0]['tags'], ['color:red']); self.assertEqual(out['dropped_tags'], ['bogus:tag'])
        self.assertEqual(out['planned_instances'], 2)

    def test_rejections(self):
        for bad in (plan(used_floors=['ground', 'upper']), plan(fixtures={'floor': 'a'}), plan(zones=[]),
                    plan(zones=[{'name': 'a', 'items': [{'role': 'seating', 'query': '紅色椅子', 'count': 1}]}]),
                    plan(zones=[{'name': 'a', 'items': [{'role': 'sofa-ish', 'query': 'x', 'count': 1}]}]),
                    plan(zones=[{'name': 'a', 'items': [{'role': 'seating', 'query': 'x', 'count': 0}]}])):
            with self.assertRaises(ValueError): validate_plan(bad, vocab_keys=PLAN_VOCAB, max_items=10)
        with self.assertRaises(ValueError): validate_plan(plan(), vocab_keys=PLAN_VOCAB, max_items=1)  # budget


class FloorPlacementTests(unittest.TestCase):
    def test_split_regions_conserve_area(self):
        regions = P.split_regions(L_SHAPE, [1, 1]); self.assertAlmostEqual(sum(r.area for r in regions), L_SHAPE.area, 3)
        self.assertAlmostEqual(regions[0].area, L_SHAPE.area / 2, delta=1.0)

    def make(self):
        res = [plan_entry(0, 'rug', 1, plan_geometry('Rug', 3, 3, 0.02, 'Furniture/Rug', ptype='rug')), plan_entry(0, 'table', 2, plan_geometry('Table', 1.6, 0.9, 0.7, 'Furniture/Table', ptype='floor', supports_top=True, top_z_local=0.7)),
               plan_entry(0, 'seating', 3, plan_geometry('Chair', 0.5, 0.5, 0.9, 'Furniture/Chair', ptype='floor'), 4), plan_entry(0, 'storage', 4, plan_geometry('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf', ptype='floor'), 2),
               plan_entry(1, 'wall-art', 5, plan_geometry('Scroll', 1.0, 0.03, 4.1, 'Item/Printed', z0=-2.05, ptype='wall', mount_bottom_z=0.05), 2), plan_entry(1, 'lighting', 6, plan_geometry('Lantern', 0.3, 0.3, 1.5, 'Lighting', ptype='floor')),
               plan_entry(1, 'decor', 7, plan_geometry('Vase', 0.3, 0.3, 0.4, 'Item/Others', ptype='floor'), 2)]
        return P.place_all(L_SHAPED_ROOM, res)

    def test_everything_inside_real_outline_without_floor_overlap_and_deterministic(self):
        scene, _ = self.make()
        self.assertEqual(scene.unplaced, [])
        solids = [s[0] for s in scene.solid]
        for pl in scene.placements:
            poly = Polygon(pl['footprint_poly'])
            if pl['layer'] in ('solid', 'seat', 'wall', 'rug'): self.assertTrue(L_SHAPE.buffer(0.01).covers(poly), pl)
            self.assertFalse(poly.intersects(box(0.01, 4.01, 3.99, 7.99)), 'must not stand in the notch')
        for i, a in enumerate(solids):
            for b in solids[i + 1:]: self.assertFalse(a.intersects(b) and a.intersection(b).area > 1e-6, 'floor items must not overlap')
        self.assertEqual(self.make()[0].placements, scene.placements)

    def test_seats_face_table_art_on_wall_and_tabletop_uses_table_height(self):
        scene, _ = self.make()
        table = next(p for p in scene.placements if p['role'] == 'table'); tc = Polygon(table['footprint_poly']).centroid
        around = [p for p in scene.placements if p['layer'] == 'seat']; self.assertGreaterEqual(len(around), 3)
        for p in around:
            c = Polygon(p['footprint_poly']).centroid; facing = (p['front_deg'] + p['yaw_degrees']) % 360; want = math.degrees(math.atan2(tc.y - c.y, tc.x - c.x)) % 360
            self.assertLess(abs(P.wrap(facing - want)), 45.0)   # rectangular table: seat faces perpendicular to its side, so bearing to the centre may differ; round tops are exact (test_refine)
        for p in (p for p in scene.placements if p['layer'] == 'wall'):
            self.assertLess(Polygon(p['footprint_poly']).distance(L_SHAPE.boundary), 0.06)
            self.assertGreaterEqual(p['location_m'][2] - 2.05, -1e-6); self.assertLessEqual(p['location_m'][2] + 2.05, 6.5)
        tops = [p for p in scene.placements if p['layer'] == 'top']
        for p in tops: self.assertAlmostEqual(p['location_m'][2], table['z_top_m'], places=3)   # stands exactly on the measured table top


class StairKeepoutTests(unittest.TestCase):
    def test_keepout_is_never_entered_and_regions_exclude_it(self):
        keep = box(6, 0, 12, 8)
        room = {'polygon': Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), 'ceiling_z': 6.5, 'corridor': None, 'keepouts': [keep]}
        res = [plan_entry(0, 'rug', 1, plan_geometry('Rug', 3, 3, 0.02, 'Furniture/Rug', ptype='rug')), plan_entry(0, 'table', 2, plan_geometry('Table', 1.6, 0.9, 0.7, 'Furniture/Table', ptype='floor')),
               plan_entry(0, 'seating', 3, plan_geometry('Chair', 0.5, 0.5, 0.9, 'Furniture/Chair', ptype='floor'), 4), plan_entry(0, 'storage', 4, plan_geometry('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf', ptype='floor'), 6),
               plan_entry(0, 'wall-art', 5, plan_geometry('Scroll', 1.0, 0.03, 2.0, 'Item/Printed', ptype='wall', mount_bottom_z=1.0), 4)]
        scene, rep = P.place_all(room, res)
        self.assertGreater(len(scene.placements), 8)
        for pl in scene.placements: self.assertFalse(Polygon(pl['footprint_poly']).intersects(keep), pl)
        self.assertLessEqual(max(r[2] for r in rep['regions'].values()), 6.0 + 1e-6)

    @unittest.skipUnless((ROOT / 'data/house-legacy/MakePlace/Content/Maps/XIVMediumHouse.uexp').exists() and (ROOT / 'outputs/house-layouts/native-map-tables.json').exists(), 'native map absent')
    def test_decoded_medium_stair_transforms(self):
        d = (ROOT / 'data/house-legacy/MakePlace/Content/Maps/XIVMediumHouse.uexp').read_bytes()
        ex = {e['name']: e for e in json.loads((ROOT / 'outputs/house-layouts/native-map-tables.json').read_text(encoding='utf-8'))['Medium']['exports']}
        def tf(n):
            e = ex[n]; b = d[e['serial_offset_in_uexp']:e['serial_offset_in_uexp'] + e['serial_size']]
            qx, qy, qz, qw, tx, ty, tz, sx, sy, sz = struct.unpack_from('<10d', b, 35); return (round(qz, 4), round(qw, 4), tx, ty, tz, sx, sy, sz)
        self.assertEqual(tf('Stairs'), (0.7071, 0.7071, 700.0, 400.0, 0.0, -1.0, 1.0, 1.0))
        self.assertEqual(tf('Stairs2_9'), (1.0, 0.0, -800.0, 300.0, -700.0, -1.0, 1.0, 1.0))
        self.assertEqual(tf('Railing2_2')[2:5], (-800.0, 500.0, 0.0))

    @unittest.skipUnless((ROOT / 'outputs/house-layouts/medium-stair-transforms.json').exists(), 'decoded stairs absent')
    def test_keepouts_per_floor_exist_and_match_stair_positions(self):
        from ffxiv_furniture.house_profiles import room_keepouts
        g, u, b = (room_keepouts(ROOT, 'Medium', f) for f in ('ground', 'upper', 'basement'))
        self.assertEqual((len(g), len(u), len(b)), (2, 1, 1))
        self.assertTrue(u[0].centroid.x > 0 and b[0].centroid.x < 0)
        self.assertEqual(room_keepouts(ROOT, 'Large', 'ground'), [])


DIRECTED_ROOM = {'polygon': Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), 'ceiling_z': 6.5, 'corridor': None, 'keepouts': [box(9, 4, 12, 8)]}


DIRECTED_VOCAB = {'color:red'}


def directed_geometry(name, w, d, h, category='Furniture/Shelf', **info):
    g = {'name': name, 'length': w, 'width': d, 'height': h, 'category': category, 'lo': [-w / 2, -d / 2, 0.0], 'hi': [w / 2, d / 2, h], 'ptype': 'floor', 'front_deg': 90.0}
    g.update(info); return g


def directed_entry(zone, role, item_id, g, count=1, placement=None, key=None, region=None, frac=1.0):
    return {'zone_index': zone, 'zone': f'z{zone}', 'area_fraction': frac, 'role': role, 'count': count, 'query': 'q', 'item_id': item_id, 'geometry': g, 'placement': placement or {}, 'entry_key': key or f'{zone}:{item_id}', 'region': region}


def place_directed(res, room=DIRECTED_ROOM): return P.place_all(room, res)[0]


class OverlapTests(unittest.TestCase):
    def test_full_floor_places_everything_by_relaxing_overlap_instead_of_dropping(self):
        small = {'polygon': Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]), 'ceiling_z': 6.5, 'corridor': None}
        scene = place_directed([directed_entry(0, 'storage', 1, directed_geometry('Big Cabinet', 2.0, 1.0, 2.0), count=12)], small)
        self.assertEqual(len(scene.unplaced), 0); self.assertEqual(len(scene.placements), 12)
        self.assertTrue(any('overlap' in p['note'] for p in scene.placements))

    def test_allow_overlap_is_honoured_from_the_start_and_never_enters_stairs(self):
        scene = place_directed([directed_entry(0, 'architecture', 1, directed_geometry('Screen', 2.0, 0.1, 2.0, 'Fixture'), count=20, placement={'allow_overlap': True, 'arrangement': 'cluster'})])
        stairs = box(9, 4, 12, 8)
        for p in scene.placements: self.assertFalse(Polygon(p['footprint_poly']).intersects(stairs), p)
        self.assertEqual(len(scene.placements), 20)

    def test_overlap_is_not_a_hard_violation_but_is_scored(self):
        res = [directed_entry(0, 'storage', 3, directed_geometry('Shelf', 1.5, 0.5, 2.0), count=2)]
        scene = place_directed(res); solids = [s[2] for s in scene.solid]; pls = [p for p in scene.placements if p['layer'] in ('solid', 'seat')]
        objs = [R.Obj(i, p, it) for i, (p, it) in enumerate(zip(pls, solids))]; base = R.measure(scene, objs)
        objs[1].pivot = objs[0].pivot
        after = R.measure(scene, objs)
        self.assertEqual(R.check(scene, objs), []); self.assertGreater(after['components']['overlap'], base['components']['overlap'])


class OrientationTests(unittest.TestCase):
    def test_default_free_pieces_do_not_all_face_one_way(self):
        scene = place_directed([directed_entry(0, 'architecture', 1, directed_geometry('Screen', 2.0, 0.1, 2.0, 'Fixture'), count=8)])
        self.assertGreaterEqual(len({round(p['yaw_degrees']) % 180 for p in scene.placements}), 2)

    def test_model_facing_numbers_and_compass_are_applied(self):
        for f, want in ((45, 45.0), ('N', 90.0), ('W', 180.0)):
            scene = place_directed([directed_entry(0, 'decor', 1, directed_geometry('Vase', 0.3, 0.3, 0.5, 'Furniture/Table'), placement={'facing': f, 'arrangement': 'grid'})])
            p = scene.placements[0]; self.assertAlmostEqual(P.wrap((p['front_deg'] + p['yaw_degrees']) - want), 0.0, places=1, msg=str(f))

    def test_alternate_facing_staggers_a_line(self):
        scene = place_directed([directed_entry(0, 'architecture', 1, directed_geometry('Screen', 1.5, 0.1, 2.0, 'Fixture'), count=4, placement={'arrangement': 'line', 'facing': 'alternate'})])
        self.assertEqual(len({round((p['front_deg'] + p['yaw_degrees']) % 180) for p in scene.placements}), 2)

    def test_model_facing_is_not_penalised_by_the_default_facing_rule(self):
        res = [directed_entry(0, 'storage', 3, directed_geometry('Shelf', 1.5, 0.5, 2.0), count=1, placement={'facing': 'along_wall'})]
        scene = place_directed(res); it = scene.solid[0][2]; o = R.Obj(0, scene.placements[0], it)
        self.assertIsNone(R.desired_facing(scene, o, [o]))


class ArrangementTests(unittest.TestCase):
    def test_wall_row_is_contiguous_on_the_requested_wall(self):
        scene = place_directed([directed_entry(0, 'storage', 1, directed_geometry('Bookshelf', 2.0, 0.6, 3.0), count=3, placement={'arrangement': 'wall_row', 'wall': 'W', 'spacing_m': 0.0})])
        ps = sorted(scene.placements, key=lambda p: p['footprint_m'][1])
        self.assertEqual(len(ps), 3)
        for p in ps: self.assertLess(p['footprint_m'][0], 0.2)                       # all against the west wall
        gaps = [b['footprint_m'][1] - a['footprint_m'][3] for a, b in zip(ps, ps[1:])]; self.assertTrue(all(abs(g) < 0.1 for g in gaps), gaps)

    def test_ring_surrounds_the_zone_table_facing_it(self):
        res = [directed_entry(0, 'table', 1, directed_geometry('Table', 1.6, 1.6, 0.7, 'Furniture/Table', supports_top=True, top_z_local=0.7)), directed_entry(0, 'decor', 2, directed_geometry('Cushion', 0.5, 0.5, 0.3, 'Furniture/Chair'), count=4, placement={'arrangement': 'ring'})]
        scene = place_directed(res); t = scene.tables[0][0].centroid
        for p in scene.placements[1:]:
            c = Polygon(p['footprint_poly']).centroid; want = math.degrees(math.atan2(t.y - c.y, t.x - c.x)) % 360
            self.assertLess(abs(P.wrap(p['front_deg'] + p['yaw_degrees'] - want)), 1.0)

    def test_region_hint_puts_the_zone_where_the_model_said(self):
        res = [directed_entry(0, 'storage', 1, directed_geometry('Shelf', 1.0, 0.5, 1.5), count=2, region='west', frac=0.5), directed_entry(1, 'storage', 2, directed_geometry('Shelf2', 1.0, 0.5, 1.5), count=2, region='north', frac=0.5)]
        scene = place_directed(res)
        for p in scene.placements:
            cx = sum(p['footprint_m'][0::2]) / 2; cy = sum(p['footprint_m'][1::2]) / 2
            if p['zone'] == 'z0': self.assertLess(cx, 6.6)
            else: self.assertGreater(cy, 3.5)

    def test_decor_goes_on_any_flat_surface_not_only_tables(self):
        res = [directed_entry(0, 'storage', 1, directed_geometry('Counter', 2.0, 0.6, 0.9, supports_top=True, top_z_local=0.9)), directed_entry(0, 'decor', 2, directed_geometry('Teacup', 0.15, 0.15, 0.12, 'Item/Misc', small=True))]
        scene = place_directed(res); self.assertEqual(scene.placements[1]['layer'], 'top')


class PlacementSchemaTests(unittest.TestCase):
    def test_placement_fields_are_validated_and_bad_ones_dropped_not_fatal(self):
        e = {'facing': 'alternate', 'arrangement': 'wall_row', 'wall': 'w', 'spacing_m': -0.2, 'allow_overlap': True}
        out, notes = clean_placement(e); self.assertEqual(out, {'facing': 'alternate', 'arrangement': 'wall_row', 'wall': 'W', 'spacing_m': -0.2, 'allow_overlap': True}); self.assertEqual(notes, [])
        out, notes = clean_placement({'facing': 'sideways', 'arrangement': 'spiral', 'wall': 'up', 'spacing_m': 'x', 'allow_overlap': 'yes'}); self.assertEqual(out, {}); self.assertEqual(len(notes), 5)
        out, _ = clean_placement({'facing': 135}); self.assertEqual(out['facing'], 135.0)
        p = validate_plan({'title': 't', 'theme': 'x', 'used_floors': ['ground'], 'fixtures': {'floor': 'a', 'wall': 'b', 'light': 'c'},
                           'zones': [{'name': 'a', 'region': 'Northwest', 'items': [{'role': 'architecture', 'query': 'screen', 'count': 6, 'facing': 'alternate', 'arrangement': 'line'}]}]}, vocab_keys=DIRECTED_VOCAB, max_items=100)
        self.assertEqual(p['zones'][0]['items'][0]['placement'], {'facing': 'alternate', 'arrangement': 'line'}); self.assertEqual(p['zones'][0]['region'], 'northwest')


def grp(zone, role, item_id, g, count=1, **spec):
    return directed_entry(zone, role, item_id, g, count=count, placement=spec)


class GroupPlacementTests(unittest.TestCase):
    def test_flank_places_symmetric_pieces_on_both_sides_with_the_anchor_orientation(self):
        res = [grp(0, 'storage', 1, directed_geometry('Bookshelf', 2.0, 0.6, 3.0), group='wall', arrangement='wall_row', wall='W'),
               grp(0, 'decor', 2, directed_geometry('Planter', 0.6, 0.6, 1.2, 'Furniture/Table'), count=2, group='wall', relation='flank')]
        scene = place_directed(res); a = Polygon(scene.placements[0]['footprint_poly']).centroid
        ps = [Polygon(p['footprint_poly']).centroid for p in scene.placements[1:]]
        self.assertEqual(len(ps), 2); self.assertTrue(all('flank' in p['note'] for p in scene.placements[1:]))
        ys = sorted(p.y - a.y for p in ps); self.assertLess(ys[0], -0.8); self.assertGreater(ys[1], 0.8); self.assertAlmostEqual(ys[0], -ys[1], delta=0.3)   # mirrored about the anchor
        self.assertEqual({round(p['yaw_degrees']) for p in scene.placements}, {round(scene.placements[0]['yaw_degrees'])})

    def test_on_top_uses_the_anchors_support_surfaces_by_height(self):
        shelf = directed_geometry('Shelf', 1.6, 0.4, 1.8, supports_top=True, top_z_local=1.8)
        shelf['surfaces'] = [{'z': 0.4, 'min_x': -.8, 'min_y': -.2, 'max_x': .8, 'max_y': .2}, {'z': 0.9, 'min_x': -.8, 'min_y': -.2, 'max_x': .8, 'max_y': .2}, {'z': 1.8, 'min_x': -.8, 'min_y': -.2, 'max_x': .8, 'max_y': .2}]
        res = [grp(0, 'storage', 1, shelf, group='s'), grp(0, 'decor', 2, directed_geometry('Book', 0.2, 0.15, 0.2, 'Item/Misc', small=True), count=3, group='s', relation='on_top')]
        scene = place_directed(res); tops = [p for p in scene.placements if p['layer'] == 'top']
        self.assertEqual(len(tops), 3); self.assertEqual(sorted(round(p['location_m'][2], 2) for p in tops), [0.4, 0.9, 1.8])   # one per board

    def test_above_hangs_a_wall_item_over_the_anchor_on_its_wall(self):
        res = [grp(0, 'storage', 1, directed_geometry('Cabinet', 1.4, 0.5, 1.0), group='c', arrangement='wall_row', wall='W'),
               grp(0, 'wall-art', 2, directed_geometry('Scroll', 0.8, 0.05, 1.5, 'Furniture/Wall-Mounted', ptype='wall', mount_bottom_z=1.3), group='c', relation='above')]
        scene = place_directed(res); a = Polygon(scene.placements[0]['footprint_poly']).centroid; w = Polygon(scene.placements[1]['footprint_poly']).centroid
        self.assertEqual(scene.placements[1]['layer'], 'wall'); self.assertAlmostEqual(w.y, a.y, delta=0.4)

    def test_front_faces_the_anchor_and_missing_anchor_falls_back_instead_of_dropping(self):
        res = [grp(0, 'storage', 1, directed_geometry('Desk', 1.4, 0.7, 0.8), group='d', arrangement='wall_row', wall='W'), grp(0, 'seating', 2, directed_geometry('Chair', 0.5, 0.5, 0.9, 'Furniture/Chair'), group='d', relation='front')]
        scene = place_directed(res); a, c = scene.placements
        self.assertLess(abs(P.wrap((c['front_deg'] + c['yaw_degrees']) - (a['front_deg'] + a['yaw_degrees'] + 180))), 1.0)
        scene = place_directed([grp(0, 'decor', 3, directed_geometry('Vase', .3, .3, .5, 'Furniture/Table'), group='nobody', relation='flank')]); self.assertEqual(len(scene.placements), 1)

    def test_schema_accepts_group_fields_and_drops_bad_ones(self):
        out, notes = clean_placement({'group': 'tea', 'relation': 'Flank', 'gap_m': 0.1}); self.assertEqual(out, {'group': 'tea', 'relation': 'flank', 'gap_m': 0.1})
        out, notes = clean_placement({'group': '', 'relation': 'beside', 'gap_m': 'x'}); self.assertEqual(out, {}); self.assertEqual(len(notes), 3)


CONCEPT_VOCAB = {'color:red'}


FACTS = {'house_size': 'Medium', 'ground_floor_area_m2': 335.7, 'free_area_after_stairs_m2': 250.0, 'stairs_keepout_area_m2': 85.0, 'bounding_box_m': [24.0, 16.0],
         'ceiling_height_m': 6.5, 'floor_shape': 'L', 'game_cap_instances_for_whole_house': 450}


CONCEPT = {'title': 'T', 'theme': 'Th', 'style_keywords': ['wa'], 'palette': ['brown'], 'mood': 'calm', 'density_intent': 'rich', 'density_reason': 'showcase', 'target_instances_estimate': 120,
           'focal_points': ['tea alcove'], 'lighting_plan': 'many small lamps', 'architecture_ideas': ['lattice partition'],
           'fixtures': {'floor': 'dark wood floor', 'wall': 'cream plaster', 'light': 'paper lantern'},
           'zones': [{'name': 'Tea alcove', 'purpose': 'tea', 'character': 'intimate', 'area_fraction': 2, 'adjacent_to': ['Library'], 'is_focal': True},
                     {'name': 'Library', 'purpose': 'reading', 'character': 'quiet', 'area_fraction': 1, 'adjacent_to': [], 'is_focal': False}]}


def fake_agy(replies):
    seen = []
    def call(prompt, *, model=None, timeout=420, workdir=None, name='prompt'):
        seen.append((name, prompt)); text = replies(name, prompt)
        return json.dumps({'response': json.dumps(text) if not isinstance(text, str) else text, 'usage': {}}), ''
    call.seen = seen; return call


def zone_items(name, prompt):
    n = 40 if 'Tea alcove' in prompt.split('Your zone:')[1][:80] else 3          # a zone with 40 entries and count 25: far above the old 8 / 6 caps
    roles = ['architecture', 'table', 'seating', 'storage', 'rug', 'decor', 'wall-art', 'lighting']
    return {'items': [{'role': roles[i % len(roles)], 'query': f'dark wood item number {i}', 'count': 25 if i == 0 else 2, 'tags': ['color:red', 'bogus:tag'], 'why': 'x'} for i in range(n)]}


class HierarchicalPlanTests(unittest.TestCase):
    def run_plan(self, items_fn=zone_items):
        agy = fake_agy(lambda name, prompt: CONCEPT if name == 'concept-prompt-attempt0' else items_fn(name, prompt))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(C, 'call_agy', agy):
            plan = C.request_hierarchical_plan('tea room', tmp, facts=FACTS, categories=['Furniture/Table'], tag_examples=['color:red'], vocab_keys=CONCEPT_VOCAB, workers=2)
            files = sorted(p.name for p in Path(tmp).iterdir())
        return plan, agy.seen, files

    def test_no_artificial_limits_and_concept_flows_down(self):
        plan, seen, files = self.run_plan()
        self.assertEqual(len(plan['zones'][0]['items']), 40)                       # old cap: 8 entries per zone
        self.assertGreater(plan['planned_instances'], 100)                         # old default cap: 40 instances
        self.assertIn('architecture', {i['role'] for z in plan['zones'] for i in z['items']})
        self.assertIn('concept', plan); self.assertEqual(plan['concept']['density_intent'], 'rich')
        zone_prompts = [p for n, p in seen if n.startswith('zone')]; self.assertEqual(len(zone_prompts), 2)
        for p in zone_prompts: self.assertIn('Overall direction', p); self.assertIn('lattice partition', p); self.assertIn('450', p)   # the game cap is stated as a fact
        self.assertTrue(any(f.startswith('zone00-response') for f in files) and any(f.startswith('concept-response') for f in files))   # counted by the quota tool
        self.assertAlmostEqual(sum(z['area_fraction'] for z in plan['zones']), 1.0)

    def test_game_cap_is_still_enforced(self):
        def too_many(name, prompt): return {'items': [{'role': 'decor', 'query': 'vase', 'count': 300, 'why': 'x'}]}
        with self.assertRaises(RuntimeError): self.run_plan(too_many)             # 2 zones x 300 > 450: rejected, retried, then reported

    def test_bad_zone_reply_is_retried_with_feedback(self):
        calls = {'n': 0}
        def flaky(name, prompt):
            if name.startswith('zone00') :
                calls['n'] += 1
                if calls['n'] == 1: return {'items': [{'role': 'sofa-ish', 'query': 'x', 'count': 1}]}
            return zone_items(name, prompt)
        plan, seen, _ = self.run_plan(flaky); self.assertEqual(calls['n'], 2)
        retry = [p for n, p in seen if n == 'zone00-prompt-attempt1'][0]; self.assertIn('rejected', retry)


class ConceptQuerySanitizationTests(unittest.TestCase):
    def test_non_latin_words_are_removed_and_recorded_not_fatal(self):
        C.SANITIZED.clear()
        def cjk(name, prompt): return {'items': [{'role': 'lighting', 'query': 'small dark wood and washi paper floor\u884c\u706f andon lantern', 'count': 2, 'why': 'x'}]}
        plan, seen, files = HierarchicalPlanTests().run_plan(cjk)
        self.assertEqual(plan['zones'][0]['items'][0]['query'], 'small dark wood and washi paper floor andon lantern')
        self.assertTrue(plan['sanitized_queries'] and 'original' in plan['sanitized_queries'][0])

    def test_query_with_no_english_left_is_still_an_error(self):
        with self.assertRaises(ValueError): C.clean_query('\u884c\u706f', 'z')


def resolved_entry(zone, k, n_options=24, planned=3, role='storage'):
    opts = []
    for i in range(n_options):
        g = {'name': f'item{zone}-{k}-{i}', 'category': 'Furniture/Shelf'}
        opts.append({'item_id': 100000 * zone + 1000 * k + i, 'name': g['name'], 'category': 'Furniture/Shelf', 'size_m': [3.0, 1.1, 3.4], 'placement': 'floor', 'matches_role_category': True,
                     'description': 'a tall dark wooden shelf', 'tags': ['form:shelving unit'], 'similarity': 0.9 - i * 0.001, 'geometry': g})
    return {'zone_index': zone, 'zone': f'z{zone}', 'role': role, 'query': 'tall dark wood bookshelf', 'count': planned, 'item_id': opts[0]['item_id'], 'geometry': opts[0]['geometry'], 'similarity': .9, 'options': opts}


class RerankPickTests(unittest.TestCase):
    def test_model_can_pick_several_distinct_candidates_with_own_counts(self):
        res = [resolved_entry(0, 0, planned=3)]
        kept, rep = RR.apply_picks(res, [{'entry': 0, 'picks': [{'i': 4, 'count': 2}, {'i': 9, 'count': 1}, {'i': 17, 'count': 3}], 'why': 'varied wall'}])
        self.assertEqual([(k['geometry']['name'], k['count']) for k in kept], [('item0-0-4', 2), ('item0-0-9', 1), ('item0-0-17', 3)])   # 3 different shelves, total 6 > planned 3: the model decides
        self.assertEqual(rep[0]['distinct'], 3); self.assertEqual(rep[0]['total'], 6)

    def test_none_and_legacy_single_pick_still_work_and_bad_replies_are_rejected(self):
        res = [resolved_entry(0, 0), resolved_entry(0, 1)]
        kept, rep = RR.apply_picks(res, [{'entry': 0, 'picks': [], 'why': 'nothing fits'}, {'entry': 1, 'pick': 5, 'why': 'legacy'}])
        self.assertEqual(len(kept), 1); self.assertEqual(kept[0]['count'], 3); self.assertEqual(rep[0]['picks'], [])
        for bad in ([{'entry': 0, 'picks': [{'i': 99, 'count': 1}]}, {'entry': 1, 'picks': []}], [{'entry': 0, 'picks': [{'i': 1, 'count': 0}]}, {'entry': 1, 'picks': []}],
                    [{'entry': 0, 'picks': [{'i': 1, 'count': 1}, {'i': 1, 'count': 1}]}, {'entry': 1, 'picks': []}], [{'entry': 0, 'picks': []}]):
            with self.assertRaises(ValueError): RR.apply_picks(res, bad)

    def test_resolve_exposes_top24_with_rich_info_and_prompt_lists_them_all(self):
        r = resolved_entry(0, 0); p = RR.build_prompt({'title': 't', 'theme': 'x'}, [r]); self.assertEqual(p.count('"matches_role_category"'), 24); self.assertIn('size_m', p); self.assertIn('placement', p)
        self.assertIn('several different shelves', p)


class RerankBatchTests(unittest.TestCase):
    def test_batches_by_zone_keep_order_and_are_not_a_limit(self):
        resolved = [resolved_entry(zi, k, n_options=2, planned=1, role='decor') for zi in range(3) for k in range(70)]
        def reply(name, prompt):
            n = prompt.count('"entry": '); return [{'entry': i, 'picks': [{'i': 0, 'count': 1}], 'why': 'ok'} for i in range(n)]
        agy = fake_agy(lambda name, prompt: reply(name, prompt))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(RR, 'call_agy', agy):
            kept, report = RR.rerank({'title': 't', 'theme': 'x'}, resolved, tmp)
        self.assertEqual(len(kept), 210); self.assertEqual([r['item_id'] for r in kept], [r['item_id'] for r in resolved])
        self.assertEqual(len(agy.seen), 18); self.assertTrue(all(len(p) < 60000 for _, p in agy.seen))   # ceil(70/12)=6 calls per zone


def palette_color_row(hex_color):
    rgb = tuple(int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    return dict(c1_hex=hex_color, c1_frac=1., mean_h=h, mean_s=s, mean_v=v)


class PaletteTests(unittest.TestCase):
    def test_dark_brown_matches_better_than_red_or_cream(self):
        from ffxiv_furniture.design.palette import palette_names_to_hsv_ranges, color_distance
        targets = palette_names_to_hsv_ranges(['dark brown'])
        assert color_distance(palette_color_row('#49301d'), targets) < color_distance(palette_color_row('#dd2020'), targets)
        assert color_distance(palette_color_row('#49301d'), targets) < color_distance(palette_color_row('#fff5dc'), targets)

    def test_cream_and_red_targets_and_circular_hue(self):
        from ffxiv_furniture.design.palette import palette_names_to_hsv_ranges, color_distance
        for name, good, bad in [('cream', '#fff5dc', '#49301d'), ('crimson', '#d02035', '#fff5dc')]:
            targets = palette_names_to_hsv_ranges(name)
            assert color_distance(palette_color_row(good), targets) < color_distance(palette_color_row(bad), targets)
        red = palette_names_to_hsv_ranges('red')
        assert color_distance(palette_color_row('#ff0010'), red) < .05
        assert color_distance(palette_color_row('#ff1000'), red) < .05
        for name in ('dark brown', 'cream', 'warm amber', 'jade green', 'crimson', 'ivory', 'charcoal'):
            assert palette_names_to_hsv_ranges(name)
        assert color_distance({}, red) == 1
        assert color_distance({}, []) == 0

    def test_texture_summary_ignores_transparent_and_near_black(self):
        import numpy as np
        from scripts.fill_dominant_colors import summarize_textures
        pixels = np.array([[[255, 0, 0, 255]] * 6 + [[0, 255, 0, 255]] * 2 +
                           [[0, 0, 255, 0]] * 4 + [[1, 1, 1, 255]] * 4], dtype=np.uint8)
        summary = summarize_textures([pixels])
        assert summary['c1_hex'] == '#ff0000'
        assert summary['c1_frac'] == .75
        assert summary['c2_hex'] == '#00ff00'
        assert summary['c2_frac'] == .25
        assert summary['c3_hex'] is None
        assert summary['hue_name'] == 'red'
        assert summarize_textures([])['c1_hex'] is None


try:
    import numpy as np
    from shapely.geometry import Polygon, box
except ImportError:
    raise unittest.SkipTest('numpy/shapely not installed')


class DefaultDyeRenderingTests(unittest.TestCase):
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
class StairOrientationTests(unittest.TestCase):
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


class RefinementMeasureContractTests(unittest.TestCase):
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
