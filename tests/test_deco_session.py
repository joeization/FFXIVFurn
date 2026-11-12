"""Session operations, validation, history, persistence, fixtures and size-specific exports."""
import copy
import json
import math
import tempfile
import unittest
from ffxiv_furniture.deco.core import Catalog, DecoError, Room, Session
from pathlib import Path
from tests.support import P, catalog, has_seed, needs_seed, read_layout, room, seed, session

class CatalogFingerprintTests(unittest.TestCase):
    def test_same_size_restored_mtime_changes_catalog_fingerprint(self):
        import os
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'catalog.sqlite3'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE sample (value TEXT)')
            db.execute("INSERT INTO sample VALUES ('old')")
            db.commit()
            cat = Catalog(path)
            try:
                before = cat.sha(); stat = path.stat()
                db.execute("UPDATE sample SET value='new'"); db.commit()
                self.assertEqual(path.stat().st_size, stat.st_size)
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                self.assertNotEqual(cat.sha(), before)
                self.assertEqual(cat.sha(), cat.sha())
            finally:
                cat.db.close(); db.close()


class SessionOperationTests(unittest.TestCase):

    def test_bottom_center_roundtrip_asymmetric(self):
        s = session()
        for yaw in (0, 37, 90, 180, 270):
            r = s.apply([P('Hingan Floor Cabinet', [-6, -3, 0], yaw, instance_id='c')])
            bc = r['changed'][0]['bottom_center_m']
            self.assertAlmostEqual(bc[0], -6, 2)
            self.assertAlmostEqual(bc[1], -3, 2)
            self.assertAlmostEqual(bc[2], 0, 2)
            s.apply([dict(op='remove', instance_id='c')])

    def test_rotate_keeps_centre(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], 0, instance_id='a')])
        b0 = s.view(s.instances['a'])['bottom_center_m']
        s.apply([dict(op='rotate', instance_id='a', yaw_deg=123)])
        b1 = s.view(s.instances['a'])['bottom_center_m']
        self.assertTrue(all((abs(x - y) < 1e-06 for x, y in zip(b0, b1))))

    def test_outside_floor_stairs_and_hole_rejected_atomically(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='ok')])
        rev = s.revision
        with self.assertRaises(DecoError) as c:
            s.apply([P('Hingan Sofa', [3, -4, 0], instance_id='good2'), P('Hingan Sofa', [30, 0, 0]), P('Hingan Sofa', [8, 3, 0])], strict=True)
        codes = {i['code'] for i in c.exception.issues}
        self.assertIn('OUTSIDE_FLOOR', codes)
        self.assertIn('STAIR_INTERSECTION', codes)
        self.assertEqual(s.revision, rev)
        self.assertNotIn('good2', s.instances)
        with self.assertRaises(DecoError) as c:
            s.apply([P('Hingan Sofa', [-8, 5, 0])], strict=True)
        self.assertTrue(any((i['code'] in ('OUTSIDE_FLOOR', 'STAIR_INTERSECTION') for i in c.exception.issues)))

    @needs_seed('Medium')
    def test_export_keeps_only_the_newest_file_per_name(self):
        s = session()
        s.apply([P('Hingan Bench', [0, -3, 0], instance_id='a')])
        first = s.export('plan')
        other = s.export('other')
        (s.dir / 'plan-r1.json.backup').write_text('app copy', encoding='utf-8')
        s.apply([P('Hingan Bench', [2, -3, 0], instance_id='b')])
        second = s.export('plan')
        names = sorted((p.name for p in s.dir.iterdir() if p.name.startswith(('plan', 'other'))))
        rev = s.revision
        self.assertEqual(names, sorted([f'plan-r{rev}.json', f'plan-r{rev}.map.json', 'plan-r1.json.backup', 'other-r1.json', 'other-r1.map.json']))
        self.assertEqual(sorted(second['removed']), sorted([Path(first['layout']['path']).name, Path(first['instance_map']).name]))

    def test_legal_overlap_and_floating(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        s.apply([P('Hingan Sofa', [0.3, -3, 0], instance_id='b'), P('Zabuton Cushion', [0, -3, 2.0], instance_id='c')])
        self.assertEqual(len(s.instances), 3)

    def test_revision_conflict_undo_redo_snapshot_restore(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        sid = s.snapshot('one')['snapshot_id']
        with self.assertRaises(DecoError) as c:
            s.apply([dict(op='remove', instance_id='a')], expected_revision=0)
        self.assertEqual(c.exception.code, 'REVISION_CONFLICT')
        s.apply([dict(op='remove', instance_id='a')])
        self.assertEqual(len(s.instances), 0)
        s.undo()
        self.assertIn('a', s.instances)
        s.redo()
        self.assertEqual(len(s.instances), 0)
        s.restore(sid)
        self.assertIn('a', s.instances)
        r0 = s.revision
        s.undo()
        self.assertEqual(len(s.instances), 0)
        self.assertGreater(s.revision, r0)

    @needs_seed('Medium')
    def test_persistence(self):
        d = tempfile.mkdtemp()
        s = Session('p', catalog(), room(), d, seed_layout=seed('Medium') if has_seed('Medium') else None)
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        s2 = Session('p', catalog(), room(), d, seed_layout=seed('Medium') if has_seed('Medium') else None)
        self.assertEqual(s2.revision, 1)
        self.assertIn('a', s2.instances)

    def test_place_on_uses_measured_surface(self):
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -5, 0.5], instance_id='t')])
        s.apply([dict(op='place_on', instance_id='tea', name='Oriental Tea Set', target_id='t', offset_xy=[0.2, 0])])
        t, tea = (s.view(s.instances['t']), s.view(s.instances['tea']))
        self.assertAlmostEqual(tea['bottom_center_m'][2], 0.5 + 0.651, 1)
        self.assertAlmostEqual(tea['bottom_center_m'][0], 0.2, 1)

    def test_along_wall_floor_and_wall_item(self):
        s = session()
        s.apply([dict(op='place_along_wall', instance_id='sb', name='Hingan Sideboard', wall_id='south1', along_m=12.0, gap_m=0.0, facing='inward')])
        b = s.view(s.instances['sb'])['bounds_world']
        self.assertAlmostEqual(b['min'][1], -8.0, 1)
        self.assertAlmostEqual(s.view(s.instances['sb'])['facing_deg'], 90.0, 0)
        s.apply([dict(op='place_along_wall', instance_id='sc', name='Oriental Wall Scroll', wall_id='south1', along_m=12.0, height_m=3.0)])
        self.assertAlmostEqual(s.instances['sc']['pivot'][1], -8.0, 1)

    def test_face_target(self):
        s = session()
        s.apply([P('Hingan Chair', [0, -3, 0], instance_id='c'), P('Hingan Sitting Table', [0, -6, 0], instance_id='t')])
        s.apply([dict(op='face', instance_id='c', target_id='t')])
        self.assertAlmostEqual(s.view(s.instances['c'])['facing_deg'], 270.0, 0)

    def test_budget_and_unknown(self):
        s = session()
        with self.assertRaises(DecoError) as c:
            s.apply([P('No Such Item', [0, 0, 0])])
        self.assertTrue(any((i['code'] == 'UNKNOWN_ITEM' for i in c.exception.issues)))

    @needs_seed('Medium')
    def test_export_roundtrip(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], 33, instance_id='a')])
        r = s.export('x')
        raw = Path(r['layout']['path']).read_bytes()
        self.assertTrue(raw.startswith(b'\xff\xfe'))
        d = json.loads(raw)
        self.assertEqual(len(d['interiorFurniture']), 1)
        self.assertEqual(d['houseSize'], 'Medium')
        q = d['interiorFurniture'][0]['transform']['rotation']
        self.assertAlmostEqual(math.degrees(2 * math.atan2(q[2], q[3])), 33, 3)

    def test_search(self):
        rows, _ = catalog().search('tea set', 'text', [], [], 5)
        self.assertTrue(any(('Tea Set' in r['name'] for r in rows)))

