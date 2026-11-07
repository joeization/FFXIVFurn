import json, math, tempfile, unittest
from pathlib import Path
from ffxiv_furniture.deco.core import Catalog, Room, Session, DecoError, ROOT

SEED = json.loads((ROOT / 'outputs/designs/hand-tea-room/final-layout.json').read_bytes())
SEED = {k: v for k, v in SEED.items() if k != 'interiorFurniture'}
_cat = None; _room = None


def mk():
    global _cat, _room
    _cat = _cat or Catalog(); _room = _room or Room()
    return Session('t', _cat, _room, tempfile.mkdtemp(), seed_layout=SEED)


def P(name, pos, yaw=0, **k): return dict(op='place', name=name, position=pos, yaw_deg=yaw, **k)


class DecoTests(unittest.TestCase):
    def test_bottom_center_roundtrip_asymmetric(self):
        s = mk()   # Hingan Floor Cabinet bounds are asymmetric in y (-0.61..0.12)
        for yaw in (0, 37, 90, 180, 270):
            r = s.apply([P('Hingan Floor Cabinet', [-6, -3, 0], yaw, instance_id='c')])
            bc = r['changed'][0]['bottom_center_m']; self.assertAlmostEqual(bc[0], -6, 2); self.assertAlmostEqual(bc[1], -3, 2); self.assertAlmostEqual(bc[2], 0, 2)
            s.apply([dict(op='remove', instance_id='c')])

    def test_rotate_keeps_centre(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], 0, instance_id='a')]); b0 = s.view(s.instances['a'])['bottom_center_m']
        s.apply([dict(op='rotate', instance_id='a', yaw_deg=123)]); b1 = s.view(s.instances['a'])['bottom_center_m']
        self.assertTrue(all(abs(x - y) < 1e-6 for x, y in zip(b0, b1)))

    def test_outside_floor_and_stairs_rejected_atomically(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='ok')]); rev = s.revision
        with self.assertRaises(DecoError) as c: s.apply([P('Hingan Sofa', [3, -4, 0], instance_id='good2'), P('Hingan Sofa', [30, 0, 0]), P('Hingan Sofa', [8, 3, 0])], strict=True)
        codes = {i['code'] for i in c.exception.issues}; self.assertIn('OUTSIDE_FLOOR', codes); self.assertIn('STAIR_INTERSECTION', codes)
        self.assertEqual(s.revision, rev); self.assertNotIn('good2', s.instances)   # nothing changed

    def test_export_keeps_only_the_newest_file_per_name(self):
        s = mk(); s.apply([P('Hingan Bench', [0, -3, 0], instance_id='a')])
        first = s.export('plan'); other = s.export('other')
        (s.dir / 'plan-r1.json.backup').write_text('app copy', encoding='utf-8')   # app-owned file, never touched
        s.apply([P('Hingan Bench', [2, -3, 0], instance_id='b')])
        second = s.export('plan')
        names = sorted(p.name for p in s.dir.iterdir() if p.name.startswith(('plan', 'other')))
        rev = s.revision
        self.assertEqual(names, sorted([f'plan-r{rev}.json', f'plan-r{rev}.map.json', 'plan-r1.json.backup', 'other-r1.json', 'other-r1.map.json']))
        self.assertEqual(sorted(second['removed']), sorted([Path(first['layout']['path']).name, Path(first['instance_map']).name]))

    def test_hole_rejected(self):
        s = mk()
        with self.assertRaises(DecoError) as c: s.apply([P('Hingan Sofa', [-8, 5, 0])], strict=True)
        self.assertTrue(any(i['code'] in ('OUTSIDE_FLOOR', 'STAIR_INTERSECTION') for i in c.exception.issues))

    def test_legal_overlap_and_floating(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')]); s.apply([P('Hingan Sofa', [0.3, -3, 0], instance_id='b'), P('Zabuton Cushion', [0, -3, 2.0], instance_id='c')])
        self.assertEqual(len(s.instances), 3)

    def test_revision_conflict_undo_redo_snapshot_restore(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')]); sid = s.snapshot('one')['snapshot_id']
        with self.assertRaises(DecoError) as c: s.apply([dict(op='remove', instance_id='a')], expected_revision=0)
        self.assertEqual(c.exception.code, 'REVISION_CONFLICT')
        s.apply([dict(op='remove', instance_id='a')]); self.assertEqual(len(s.instances), 0)
        s.undo(); self.assertIn('a', s.instances); s.redo(); self.assertEqual(len(s.instances), 0)
        s.restore(sid); self.assertIn('a', s.instances); r0 = s.revision; s.undo(); self.assertEqual(len(s.instances), 0); self.assertGreater(s.revision, r0)

    def test_persistence(self):
        d = tempfile.mkdtemp(); s = Session('p', mk().cat, _room, d, seed_layout=SEED); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        s2 = Session('p', _cat, _room, d, seed_layout=SEED); self.assertEqual(s2.revision, 1); self.assertIn('a', s2.instances)

    def test_place_on_uses_measured_surface(self):
        s = mk(); s.apply([P('Hingan Sitting Table', [0, -5, 0.5], instance_id='t')])
        s.apply([dict(op='place_on', instance_id='tea', name='Oriental Tea Set', target_id='t', offset_xy=[0.2, 0])])
        t, tea = s.view(s.instances['t']), s.view(s.instances['tea']); self.assertAlmostEqual(tea['bottom_center_m'][2], 0.5 + 0.651, 1); self.assertAlmostEqual(tea['bottom_center_m'][0], 0.2, 1)

    def test_along_wall_floor_and_wall_item(self):
        s = mk(); s.apply([dict(op='place_along_wall', instance_id='sb', name='Hingan Sideboard', wall_id='south1', along_m=12.0, gap_m=0.0, facing='inward')])
        b = s.view(s.instances['sb'])['bounds_world']; self.assertAlmostEqual(b['min'][1], -8.0, 1); self.assertAlmostEqual(s.view(s.instances['sb'])['facing_deg'], 90.0, 0)
        s.apply([dict(op='place_along_wall', instance_id='sc', name='Oriental Wall Scroll', wall_id='south1', along_m=12.0, height_m=3.0)])
        self.assertAlmostEqual(s.instances['sc']['pivot'][1], -8.0, 1)

    def test_face_target(self):
        s = mk(); s.apply([P('Hingan Chair', [0, -3, 0], instance_id='c'), P('Hingan Sitting Table', [0, -6, 0], instance_id='t')]); s.apply([dict(op='face', instance_id='c', target_id='t')])
        self.assertAlmostEqual(s.view(s.instances['c'])['facing_deg'], 270.0, 0)

    def test_budget_and_unknown(self):
        s = mk()
        with self.assertRaises(DecoError) as c: s.apply([P('No Such Item', [0, 0, 0])])
        self.assertTrue(any(i['code'] == 'UNKNOWN_ITEM' for i in c.exception.issues))

    def test_export_roundtrip(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], 33, instance_id='a')]); r = s.export('x'); raw = Path(r['layout']['path']).read_bytes()
        self.assertTrue(raw.startswith(b'\xff\xfe')); d = json.loads(raw); self.assertEqual(len(d['interiorFurniture']), 1); self.assertEqual(d['houseSize'], 'Medium')
        q = d['interiorFurniture'][0]['transform']['rotation']; self.assertAlmostEqual(math.degrees(2 * math.atan2(q[2], q[3])), 33, 3)

    def test_search(self):
        rows, _ = mk().cat.search('tea set', 'text', [], [], 5); self.assertTrue(any('Tea Set' in r['name'] for r in rows))


