import unittest
try:
    from shapely.geometry import Polygon, box
except ImportError:  # optional render/design dependency
    raise unittest.SkipTest('shapely not installed')
import json as _json, math, struct as _struct
from pathlib import Path as _P
from ffxiv_furniture.design.plan import validate_plan
from ffxiv_furniture.design import place as P

_ROOT = _P(__file__).resolve().parents[1]
L_SHAPE = Polygon([(0, 0), (12, 0), (12, 8), (4, 8), (4, 4), (0, 4)])  # notch x0..4, y4..8 is NOT floor
ROOM = {'polygon': L_SHAPE, 'ceiling_z': 6.5, 'corridor': None}
VOCAB = {'color:red', 'material:wood-like appearance'}


def geo(name, w, d, h, category, z0=0.0, **info):
    g = {'name': name, 'length': w, 'width': d, 'height': h, 'category': category, 'lo': [-w / 2, -d / 2, z0], 'hi': [w / 2, d / 2, z0 + h]}
    g.update(info); return g


def entry(zone, role, item_id, g, count=1):
    return {'zone_index': zone, 'zone': f'z{zone}', 'area_fraction': 0.5, 'role': role, 'count': count, 'query': 'q', 'item_id': item_id, 'geometry': g}


def plan(**kw):
    p = {'title': 't', 'theme': 'th', 'used_floors': ['ground'], 'fixtures': {'floor': 'a', 'wall': 'b', 'light': 'c'},
         'zones': [{'name': 'a', 'area_fraction': 1, 'items': [{'role': 'seating', 'query': 'red chair', 'count': 2, 'tags': ['color:red', 'bogus:tag']}]}]}
    p.update(kw); return p


class PlanTests(unittest.TestCase):
    def test_valid_and_unknown_tags_dropped_not_invented(self):
        out = validate_plan(plan(), vocab_keys=VOCAB, max_items=10)
        self.assertEqual(out['zones'][0]['items'][0]['tags'], ['color:red']); self.assertEqual(out['dropped_tags'], ['bogus:tag'])
        self.assertEqual(out['planned_instances'], 2)

    def test_rejections(self):
        for bad in (plan(used_floors=['ground', 'upper']), plan(fixtures={'floor': 'a'}), plan(zones=[]),
                    plan(zones=[{'name': 'a', 'items': [{'role': 'seating', 'query': '紅色椅子', 'count': 1}]}]),
                    plan(zones=[{'name': 'a', 'items': [{'role': 'sofa-ish', 'query': 'x', 'count': 1}]}]),
                    plan(zones=[{'name': 'a', 'items': [{'role': 'seating', 'query': 'x', 'count': 0}]}])):
            with self.assertRaises(ValueError): validate_plan(bad, vocab_keys=VOCAB, max_items=10)
        with self.assertRaises(ValueError): validate_plan(plan(), vocab_keys=VOCAB, max_items=1)  # budget


class PlacementTests(unittest.TestCase):
    def test_split_regions_conserve_area(self):
        regions = P.split_regions(L_SHAPE, [1, 1]); self.assertAlmostEqual(sum(r.area for r in regions), L_SHAPE.area, 3)
        self.assertAlmostEqual(regions[0].area, L_SHAPE.area / 2, delta=1.0)

    def make(self):
        res = [entry(0, 'rug', 1, geo('Rug', 3, 3, 0.02, 'Furniture/Rug', ptype='rug')), entry(0, 'table', 2, geo('Table', 1.6, 0.9, 0.7, 'Furniture/Table', ptype='floor', supports_top=True, top_z_local=0.7)),
               entry(0, 'seating', 3, geo('Chair', 0.5, 0.5, 0.9, 'Furniture/Chair', ptype='floor'), 4), entry(0, 'storage', 4, geo('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf', ptype='floor'), 2),
               entry(1, 'wall-art', 5, geo('Scroll', 1.0, 0.03, 4.1, 'Item/Printed', z0=-2.05, ptype='wall', mount_bottom_z=0.05), 2), entry(1, 'lighting', 6, geo('Lantern', 0.3, 0.3, 1.5, 'Lighting', ptype='floor')),
               entry(1, 'decor', 7, geo('Vase', 0.3, 0.3, 0.4, 'Item/Others', ptype='floor'), 2)]
        return P.place_all(ROOM, res)

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
        res = [entry(0, 'rug', 1, geo('Rug', 3, 3, 0.02, 'Furniture/Rug', ptype='rug')), entry(0, 'table', 2, geo('Table', 1.6, 0.9, 0.7, 'Furniture/Table', ptype='floor')),
               entry(0, 'seating', 3, geo('Chair', 0.5, 0.5, 0.9, 'Furniture/Chair', ptype='floor'), 4), entry(0, 'storage', 4, geo('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf', ptype='floor'), 6),
               entry(0, 'wall-art', 5, geo('Scroll', 1.0, 0.03, 2.0, 'Item/Printed', ptype='wall', mount_bottom_z=1.0), 4)]
        scene, rep = P.place_all(room, res)
        self.assertGreater(len(scene.placements), 8)
        for pl in scene.placements: self.assertFalse(Polygon(pl['footprint_poly']).intersects(keep), pl)
        self.assertLessEqual(max(r[2] for r in rep['regions'].values()), 6.0 + 1e-6)

    @unittest.skipUnless((_ROOT / 'data/house-legacy/MakePlace/Content/Maps/XIVMediumHouse.uexp').exists() and (_ROOT / 'outputs/house-layouts/native-map-tables.json').exists(), 'native map absent')
    def test_decoded_medium_stair_transforms(self):
        d = (_ROOT / 'data/house-legacy/MakePlace/Content/Maps/XIVMediumHouse.uexp').read_bytes()
        ex = {e['name']: e for e in _json.loads((_ROOT / 'outputs/house-layouts/native-map-tables.json').read_text(encoding='utf-8'))['Medium']['exports']}
        def tf(n):
            e = ex[n]; b = d[e['serial_offset_in_uexp']:e['serial_offset_in_uexp'] + e['serial_size']]
            qx, qy, qz, qw, tx, ty, tz, sx, sy, sz = _struct.unpack_from('<10d', b, 35); return (round(qz, 4), round(qw, 4), tx, ty, tz, sx, sy, sz)
        self.assertEqual(tf('Stairs'), (0.7071, 0.7071, 700.0, 400.0, 0.0, -1.0, 1.0, 1.0))
        self.assertEqual(tf('Stairs2_9'), (1.0, 0.0, -800.0, 300.0, -700.0, -1.0, 1.0, 1.0))
        self.assertEqual(tf('Railing2_2')[2:5], (-800.0, 500.0, 0.0))

    @unittest.skipUnless((_ROOT / 'outputs/house-layouts/medium-stair-transforms.json').exists(), 'decoded stairs absent')
    def test_keepouts_per_floor_exist_and_match_stair_positions(self):
        from ffxiv_furniture.house_profiles import room_keepouts
        g, u, b = (room_keepouts(_ROOT, 'Medium', f) for f in ('ground', 'upper', 'basement'))
        self.assertEqual((len(g), len(u), len(b)), (2, 1, 1))
        self.assertTrue(u[0].centroid.x > 0 and b[0].centroid.x < 0)
        self.assertEqual(room_keepouts(_ROOT, 'Large', 'ground'), [])


if __name__ == '__main__':
    unittest.main()