class SessionAdvisoryTests(unittest.TestCase):

    def test_spatial_findings_are_warnings_by_default(self):
        s = session()
        r = s.apply([P('Hingan Sofa', [8, 3, 0], instance_id='in_stairs'), P('Hingan Sofa', [30, 0, 0], instance_id='outside'), dict(op='place', name='Oriental Wall Scroll', position=[0, -3, 3.0], yaw_deg=0, anchor='pivot', instance_id='floating')])
        codes = {w['code'] for w in r['warnings']}
        self.assertTrue({'STAIR_INTERSECTION', 'OUTSIDE_FLOOR', 'WALL_MOUNT_INVALID'} <= codes)
        self.assertEqual(len(s.instances), 3)
        self.assertTrue(all((w.get('severity') == 'advisory' for w in r['warnings'] if w['code'] in ('STAIR_INTERSECTION', 'OUTSIDE_FLOOR'))))

    def test_budget_is_still_hard(self):
        s = session()
        s.apply([P('Zabuton Cushion', [0, -3, 0]) for _ in range(450)])
        self.assertEqual(len(s.instances), 450)
        with self.assertRaises(DecoError) as c:
            s.apply([P('Zabuton Cushion', [0, -3, 0])])
        self.assertEqual(c.exception.issues[-1]['code'], 'BUDGET_EXCEEDED')