if __name__ == '__main__': unittest.main()


class RelaxedTest(unittest.TestCase):
    def test_spatial_findings_are_warnings_by_default(self):
        s = mk(); r = s.apply([P('Hingan Sofa', [8, 3, 0], instance_id='in_stairs'), P('Hingan Sofa', [30, 0, 0], instance_id='outside'), dict(op='place', name='Oriental Wall Scroll', position=[0, -3, 3.0], yaw_deg=0, anchor='pivot', instance_id='floating')])
        codes = {w['code'] for w in r['warnings']}; self.assertTrue({'STAIR_INTERSECTION', 'OUTSIDE_FLOOR', 'WALL_MOUNT_INVALID'} <= codes)
        self.assertEqual(len(s.instances), 3); self.assertTrue(all(w.get('severity') == 'advisory' for w in r['warnings'] if w['code'] in ('STAIR_INTERSECTION', 'OUTSIDE_FLOOR')))

    def test_budget_is_still_hard(self):
        s = mk()
        s.apply([P('Zabuton Cushion', [0, -3, 0]) for _ in range(450)]); self.assertEqual(len(s.instances), 450)
        with self.assertRaises(DecoError) as c: s.apply([P('Zabuton Cushion', [0, -3, 0])])
        self.assertEqual(c.exception.issues[-1]['code'], 'BUDGET_EXCEEDED')

    def test_stair_clearance_reports_underside(self):
        cl = mk().room.stair_clearance(); self.assertTrue(cl['up']['cells']); self.assertTrue(any(c[2] < 1.0 for c in cl['up']['cells'])); self.assertTrue(any(c[2] >= 3.0 for c in cl['up']['cells']))


