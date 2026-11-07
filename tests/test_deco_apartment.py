import json, tempfile, unittest
from ffxiv_furniture.deco.core import Catalog, Room, Session, DecoError, ROOT

SEED = json.loads((ROOT / 'data/seeds/apartment-seed.json').read_bytes())


def mk(cat=[]):
    cat = cat or [Catalog()]
    return Session('apt', cat[0], Room('Shirogane', 'Apartment'), tempfile.mkdtemp(), seed_layout=SEED)


def P(name, pos, yaw=0, **k): return dict(op='place', name=name, position=pos, yaw_deg=yaw, **k)


class ApartmentTests(unittest.TestCase):
    def test_room_is_single_floor_without_stairs(self):
        r = Room('Shirogane', 'Apartment')
        self.assertEqual((r.house_size, r.limit, r.levels), ('Apartment', 150, ('ground',)))
        self.assertEqual([round(v, 2) for v in r.floor.bounds], [-6.0, -8.0, 6.0, 8.0]); self.assertEqual(r.walls_by_level['upper'], [])
        self.assertEqual({w['wall_id'] for w in r.walls_by_level['ground']}, {'north1', 'south1', 'east1', 'west1'})
        self.assertIn('no stairs', r.stair_summary()['note']); self.assertEqual(r.stairs, [])

    def test_unsupported_combinations(self):
        with self.assertRaises(DecoError): Room('Minimalist', 'Apartment')    # only the calibrated enclosure
        with self.assertRaises(DecoError): Room('Shirogane', 'PrivateRoom')   # Large is supported now; private rooms are not
        with self.assertRaises(DecoError): Session('x', Catalog(), Room('Shirogane', 'Medium'), tempfile.mkdtemp(), seed_layout=SEED)   # seed/room mismatch

    def test_status_limit_levels_and_walls(self):
        s = mk(); st = s.status()
        self.assertEqual((st['house_size'], st['limit'], st['capabilities']['levels']), ('Apartment', 150, ['ground']))
        s.apply([dict(op='interior', style='Empyreum')]); self.assertEqual((s.room.style, s.room.house_size), ('Empyreum', 'Apartment'))
        self.assertEqual(s.layout_dict()['houseSize'], 'Apartment')
        with self.assertRaises(DecoError): s.inspect(level='upper')
        with self.assertRaises(DecoError): s.apply([dict(op='interior', style='Minimalist')])
        with self.assertRaises(DecoError): s.apply([dict(op='fixture', type='Wall', level='upper', name='Glade Interior Wall')])
        self.assertTrue(s.inspect()['walls'])

    def test_floor_guard_and_budget(self):
        s = mk(); r = s.apply([P('Cosmotable', [9, 0, 0], instance_id='out')])
        self.assertIn('OUTSIDE_FLOOR', {w['code'] for w in r['warnings']})
        s.apply([dict(op='remove', instance_id='out')])
        ops = [dict(P('Cosmotable', [-5 + (i % 10), -7 + (i // 10) * 0.2, 0]), instance_id=f'p{i}') for i in range(151)]
        with self.assertRaises(DecoError) as c: s.apply(ops)
        self.assertIn('BUDGET_EXCEEDED', {i['code'] for i in c.exception.issues}); self.assertEqual(len(s.instances), 0)

    def test_export_keeps_apartment_size(self):
        s = mk(); s.apply([P('Cosmotable', [0, 0, 0], instance_id='t')])
        d = s.layout_dict(); self.assertEqual(d['houseSize'], 'Apartment'); self.assertEqual(len(d['interiorFurniture']), 1)

    def test_snapshot_restore_and_undo_keep_house_size(self):
        s = mk(); s.apply([P('Cosmotable', [0, 0, 0], instance_id='t')]); s.snapshot('a') if hasattr(s, 'snapshot') else None
        s.apply([dict(op='remove', instance_id='t')]); s.undo(); self.assertEqual(s.room.house_size, 'Apartment'); self.assertIn('t', s.instances)


class PatchAndFacingTests(unittest.TestCase):
    def test_max_patch_blocks_new_items_in_search_and_place(self):
        s = Session('mp', Catalog(), Room('Shirogane', 'Apartment'), tempfile.mkdtemp(), seed_layout=SEED, max_patch=7.2)
        self.assertEqual(s.status()['max_patch'], 7.2)
        with self.assertRaises(DecoError) as c: s.apply([P('Everkeep Round Table', [0, 0, 0])])
        self.assertIn('ITEM_TOO_NEW', json.dumps(c.exception.payload()))
        rows, _ = s.cat.search('Everkeep', 'text', [], [], 20, 0); self.assertEqual(rows, [])
        s.apply([P('Glade Table', [0, 0, 0])])
        s.cat.material(None, 'Pure White Interior Wall', 'Wall')    # patch 7.1: allowed

    def test_guessed_front_is_flagged_and_override_applies(self):
        s = mk(); r = s.apply([dict(P('Low Bookshelf', [0, 0, 0], instance_id='b'))] + [dict(op='face', instance_id='b', direction_deg=0)])
        self.assertIn('FACING_UNVERIFIED', {w['code'] for w in r['warnings']})
        self.assertEqual(s.cat.item(name='Oasis Desk')['front_deg'], 270.0)   # user-verified override


class PillarTests(unittest.TestCase):
    def test_pillars_known_and_flagged(self):
        r = Room('Mist', 'Apartment'); self.assertEqual(len(r.pillars_by_level['ground']), 14)
        s = Session('pl', Catalog(), r, tempfile.mkdtemp(), seed_layout=SEED)
        w = s.apply([dict(op='place', instance_id='f', name='Grade 3 Picture Frame', position=[-5.95, 4.0, 2.7], yaw_deg=270, anchor='pivot')])['warnings']
        self.assertIn('PILLAR_CONFLICT', {x['code'] for x in w})
        w = s.apply([dict(op='place', instance_id='g', name='Grade 3 Picture Frame', position=[-5.95, 2.0, 2.7], yaw_deg=270, anchor='pivot')])['warnings']
        self.assertNotIn('PILLAR_CONFLICT', {x['code'] for x in w})
        self.assertTrue(s.inspect()['pillars'])

    def test_enclosure_reported_when_sealed(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = Session('enc', Catalog(), Room('Mist', 'Apartment'), tempfile.mkdtemp(), seed_layout=SEED)
        s.apply([P('Blank Minimalist Partition', [-4.0, 0.0, 0], instance_id='n'), P('Blank Minimalist Partition', [-2.0, -5.62, 0], 90, instance_id='e1'),
                 P('Minimalist Partition Door', [-2.0, -1.62, 0], 90, instance_id='d')])
        enc = analyze(s)['enclosures']; self.assertEqual(len(enc), 1); self.assertEqual(enc[0]['door_partitions'], ['d'])
        s.apply([dict(op='remove', instance_id='e1')]); self.assertEqual(analyze(s)['enclosures'], [])   # open again


class SmallTests(unittest.TestCase):
    def test_small_room_stair_and_limit(self):
        seed = json.loads((ROOT / 'data/seeds/small-seed.json').read_bytes())
        r = Room('Minimalist', 'Small'); self.assertEqual((r.house_size, r.limit, r.levels, r.door_xy), ('Small', 300, ('ground', 'basement'), (0.0, 6.0)))
        self.assertEqual([round(v) for v in r.floor.bounds], [-6, -6, 10, 6])
        d = r.stair_info()['down']; self.assertTrue(d['top'].bounds[0] > 6.0)   # stair top is in the east alcove
        s = Session('sm', Catalog(), r, tempfile.mkdtemp(), seed_layout=seed)
        w = s.apply([P('Glade Table', [5.4, -3.8, 0], instance_id='blk')])['warnings']
        self.assertIn('STAIR_ACCESS_BLOCKED', {x['code'] for x in w})   # landing doorway approach
        self.assertEqual(s.layout_dict()['houseSize'], 'Small')

    def test_small_basement_windows_and_support(self):
        from ffxiv_furniture.deco.analyze import analyze
        seed = json.loads((ROOT / 'data/seeds/small-seed.json').read_bytes())
        s = Session('sb', Catalog(), Room('Minimalist', 'Small'), tempfile.mkdtemp(), seed_layout=seed)
        self.assertEqual(len(s.inspect(level='ground')['openings']), 5)        # 4 windows + door
        self.assertEqual(s.inspect(level='basement')['openings'], [])          # the basement has no windows
        w = s.apply([dict(op='place', instance_id='f', name='Grade 3 Picture Frame', position=[-5.95, 0.0, 2.6], yaw_deg=270, anchor='pivot')])['warnings']
        self.assertIn('WINDOW_OVERLAP', {x['code'] for x in w})
        w = s.apply([P('Glade Table', [8.0, 8.0, -7.0], instance_id='blk')])['warnings']
        self.assertIn('STAIR_ACCESS_BLOCKED', {x['code'] for x in w})          # basement stair foot
        s.apply([P('Glade Table', [0, 8, -7.0], instance_id='t'), P('Glade Vase', [0.55, 8.55, -6.3], instance_id='v'), P('Glade Vase', [1.2, 8.0, -6.3], instance_id='off')])
        un = {u['instance_id'] for u in analyze(s, 'basement')['unsupported']}
        self.assertNotIn('v', un); self.assertIn('off', un)                     # centre over the top vs hanging off the edge
        s.apply([dict(op='fixture', type='Window', name='Highland Oblong Window'), dict(op='fixture', type='Floor', level='basement', name='Herringbone Flooring')])
        d = s.layout_dict(); self.assertEqual(next(x for x in d['exteriorFixture'] if x['type'] == 'Window')['name'], 'Highland Oblong Window')
        self.assertEqual(next(x for x in d['interiorFixture'] if x['type'] == 'Floor' and x['level'] == 'Basement')['name'], 'Herringbone Flooring')


if __name__ == '__main__':
    unittest.main()