class SessionWallHostTests(unittest.TestCase):

    def test_scroll_on_partition_ok_floating_scroll_rejected(self):
        s = session()
        s.apply([P('Hingan Windowed Partition', [-4.6, -4.5, 0], 90, instance_id='wp')])
        s.apply([dict(op='place', name='Oriental Wall Scroll', position=[-4.36, -6.6, 3.0], yaw_deg=270, anchor='pivot')])
        with self.assertRaises(DecoError) as c:
            s.apply([dict(op='place', name='Oriental Wall Scroll', position=[0, -3, 3.0], yaw_deg=0, anchor='pivot')], strict=True)
        self.assertEqual(c.exception.issues[0]['code'], 'WALL_MOUNT_INVALID')

class SessionUpperFloorTests(unittest.TestCase):

    def test_upper_polygon_has_stair_opening_and_levels_are_separate(self):
        r = room()
        self.assertAlmostEqual(r.upper.area, 336, delta=2)
        self.assertFalse(r.upper.contains(__import__('shapely.geometry').geometry.Point(8, 5)))
        s = session()
        res = s.apply([P('Hingan Sofa', [-8, 5, 7.0], instance_id='up_ok')])
        self.assertFalse([w for w in res['warnings'] if w['code'] == 'OUTSIDE_FLOOR'])
        res = s.apply([P('Hingan Sofa', [8, 5, 7.0], instance_id='in_opening')])
        self.assertTrue([w for w in res['warnings'] if w['code'] == 'OUTSIDE_FLOOR'])

    def test_floor_standing_thin_panel_on_upper_floor_is_not_a_wall_item(self):
        s = session()
        res = s.apply([P('Wood Slat Partition', [0, -4, 7.0], 90, instance_id='slat_up'), P('Wood Slat Partition', [0, -4, 0.0], 90, instance_id='slat_g')])
        self.assertFalse([w for w in res['warnings'] if w['code'] == 'WALL_MOUNT_INVALID'], res['warnings'])
        res = s.apply([P('Wood Slat Partition', [5, -4, 8.5], 90, instance_id='slat_raised')])
        self.assertTrue([w for w in res['warnings'] if w['code'] == 'WALL_MOUNT_INVALID'])

    @needs_seed('Medium')
    def test_upper_fixtures_export_to_upper_slot(self):
        s = session()
        s.apply([dict(op='fixture', type='Wall', level='upper', item_id=44870), dict(op='fixture', type='Wall', item_id=7138)])
        d = s.layout_dict()
        slots = {x['level']: x['itemId'] for x in d['interiorFixture'] if x['type'] == 'Wall'}
        self.assertEqual(slots['Upper Floor'], 44870)
        self.assertEqual(slots['Ground Floor'], 7138)

    def test_inspect_surfaces_have_world_centres_matching_place_on(self):
        s = session()
        s.apply([P('Hingan Sitting Table', [-2.0, -3.0, 0], 90, instance_id='t')])
        surf = [x for x in s.inspect()['surfaces'] if x['owner_id'] == 't']
        self.assertTrue(surf)
        for x in surf:
            self.assertEqual(len(x['center_world']), 2)
            s.apply([dict(op='place_on', instance_id=f"c{x['surface_idx']}", name='Green Tea Set', target_id='t', surface_idx=x['surface_idx'], offset_xy=[0, 0])])
            b = s.view(s.instances[f"c{x['surface_idx']}"])['bounds_world']
            cx, cy = ((b['min'][0] + b['max'][0]) / 2, (b['min'][1] + b['max'][1]) / 2)
            self.assertAlmostEqual(cx, x['center_world'][0], delta=0.05)
            self.assertAlmostEqual(cy, x['center_world'][1], delta=0.05)