class WallHostTest(unittest.TestCase):
    def test_scroll_on_partition_ok_floating_scroll_rejected(self):
        s = mk(); s.apply([P('Hingan Windowed Partition', [-4.6, -4.5, 0], 90, instance_id='wp')])
        s.apply([dict(op='place', name='Oriental Wall Scroll', position=[-4.36, -6.6, 3.0], yaw_deg=270, anchor='pivot')])
        with self.assertRaises(DecoError) as c: s.apply([dict(op='place', name='Oriental Wall Scroll', position=[0, -3, 3.0], yaw_deg=0, anchor='pivot')], strict=True)
        self.assertEqual(c.exception.issues[0]['code'], 'WALL_MOUNT_INVALID')


class UpperFloorTest(unittest.TestCase):
    def test_upper_polygon_has_stair_opening_and_levels_are_separate(self):
        r = mk().room; self.assertAlmostEqual(r.upper.area, 336, delta=2); self.assertFalse(r.upper.contains(__import__('shapely.geometry').geometry.Point(8, 5)))
        s = mk(); res = s.apply([P('Hingan Sofa', [-8, 5, 7.0], instance_id='up_ok')])   # above the ground-floor hole: valid on the upper floor
        self.assertFalse([w for w in res['warnings'] if w['code'] == 'OUTSIDE_FLOOR'])
        res = s.apply([P('Hingan Sofa', [8, 5, 7.0], instance_id='in_opening')]); self.assertTrue([w for w in res['warnings'] if w['code'] == 'OUTSIDE_FLOOR'])
    def test_floor_standing_thin_panel_on_upper_floor_is_not_a_wall_item(self):
        # A slat partition standing on the upper floor (bottom z = 7) is a floor item; the "raised thin panel = wall-hung"
        # heuristic must use the height above the level's floor, not absolute z (every upper panel was flagged).
        s = mk(); res = s.apply([P('Wood Slat Partition', [0, -4, 7.0], 90, instance_id='slat_up'), P('Wood Slat Partition', [0, -4, 0.0], 90, instance_id='slat_g')])
        self.assertFalse([w for w in res['warnings'] if w['code'] == 'WALL_MOUNT_INVALID'], res['warnings'])
        res = s.apply([P('Wood Slat Partition', [5, -4, 8.5], 90, instance_id='slat_raised')])   # genuinely raised 1.5 m above the upper floor
        self.assertTrue([w for w in res['warnings'] if w['code'] == 'WALL_MOUNT_INVALID'])

    def test_upper_fixtures_export_to_upper_slot(self):
        s = mk(); s.apply([dict(op='fixture', type='Wall', level='upper', item_id=44870), dict(op='fixture', type='Wall', item_id=7138)])
        d = s.layout_dict(); slots = {x['level']: x['itemId'] for x in d['interiorFixture'] if x['type'] == 'Wall'}
        self.assertEqual(slots['Upper Floor'], 44870); self.assertEqual(slots['Ground Floor'], 7138)


    def test_inspect_surfaces_have_world_centres_matching_place_on(self):
        s = mk(); s.apply([P('Hingan Sitting Table', [-2.0, -3.0, 0], 90, instance_id='t')])
        surf = [x for x in s.inspect()['surfaces'] if x['owner_id'] == 't']
        self.assertTrue(surf)
        for x in surf:
            self.assertEqual(len(x['center_world']), 2)
            s.apply([dict(op='place_on', instance_id=f"c{x['surface_idx']}", name='Green Tea Set', target_id='t', surface_idx=x['surface_idx'], offset_xy=[0, 0])])
            b = s.view(s.instances[f"c{x['surface_idx']}"])['bounds_world']
            cx, cy = (b['min'][0] + b['max'][0]) / 2, (b['min'][1] + b['max'][1]) / 2
            self.assertAlmostEqual(cx, x['center_world'][0], delta=0.05); self.assertAlmostEqual(cy, x['center_world'][1], delta=0.05)

class AnalyzeTest(unittest.TestCase):
    def test_closed_box_is_inaccessible_and_a_door_opens_it(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = mk(); s.apply([P('Oasis Stool', [-8, -5, 0], instance_id='in_room'), P(B, [-10.2, -5.0, 0], 90), P(B, [-5.8, -5.0, 0], 90), P(B, [-8.0, -2.6, 0], 0), P(B, [-8.0, -7.6, 0], 0)])
        self.assertIn('in_room', [x['instance_id'] for x in analyze(s, start=(0.0, -4.0))['reachability']['instances_without_access']])
        s2 = mk(); s2.apply([P('Oasis Stool', [-8, -5, 0], instance_id='in_room'), P(B, [-10.2, -5.0, 0], 90), P('Minimalist Partition Door', [-5.8, -5.0, 0], 90), P(B, [-8.0, -2.6, 0], 0), P(B, [-8.0, -7.6, 0], 0)])
        self.assertNotIn('in_room', [x['instance_id'] for x in analyze(s2, start=(0.0, -4.0))['reachability']['instances_without_access']])

    def test_offset_sliding_door_partitions_open_a_closed_box(self):
        # Paper/Oriental Partition have no 'door' in their names; their walkable opening is a measured
        # ~1.8 m half-open bay on local +x, not a centred gap. Reachability must use the mesh opening.
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        for door in ('Paper Partition', 'Oriental Partition'):
            s = mk(); s.apply([P('Oasis Stool', [-8, -5, 0], instance_id='in_room'), P(B, [-10.2, -5.0, 0], 90), P(door, [-5.8, -5.0, 0], 90, instance_id='d'), P(B, [-8.0, -2.6, 0], 0), P(B, [-8.0, -7.6, 0], 0)])
            a = analyze(s, start=(0.0, -4.0))
            self.assertNotIn('in_room', [x['instance_id'] for x in a['reachability']['instances_without_access']], door)
            # turning it end-for-end (yaw 90 -> 270) moves the opening to the other half; it must still open the box
            s.apply([dict(op='rotate', instance_id='d', yaw_deg=270)])
            a = analyze(s, start=(0.0, -4.0))
            self.assertNotIn('in_room', [x['instance_id'] for x in a['reachability']['instances_without_access']], door + ' yaw270')

    def test_solid_partition_without_opening_stays_closed(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = mk(); s.apply([P('Oasis Stool', [-8, -5, 0], instance_id='in_room'), P(B, [-10.2, -5.0, 0], 90), P('Blank Hingan Partition', [-5.8, -5.0, 0], 90), P(B, [-8.0, -2.6, 0], 0), P(B, [-8.0, -7.6, 0], 0)])
        self.assertIn('in_room', [x['instance_id'] for x in analyze(s, start=(0.0, -4.0))['reachability']['instances_without_access']])

    def test_check_routes_reports_blockers_but_not_rugs_or_door_openings(self):
        from ffxiv_furniture.deco.analyze import check_routes
        route = [dict(name='aisle', points=[[-3, -5], [3, -5]])]
        s = mk()
        r = check_routes(s, route)[0]
        self.assertTrue(r['clear'], r); self.assertEqual(r['blockers'], [])
        s.apply([P('Combed Wool Rug', [0, -5, 0], instance_id='rug')])
        self.assertTrue(check_routes(s, route)[0]['clear'])
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t')])
        r = check_routes(s, route)[0]
        self.assertFalse(r['clear']); self.assertEqual([b['instance_id'] for b in r['blockers']], ['t'])
        self.assertGreater(r['blockers'][0]['overlap_m2'], 0.3)
        s2 = mk(); s2.apply([P('Minimalist Partition Door', [0, -5, 0], 90, instance_id='door')])
        self.assertTrue(check_routes(s2, route)[0]['clear'])
        s3 = mk(); s3.apply([P('Blank Minimalist Partition', [0, -5, 0], 90, instance_id='wall')])
        self.assertEqual([b['instance_id'] for b in check_routes(s3, route)[0]['blockers']], ['wall'])

    def test_check_routes_width_and_validation(self):
        from ffxiv_furniture.deco.analyze import check_routes
        s = mk(); s.apply([P('Hingan Sitting Table', [0, -3.5, 0], instance_id='t')])   # table edge ~0.7 m from the line
        line = [dict(name='a', points=[[-3, -5.0], [3, -5.0]])]
        self.assertTrue(check_routes(s, line, width_m=0.8)[0]['clear'])
        self.assertFalse(check_routes(s, line, width_m=2.4)[0]['clear'])
        for bad in ([dict(name='x', points=[[0, 0]])], [dict(points=[[0, 0], [1, 1]])], [dict(name='x', points=[[0, 0], [float('nan'), 1]])]):
            with self.assertRaises(DecoError): check_routes(s, bad)
        with self.assertRaises(DecoError): check_routes(s, line, width_m=0)

    def test_check_routes_mcp_tool_wraps_errors(self):
        from unittest.mock import patch
        from mcp.server.fastmcp.exceptions import ToolError
        from ffxiv_furniture.deco import server
        s = mk(); s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t')])
        with patch.object(server, '_boot', return_value=s), patch.object(server, '_sess', s):
            r = server.check_routes(routes=[dict(name='aisle', points=[[-3, -5], [3, -5]])])
            self.assertEqual(r['routes'][0]['blockers'][0]['instance_id'], 't'); self.assertFalse(r['all_clear'])
            with self.assertRaises(ToolError): server.check_routes(routes=[])

    def test_wall_gaps_report_narrow_seal_leaks_with_location(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = mk(); s.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-3.8, -2.6, 0], 0, instance_id='w2')])   # ends 0.2 m apart at x~-5.9
        gaps = analyze(s)['wall_gaps']
        hit = [g for g in gaps if {g['a'], g['b']} == {'w1', 'w2'}]
        self.assertEqual(len(hit), 1, gaps)
        self.assertAlmostEqual(hit[0]['width_m'], 0.2, delta=0.05)
        self.assertAlmostEqual(hit[0]['at'][0], -5.9, delta=0.15); self.assertAlmostEqual(hit[0]['at'][1], -2.6, delta=0.5)
        s2 = mk(); s2.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-4.0, -2.6, 0], 0, instance_id='w2')])   # touching: sealed
        self.assertEqual([g for g in analyze(s2)['wall_gaps'] if {g['a'], g['b']} == {'w1', 'w2'}], [])
        s3 = mk(); s3.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-2.0, -2.6, 0], 0, instance_id='w2')])   # 2 m: a real opening
        self.assertEqual([g for g in analyze(s3)['wall_gaps'] if {g['a'], g['b']} == {'w1', 'w2'}], [])

    def test_wall_gaps_ignore_gaps_bridged_by_a_third_piece(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = mk(); s.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-3.8, -2.6, 0], 0, instance_id='w2'),
                           P(B, [-5.9, -2.0, 0], 0, instance_id='bridge')])   # third wall laps over the 0.2 m slit
        self.assertEqual([g for g in analyze(s)['wall_gaps'] if {g['a'], g['b']} == {'w1', 'w2'}], [])

    def test_wall_gaps_ignore_a_slit_closed_by_a_full_height_furniture_pillar(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = mk(); s.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-3.8, -2.6, 0], 0, instance_id='w2'),
                           P('Simple Hingan Pillar', [-5.9, -2.6, 0], 0, instance_id='post')])   # a post stands in the 0.2 m slit
        self.assertEqual([g for g in analyze(s)['wall_gaps'] if {g['a'], g['b']} == {'w1', 'w2'}], [])

    def test_raised_platform_is_walkable_but_a_table_is_not(self):
        from ffxiv_furniture.deco.analyze import analyze, check_routes, is_platform
        s = mk()
        self.assertTrue(is_platform(s.cat.item(name='Tatami Loft')))
        self.assertFalse(is_platform(s.cat.item(name='Hingan Sitting Table')))
        s.apply([P('Tatami Loft', [0, -4, 0], instance_id='loft'), P('Zabuton Cushion', [0, -4, 0.5], instance_id='cushion')])
        a = analyze(s)
        self.assertNotIn('loft', [x['instance_id'] for x in a['reachability']['instances_without_access']])
        r = check_routes(s, [dict(name='over', points=[[-3, -4], [3, -4]])])[0]
        self.assertTrue(r['clear'], r); self.assertEqual([x['instance_id'] for x in r['steps']], ['loft'])
        s.apply([P('Hingan Sitting Table', [0, -4, 0.5], instance_id='t')])
        r = check_routes(s, [dict(name='over', points=[[-3, -4], [3, -4]])])[0]
        self.assertEqual([x['instance_id'] for x in r['blockers']], ['t'])

    def test_tall_pieces_crowding_the_entrance_are_listed(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = mk(); dx, dy = s.room.door_xy   # Medium: door on the north wall, lane runs south
        s.apply([P('Hingan Cupboard', [dx + 2.3, dy - 1.5, 0], 0, instance_id='near'), P('Hingan Cupboard', [dx + 8, dy - 6, 0], 0, instance_id='far'),
                 P('Hingan Bench', [dx - 2.2, dy - 1.5, 0], 0, instance_id='low')])
        hits = {x['instance_id']: x for x in analyze(s)['entrance_tall']}
        self.assertIn('near', hits); self.assertNotIn('far', hits); self.assertNotIn('low', hits)
        self.assertGreaterEqual(hits['near']['height_m'], 2.0); self.assertLess(hits['near']['distance_to_lane_m'], 1.5)
        self.assertEqual(analyze(s, level='upper')['entrance_tall'], [])

    def test_seat_facing_error_reported(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = mk(); s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t'), P('Hingan Chair', [0, -3.6, 0], instance_id='c'), dict(op='face', instance_id='c', target_id='t')])
        ok = [x for x in analyze(s)['seat_orientation'] if x['instance_id'] == 'c'][0]['facing_error_deg']
        s.apply([dict(op='rotate', instance_id='c', yaw_deg=(s.instances['c']['yaw'] + 40) % 360)])
        bad = [x for x in analyze(s)['seat_orientation'] if x['instance_id'] == 'c'][0]['facing_error_deg']
        self.assertLess(ok, 3); self.assertAlmostEqual(bad, 40, delta=3)


class AnalyzeFactsTest(unittest.TestCase):
    def test_overlapping_floor_items_flagged(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = mk(); s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t1'), P('Hingan Sitting Table', [0.3, -5, 0], instance_id='t2')])
        pairs = {(x['a'], x['b']) for x in analyze(s)['overlaps']}
        self.assertIn(('t1', 't2'), pairs)

    def test_supported_stack_and_rug_are_not_overlaps(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = mk()
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t'), P('Combed Wool Rug', [0, -5, 0], instance_id='r'), dict(op='place_on', name='Encyclopedia Eorzea', target_id='t', offset_xy=[0, 0], instance_id='bk')])
        a = analyze(s)['overlaps']
        self.assertEqual([x for x in a if 'bk' in (x['a'], x['b']) or 'r' in (x['a'], x['b'])], [])

    def test_seat_tucked_at_its_table_not_front_blocked(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = mk(); s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t'), P('Hingan Chair', [0, -4.2, 0], 180, instance_id='c')])
        self.assertNotIn('c', [x['instance_id'] for x in analyze(s)['front_clearance']])

    def test_seat_blocked_by_other_furniture_front_flagged(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = mk(); s.apply([P('Hingan Chair', [0, -4.2, 0], 0, instance_id='c'), P('Hingan Sofa', [0, -2.8, 0], 180, instance_id='sofa')])
        hits = [x for x in analyze(s)['front_clearance'] if x['instance_id'] == 'c']
        self.assertTrue(hits and hits[0]['front_blocked_fraction'] > 0.5)


class AnalyzeUpperTest(unittest.TestCase):
    def test_upper_level_sees_upper_items(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = mk(); s.apply([P('Hingan Sofa', [-8, -5, 7.0], instance_id='up')])
        a = analyze(s, level='upper'); self.assertGreater(a['balance']['covered_fraction'], 0.0)


class StairInfoTest(unittest.TestCase):
    def test_minimalist_native_stair_zones_and_warning(self):
        r = Room('Minimalist'); u = r.stair_summary()['up']
        self.assertAlmostEqual(u['foot_xy_bounds'][0], 3.8, delta=0.2); self.assertGreater(u['foot_xy_bounds'][1], 4.5)       # foot beside the hall, north end (mirrored stair)
        self.assertGreater(u['upper_arrival_xy_bounds'][0], 8.5); self.assertLess(u['upper_arrival_xy_bounds'][1], 0.5)       # arrival at the south end of flight 2
        s = Session('stairs', _cat or Catalog(), r, tempfile.mkdtemp(), seed_layout={**SEED, 'interiorFixture': [dict(f, name='Minimalist') if f['type'] == 'District' else f for f in SEED['interiorFixture']]})
        res = s.apply([P('Hingan Sofa', [4.2, 6.0, 0], instance_id='on_foot'), P('Hingan Sofa', [0, -5, 0], instance_id='fine')])
        self.assertIn('on_foot', [w.get('instance_id') for w in res['warnings'] if w['code'] in ('STAIR_ACCESS_BLOCKED', 'STAIR_INTERSECTION')])
        self.assertNotIn('fine', [w.get('instance_id') for w in res['warnings'] if w['code'].startswith('STAIR')])


class DyeTest(unittest.TestCase):
    def test_dye_export_roundtrip_and_rules(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a'), P('Pine Bonsai', [2, -3, 0], instance_id='b')])
        s.apply([dict(op='dye', instance_id='a', color='Snow White')]); self.assertEqual(s.instances['a']['color'], 'E4DFD0')
        d = s.layout_dict(); self.assertEqual(d['interiorFurniture'][0]['properties'], {'color': 'E4DFD0FF'})
        s.apply([dict(op='dye', instance_id='a', color='#e5e0d1')]); self.assertEqual(s.instances['a']['color'], 'E4DFD0')    # snaps to the nearest housing dye
        with self.assertRaises(DecoError): s.apply([dict(op='dye', instance_id='a', color='no such dye')])
        s.apply([dict(op='dye', instance_id='a', color=None)]); self.assertNotIn('color', s.instances['a'])
        s2 = Session('d2', _cat, _room, tempfile.mkdtemp(), seed_layout=SEED, from_layout=dict(SEED, interiorFurniture=[dict(s.layout_dict()['interiorFurniture'][0], properties={'color': '781A1AFF'})]))
        self.assertEqual(list(s2.instances.values())[0]['color'], '781A1A')


class CeilingLightTest(unittest.TestCase):
    def test_full_height_piece_under_ceiling_light_is_flagged(self):
        # The ceiling-light fixture hangs at the room centre (0,0); a full-height partition through it clipped the lamp in the app.
        s = mk(); s.apply([dict(op='fixture', type='Light', level='ground', name='Flat Ceiling Lamp')])
        r = s.apply([P('White Partition', [0, 0, 0], 0, instance_id='through_lamp'), P('White Partition', [0, -4, 0], 0, instance_id='clear'),
                     P('Hingan Sofa', [0, 0, 0], 0, instance_id='low_sofa')])
        ids = [w['instance_id'] for w in r['warnings'] if w['code'] == 'CEILING_LIGHT_CONFLICT']
        self.assertEqual(ids, ['through_lamp'])
        self.assertTrue(all(w['severity'] == 'advisory' for w in r['warnings'] if w['code'] == 'CEILING_LIGHT_CONFLICT'))
        r = s.apply([P('White Partition', [0, 0, 7.0], 0, instance_id='upper_through')])
        self.assertIn('upper_through', [w['instance_id'] for w in r['warnings'] if w['code'] == 'CEILING_LIGHT_CONFLICT'])