class SessionDyeTests(unittest.TestCase):

    @needs_seed('Medium')
    def test_dye_export_roundtrip_and_rules(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a'), P('Pine Bonsai', [2, -3, 0], instance_id='b')])
        s.apply([dict(op='dye', instance_id='a', color='Snow White')])
        self.assertEqual(s.instances['a']['color'], 'E4DFD0')
        d = s.layout_dict()
        self.assertEqual(d['interiorFurniture'][0]['properties'], {'color': 'E4DFD0FF'})
        s.apply([dict(op='dye', instance_id='a', color='#e5e0d1')])
        self.assertEqual(s.instances['a']['color'], 'E4DFD0')
        with self.assertRaises(DecoError):
            s.apply([dict(op='dye', instance_id='a', color='no such dye')])
        s.apply([dict(op='dye', instance_id='a', color=None)])
        self.assertNotIn('color', s.instances['a'])
        s2 = Session('d2', catalog(), room(), tempfile.mkdtemp(), seed_layout=seed('Medium'), from_layout=dict(seed('Medium'), interiorFurniture=[dict(s.layout_dict()['interiorFurniture'][0], properties={'color': '781A1AFF'})]))
        self.assertEqual(list(s2.instances.values())[0]['color'], '781A1A')

class SessionCeilingLightTests(unittest.TestCase):

    @needs_seed('Medium')
    def test_full_height_piece_under_ceiling_light_is_flagged(self):
        s = session()
        s.apply([dict(op='fixture', type='Light', level='ground', name='Flat Ceiling Lamp')])
        r = s.apply([P('White Partition', [0, 0, 0], 0, instance_id='through_lamp'), P('White Partition', [0, -4, 0], 0, instance_id='clear'), P('Hingan Sofa', [0, 0, 0], 0, instance_id='low_sofa')])
        ids = [w['instance_id'] for w in r['warnings'] if w['code'] == 'CEILING_LIGHT_CONFLICT']
        self.assertEqual(ids, ['through_lamp'])
        self.assertTrue(all((w['severity'] == 'advisory' for w in r['warnings'] if w['code'] == 'CEILING_LIGHT_CONFLICT')))
        r = s.apply([P('White Partition', [0, 0, 7.0], 0, instance_id='upper_through')])
        self.assertIn('upper_through', [w['instance_id'] for w in r['warnings'] if w['code'] == 'CEILING_LIGHT_CONFLICT'])

class ApartmentTests(unittest.TestCase):

    @needs_seed('Apartment')
    def test_unsupported_combinations(self):
        with self.assertRaises(DecoError):
            Room('Minimalist', 'Apartment')
        with self.assertRaises(DecoError):
            Room('Shirogane', 'PrivateRoom')
        with self.assertRaises(DecoError):
            Session('x', Catalog(), Room('Shirogane', 'Medium'), tempfile.mkdtemp(), seed_layout=seed('Apartment'))

    @needs_seed('Apartment')
    def test_status_limit_levels_and_walls(self):
        s = session('Apartment')
        st = s.status()
        self.assertEqual((st['house_size'], st['limit'], st['capabilities']['levels']), ('Apartment', 150, ['ground']))
        s.apply([dict(op='interior', style='Empyreum')])
        self.assertEqual((s.room.style, s.room.house_size), ('Empyreum', 'Apartment'))
        self.assertEqual(s.layout_dict()['houseSize'], 'Apartment')
        with self.assertRaises(DecoError):
            s.inspect(level='upper')
        with self.assertRaises(DecoError):
            s.apply([dict(op='interior', style='Minimalist')])
        with self.assertRaises(DecoError):
            s.apply([dict(op='fixture', type='Wall', level='upper', name='Glade Interior Wall')])
        self.assertTrue(s.inspect()['walls'])

    def test_floor_guard_and_budget(self):
        s = session('Apartment')
        r = s.apply([P('Cosmotable', [9, 0, 0], instance_id='out')])
        self.assertIn('OUTSIDE_FLOOR', {w['code'] for w in r['warnings']})
        s.apply([dict(op='remove', instance_id='out')])
        ops = [dict(P('Cosmotable', [-5 + i % 10, -7 + i // 10 * 0.2, 0]), instance_id=f'p{i}') for i in range(151)]
        with self.assertRaises(DecoError) as c:
            s.apply(ops)
        self.assertIn('BUDGET_EXCEEDED', {i['code'] for i in c.exception.issues})
        self.assertEqual(len(s.instances), 0)

    @needs_seed('Apartment')
    def test_export_keeps_apartment_size(self):
        s = session('Apartment')
        s.apply([P('Cosmotable', [0, 0, 0], instance_id='t')])
        d = s.layout_dict()
        self.assertEqual(d['houseSize'], 'Apartment')
        self.assertEqual(len(d['interiorFurniture']), 1)

    def test_snapshot_restore_and_undo_keep_house_size(self):
        s = session('Apartment')
        s.apply([P('Cosmotable', [0, 0, 0], instance_id='t')])
        s.snapshot('a') if hasattr(s, 'snapshot') else None
        s.apply([dict(op='remove', instance_id='t')])
        s.undo()
        self.assertEqual(s.room.house_size, 'Apartment')
        self.assertIn('t', s.instances)

class PatchAndFacingTests(unittest.TestCase):

    @needs_seed('Apartment')
    def test_max_patch_blocks_new_items_in_search_and_place(self):
        s = Session('mp', Catalog(), Room('Shirogane', 'Apartment'), tempfile.mkdtemp(), seed_layout=seed('Apartment'), max_patch=7.2)
        self.assertEqual(s.status()['max_patch'], 7.2)
        with self.assertRaises(DecoError) as c:
            s.apply([P('Everkeep Round Table', [0, 0, 0])])
        self.assertIn('ITEM_TOO_NEW', json.dumps(c.exception.payload()))
        rows, _ = s.cat.search('Everkeep', 'text', [], [], 20, 0)
        self.assertEqual(rows, [])
        s.apply([P('Glade Table', [0, 0, 0])])
        s.cat.material(None, 'Pure White Interior Wall', 'Wall')

    def test_guessed_front_is_flagged_and_override_applies(self):
        s = session('Apartment')
        r = s.apply([dict(P('Low Bookshelf', [0, 0, 0], instance_id='b'))] + [dict(op='face', instance_id='b', direction_deg=0)])
        self.assertIn('FACING_UNVERIFIED', {w['code'] for w in r['warnings']})
        self.assertEqual(s.cat.item(name='Oasis Desk')['front_deg'], 270.0)

class ApartmentPillarTests(unittest.TestCase):

    def test_pillars_known_and_flagged(self):
        r = Room('Mist', 'Apartment')
        self.assertEqual(len(r.pillars_by_level['ground']), 14)
        s = session('Apartment', style='Mist')
        w = s.apply([dict(op='place', instance_id='f', name='Grade 3 Picture Frame', position=[-5.95, 4.0, 2.7], yaw_deg=270, anchor='pivot')])['warnings']
        self.assertIn('PILLAR_CONFLICT', {x['code'] for x in w})
        w = s.apply([dict(op='place', instance_id='g', name='Grade 3 Picture Frame', position=[-5.95, 2.0, 2.7], yaw_deg=270, anchor='pivot')])['warnings']
        self.assertNotIn('PILLAR_CONFLICT', {x['code'] for x in w})
        self.assertTrue(s.inspect()['pillars'])

class SmallSessionTests(unittest.TestCase):

    @needs_seed('Small')
    def test_small_room_stair_and_limit(self):
        layout = seed('Small')
        r = Room('Minimalist', 'Small')
        self.assertEqual((r.house_size, r.limit, r.levels, r.door_xy), ('Small', 300, ('ground', 'basement'), (0.0, 6.0)))
        self.assertEqual([round(v) for v in r.floor.bounds], [-6, -6, 10, 6])
        d = r.stair_info()['down']
        self.assertTrue(d['top'].bounds[0] > 6.0)
        s = Session('sm', Catalog(), r, tempfile.mkdtemp(), seed_layout=layout)
        w = s.apply([P('Glade Table', [5.4, -3.8, 0], instance_id='blk')])['warnings']
        self.assertIn('STAIR_ACCESS_BLOCKED', {x['code'] for x in w})
        self.assertEqual(s.layout_dict()['houseSize'], 'Small')

    @needs_seed('Small')
    def test_small_basement_windows_and_support(self):
        from ffxiv_furniture.deco.analyze import analyze
        layout = seed('Small')
        s = Session('sb', Catalog(), Room('Minimalist', 'Small'), tempfile.mkdtemp(), seed_layout=layout)
        self.assertEqual(len(s.inspect(level='ground')['openings']), 5)
        self.assertEqual(s.inspect(level='basement')['openings'], [])
        w = s.apply([dict(op='place', instance_id='f', name='Grade 3 Picture Frame', position=[-5.95, 0.0, 2.6], yaw_deg=270, anchor='pivot')])['warnings']
        self.assertIn('WINDOW_OVERLAP', {x['code'] for x in w})
        w = s.apply([P('Glade Table', [8.0, 8.0, -7.0], instance_id='blk')])['warnings']
        self.assertIn('STAIR_ACCESS_BLOCKED', {x['code'] for x in w})
        s.apply([P('Glade Table', [0, 8, -7.0], instance_id='t'), P('Glade Vase', [0.55, 8.55, -6.3], instance_id='v'), P('Glade Vase', [1.2, 8.0, -6.3], instance_id='off')])
        un = {u['instance_id'] for u in analyze(s, 'basement')['unsupported']}
        self.assertNotIn('v', un)
        self.assertIn('off', un)
        s.apply([dict(op='fixture', type='Window', name='Highland Oblong Window'), dict(op='fixture', type='Floor', level='basement', name='Herringbone Flooring')])
        d = s.layout_dict()
        self.assertEqual(next((x for x in d['exteriorFixture'] if x['type'] == 'Window'))['name'], 'Highland Oblong Window')
        self.assertEqual(next((x for x in d['interiorFixture'] if x['type'] == 'Floor' and x['level'] == 'Basement'))['name'], 'Herringbone Flooring')

def rejected(test, s, ops, **kw):
    rev, n = (s.revision, len(s.instances))
    with test.assertRaises(DecoError) as c:
        s.apply(ops, **kw)
    test.assertEqual((s.revision, len(s.instances)), (rev, n))
    return c.exception

class SessionInputTests(unittest.TestCase):

    def _lights(self, s):
        return {l['name']: l['item_id'] for l in s.cat.search_materials('', 'light', 60) if l['renderable']}

    def _over_cap(self):
        f = catalog().item(name='Hingan Sofa')
        lay = {**seed('Medium'), 'interiorFurniture': [dict(itemId=f['id'], name=f['name'], transform=dict(location=[0, -300, 0], rotation=[0, 0, 0, 1], scale=[1, 1, 1]), properties={}, attachments=[]) for _ in range(455)]}
        return Session('big', catalog(), room(), tempfile.mkdtemp(), from_layout=lay)

    def test_removed_excludes_recreated_ids(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a'), P('Hingan Bench', [3, -3, 0], instance_id='b')])
        r = s.apply([dict(op='remove', instance_id='a'), P('Hingan Sofa', [0, -3, 0], instance_id='a'), dict(op='remove', instance_id='b')])
        self.assertEqual(r['removed'], ['b'])
        self.assertIn('a', s.instances)

    def test_malformed_ops_are_bad_input_with_op_index(self):
        s = session()
        e = rejected(self, s, [P('Hingan Sofa', [0, -3, 0], instance_id='a'), 'x'])
        self.assertEqual(e.code, 'REJECTED')
        self.assertEqual((e.issues[0]['code'], e.issues[0]['op_index']), ('BAD_INPUT', 1))
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        for bad in ([1], {'k': 1}, 5):
            for op in (dict(op='remove', instance_id=bad), dict(op='move', instance_id=bad, delta=[1, 0, 0]), dict(op='rotate', instance_id=bad, yaw_deg=1), P('Hingan Sofa', [0, -3, 0], instance_id=bad)):
                e = rejected(self, s, [op])
                self.assertEqual((e.issues[0]['code'], e.issues[0]['op_index']), ('BAD_INPUT', 0), op)

    def test_unknown_keys_and_missing_position_are_rejected(self):
        s = session()
        e = rejected(self, s, [dict(op='place', name='Hingan Sofa', instance_id='a')])
        self.assertEqual(e.issues[0]['code'], 'BAD_INPUT')
        self.assertIn('position', e.issues[0]['message'])
        e = rejected(self, s, [dict(op='place', name='Hingan Sofa', psotion=[0, -3, 0], position=[0, -3, 0])])
        i = e.issues[0]
        self.assertEqual(i['code'], 'BAD_INPUT')
        self.assertIn('psotion', i['message'])
        self.assertIn('position', i['message'])
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        e = rejected(self, s, [dict(op='move', instance_id='a', delat=[1, 0, 0])])
        self.assertIn('delat', e.issues[0]['message'])

    def test_move_and_rotate_need_exactly_one_form(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        for op in (dict(op='move', instance_id='a'), dict(op='move', instance_id='a', position=[1, -3, 0], delta=[1, 0, 0]), dict(op='rotate', instance_id='a'), dict(op='rotate', instance_id='a', yaw_deg=10, yaw_delta_deg=5)):
            self.assertEqual(rejected(self, s, [op]).issues[0]['code'], 'BAD_INPUT', op)

    def test_existing_instance_with_other_item_rejected(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        e = rejected(self, s, [P('Hingan Bench', [0, -3, 0], instance_id='a')])
        self.assertEqual(e.issues[0]['code'], 'BAD_INPUT')
        it = s.cat.item(name='Hingan Sofa')
        s.apply([P('Hingan Sofa', [1, -3, 0], instance_id='a')])
        s.apply([dict(op='place', item_id=it['id'], position=[2, -3, 0], instance_id='a')])

    @needs_seed('Medium')
    def test_validate_uses_pending_fixtures(self):
        s = session()
        lights = self._lights(s)
        big = 'Star Chandelier'
        if big not in lights:
            self.skipTest('Star Chandelier mesh not extracted')
        committed = s._ceiling_light_disc('ground')
        if committed is None or committed[0] > 0.8:
            self.skipTest('seed light unexpectedly large')
        r = s.apply([dict(op='fixture', type='Light', name=big), P('Zabuton Cushion', [1.6, 0, 4.0], instance_id='z')])
        self.assertIn('CEILING_LIGHT_CONFLICT', {w['code'] for w in r['warnings']})
        s2 = session()
        r2 = s2.apply([P('Zabuton Cushion', [1.6, 0, 4.0], instance_id='z')])
        self.assertNotIn('CEILING_LIGHT_CONFLICT', {w['code'] for w in r2['warnings']})

    @needs_seed('Medium')
    def test_restore_validates_snapshot_fixtures(self):
        s = session()
        big = 'Star Chandelier'
        if big not in self._lights(s):
            self.skipTest('Star Chandelier mesh not extracted')
        s.apply([dict(op='fixture', type='Light', name=big), P('Zabuton Cushion', [1.6, 0, 4.0], instance_id='z')])
        sid = s.snapshot('x')['snapshot_id']
        s.apply([dict(op='fixture', type='Light', name='Oasis Pendant Lamp')])
        seen = []
        orig = s.validate

        def spy(inst, issues, op_index=None):
            n0 = len(issues)
            orig(inst, issues, op_index)
            seen.extend((i['code'] for i in issues[n0:]))
        s.validate = spy
        s.restore(sid)
        self.assertIn('CEILING_LIGHT_CONFLICT', seen)
        self.assertEqual(s.fixtures['Light']['name'], big)

    def test_light_mesh_resolved_via_asset_key(self):
        s = session()
        lights = self._lights(s)
        for nm in ('Flame Ceiling Fan & Lamp', 'Serpent Ceiling Fan & Lamp', "Watcher's Palace Ceiling Lamp"):
            if nm not in lights:
                continue
            s.fixtures = {'Light': dict(item_id=lights[nm], name=nm)}
            d = s._ceiling_light_disc('ground')
            self.assertIsNotNone(d, nm)
            self.assertGreater(d[0], 0.1)

    def test_missing_mesh_is_unreadable_not_crash(self):
        s = session()
        s.fixtures = {'Light': dict(item_id=-12345, name='No Such Lamp')}
        self.assertIsNone(s._ceiling_light_disc('ground'))

    @needs_seed('Medium')
    def test_over_cap_session_only_rejects_growth(self):
        s = self._over_cap()
        self.assertEqual(len(s.instances), 455)
        m = next((i for i in rejected(self, s, [P('Hingan Sofa', [0, -3, 0])]).issues if i['code'] == 'BUDGET_EXCEEDED'))['message']
        self.assertIn('remove 6', m)
        s.apply([dict(op='dye', instance_id='i1', color='default')])
        self.assertEqual(s.apply([dict(op='remove', instance_id='i1')])['count'], 454)
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='n'), dict(op='remove', instance_id='i2'), dict(op='remove', instance_id='i3')])

    def test_inspect_level_filters_instances_and_surfaces(self):
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='g'), P('Hingan Sitting Table', [0, -5, 7.0], instance_id='u')])
        if 'upper' not in s.room.levels:
            self.skipTest('no upper')
        g = s.inspect(level='ground')
        u = s.inspect(level='upper')
        self.assertEqual([v['instance_id'] for v in g['instances']], ['g'])
        self.assertEqual([v['instance_id'] for v in u['instances']], ['u'])
        self.assertTrue(g['surfaces'] and {x['owner_id'] for x in g['surfaces']} == {'g'})
        self.assertEqual({x['owner_id'] for x in u['surfaces']}, {'u'})
        self.assertEqual((g['used'], u['used']), (2, 2))

    def test_rotate_invalid_anchor(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        self.assertEqual(rejected(self, s, [dict(op='rotate', instance_id='a', yaw_deg=10, anchor='zzz')]).issues[0]['code'], 'BAD_INPUT')

    def test_search_limits_clamped(self):
        c = catalog()
        for lim in (-5, 0):
            self.assertEqual(len(c.search_materials('', 'wall', limit=lim)), 1)
            self.assertEqual(len(c.search_dyes('', limit=lim)), 1)
        self.assertLessEqual(len(c.search_materials('', 'wall', limit=10000)), 60)
        self.assertLessEqual(len(c.search_dyes('', limit=10000)), 60)

    def test_place_on_and_face_reject_self_target(self):
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t')])
        for op in (dict(op='place_on', instance_id='t', target_id='t'), dict(op='face', instance_id='t', target_id='t')):
            self.assertEqual(rejected(self, s, [op]).issues[0]['code'], 'BAD_INPUT')

    def test_ids_never_reused_after_undo_restore_and_reload(self):
        s = session()
        a = s.apply([P('Hingan Sofa', [0, -3, 0])])['changed'][0]['instance_id']
        s.undo()
        self.assertNotEqual(s.apply([P('Hingan Bench', [0, -3, 0])])['changed'][0]['instance_id'], a)
        s = session()
        sid = s.snapshot('empty')['snapshot_id']
        used = set()
        for x in (0, 2, 4):
            used.add(s.apply([P('Hingan Bench', [x, -3, 0])])['changed'][0]['instance_id'])
        s.restore(sid)
        self.assertEqual(len(s.instances), 0)
        n = s.apply([P('Hingan Sofa', [0, -3, 0])])['changed'][0]['instance_id']
        self.assertNotIn(n, used)
        s2 = Session('t', catalog(), room(), str(s.dir.parent), seed_layout=s.seed)
        s2.undo()
        s2.undo()
        self.assertNotIn(s2.apply([P('Hingan Sofa', [0, -3, 0])])['changed'][0]['instance_id'], used | {n})

    def test_old_state_file_without_counter_loads(self):
        s = session()
        s.apply([P('Hingan Sofa', [0, -3, 0])])
        p = s.dir / 'state.json'
        d = read_layout(p)
        d.pop('id_floor', None)
        p.write_text(json.dumps(d), encoding='utf-8')
        s2 = Session('t', catalog(), room(), str(s.dir.parent), seed_layout=s.seed)
        self.assertEqual(len(s2.instances), 1)
        self.assertTrue(s2.apply([P('Hingan Bench', [2, -3, 0])])['ok'])

class SessionStyleTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cat = catalog()

    def session(self):
        return Session('test', self.cat, room(), self.tmp.name, seed_layout=seed('Medium') if has_seed('Medium') else None)

    def test_style_switch_preserves_furniture_undo_redo_snapshot(self):
        s = self.session()
        s.apply([dict(op='place', name='Hingan Chair', position=[0, -4, 0], yaw_deg=37, instance_id='chair')])
        before = copy.deepcopy(s.instances)
        snap = s.snapshot('original')['snapshot_id']
        s.apply([dict(op='interior', style='Minimalist')])
        self.assertEqual(s.instances, before)
        self.assertEqual(s.room.style, 'Minimalist')
        s.undo()
        self.assertEqual(s.room.style, 'Shirogane')
        s.redo()
        self.assertEqual(s.room.style, 'Minimalist')
        s.restore(snap)
        self.assertEqual(s.room.style, 'Shirogane')
        self.assertEqual(s.instances, before)

    @needs_seed('Medium')
    def test_style_persistence_and_export_district(self):
        s = self.session()
        s.apply([dict(op='interior', style='DarkMinimalist')])
        s2 = Session('test', self.cat, Room('Mist'), self.tmp.name, seed_layout=s.seed)
        self.assertEqual(s2.room.style, 'DarkMinimalist')
        result = s2.export('changed')
        back = read_layout(Path(result['layout']['path']))
        self.assertEqual(next((f['name'] for f in back['interiorFixture'] if f['type'] == 'District')), 'Dark Minimalist')
        self.assertEqual(next((f['name'] for f in s2.layout_dict()['interiorFixture'] if f['type'] == 'District')), 'Dark Minimalist')
        self.assertEqual(next((f['name'] for f in seed('Medium')['interiorFixture'] if f['type'] == 'District')), 'Shirogane')

    def test_rejected_batch_does_not_change_style_or_geometry(self):
        s = self.session()
        before = s.state_hash()
        rev = s.revision
        with self.assertRaises(DecoError):
            s.apply([dict(op='interior', style='Minimalist'), dict(op='place', name='No Such Item', position=[0, 0, 0])])
        self.assertEqual(s.room.style, 'Shirogane')
        self.assertEqual(s.state_hash(), before)
        self.assertEqual(s.revision, rev)
        with self.assertRaises(DecoError):
            s.apply([dict(op='interior', style='Typo')])
        self.assertEqual(s.state_hash(), before)

    def test_upper_wall_helpers_have_upper_geometry_and_relative_height(self):
        s = self.session()
        s.apply([dict(op='interior', style='Minimalist')])
        info = s.inspect(level='upper')
        self.assertEqual(info['level'], 'upper')
        self.assertEqual(info['style'], 'Minimalist')
        w = next((w for w in info['walls'] if w['length'] > 8))
        s.apply([dict(op='place_along_wall', name='Oriental Wall Scroll', instance_id='scroll', level='upper', wall_id=w['wall_id'], along_m=w['length'] / 2, height_m=2)])
        self.assertEqual(s.instances['scroll']['pivot'][2], 9)
        self.assertEqual(s.inspect(level='basement')['level'], 'basement')
        with self.assertRaises(DecoError):
            s.inspect(level='attic')

    @needs_seed('Medium')
    def test_legacy_state_without_style_uses_original_seed(self):
        s = self.session()
        raw = read_layout(s.dir / 'state.json')
        raw['state'].pop('style')
        (s.dir / 'state.json').write_text(json.dumps(raw), encoding='utf-8')
        s2 = Session('test', self.cat, Room('Minimalist'), self.tmp.name, seed_layout=s.seed)
        self.assertEqual(s2.room.style, 'Shirogane')
