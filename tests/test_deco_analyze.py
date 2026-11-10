"""Layout reachability, routes, enclosures, wall gaps, support and seating analysis."""
import unittest
from ffxiv_furniture.deco import analyze as an
from ffxiv_furniture.deco.core import DecoError
from tests.support import P, session

class AnalyzeTest(unittest.TestCase):

    def test_closed_box_is_inaccessible_and_a_door_opens_it(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = session()
        s.apply([P('Oasis Stool', [-8, -5, 0], instance_id='in_room'), P(B, [-10.2, -5.0, 0], 90), P(B, [-5.8, -5.0, 0], 90), P(B, [-8.0, -2.6, 0], 0), P(B, [-8.0, -7.6, 0], 0)])
        self.assertIn('in_room', [x['instance_id'] for x in analyze(s, start=(0.0, -4.0))['reachability']['instances_without_access']])
        s2 = session()
        s2.apply([P('Oasis Stool', [-8, -5, 0], instance_id='in_room'), P(B, [-10.2, -5.0, 0], 90), P('Minimalist Partition Door', [-5.8, -5.0, 0], 90), P(B, [-8.0, -2.6, 0], 0), P(B, [-8.0, -7.6, 0], 0)])
        self.assertNotIn('in_room', [x['instance_id'] for x in analyze(s2, start=(0.0, -4.0))['reachability']['instances_without_access']])

    def test_offset_sliding_door_partitions_open_a_closed_box(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        for door in ('Paper Partition', 'Oriental Partition'):
            s = session()
            s.apply([P('Oasis Stool', [-8, -5, 0], instance_id='in_room'), P(B, [-10.2, -5.0, 0], 90), P(door, [-5.8, -5.0, 0], 90, instance_id='d'), P(B, [-8.0, -2.6, 0], 0), P(B, [-8.0, -7.6, 0], 0)])
            a = analyze(s, start=(0.0, -4.0))
            self.assertNotIn('in_room', [x['instance_id'] for x in a['reachability']['instances_without_access']], door)
            s.apply([dict(op='rotate', instance_id='d', yaw_deg=270)])
            a = analyze(s, start=(0.0, -4.0))
            self.assertNotIn('in_room', [x['instance_id'] for x in a['reachability']['instances_without_access']], door + ' yaw270')

    def test_solid_partition_without_opening_stays_closed(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = session()
        s.apply([P('Oasis Stool', [-8, -5, 0], instance_id='in_room'), P(B, [-10.2, -5.0, 0], 90), P('Blank Hingan Partition', [-5.8, -5.0, 0], 90), P(B, [-8.0, -2.6, 0], 0), P(B, [-8.0, -7.6, 0], 0)])
        self.assertIn('in_room', [x['instance_id'] for x in analyze(s, start=(0.0, -4.0))['reachability']['instances_without_access']])

    def test_check_routes_reports_blockers_but_not_rugs_or_door_openings(self):
        from ffxiv_furniture.deco.analyze import check_routes
        route = [dict(name='aisle', points=[[-3, -5], [3, -5]])]
        s = session()
        r = check_routes(s, route)[0]
        self.assertTrue(r['clear'], r)
        self.assertEqual(r['blockers'], [])
        s.apply([P('Combed Wool Rug', [0, -5, 0], instance_id='rug')])
        self.assertTrue(check_routes(s, route)[0]['clear'])
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t')])
        r = check_routes(s, route)[0]
        self.assertFalse(r['clear'])
        self.assertEqual([b['instance_id'] for b in r['blockers']], ['t'])
        self.assertGreater(r['blockers'][0]['overlap_m2'], 0.3)
        s2 = session()
        s2.apply([P('Minimalist Partition Door', [0, -5, 0], 90, instance_id='door')])
        self.assertTrue(check_routes(s2, route)[0]['clear'])
        s3 = session()
        s3.apply([P('Blank Minimalist Partition', [0, -5, 0], 90, instance_id='wall')])
        self.assertEqual([b['instance_id'] for b in check_routes(s3, route)[0]['blockers']], ['wall'])

    def test_check_routes_width_and_validation(self):
        from ffxiv_furniture.deco.analyze import check_routes
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -3.5, 0], instance_id='t')])
        line = [dict(name='a', points=[[-3, -5.0], [3, -5.0]])]
        self.assertTrue(check_routes(s, line, width_m=0.8)[0]['clear'])
        self.assertFalse(check_routes(s, line, width_m=2.4)[0]['clear'])
        for bad in ([dict(name='x', points=[[0, 0]])], [dict(points=[[0, 0], [1, 1]])], [dict(name='x', points=[[0, 0], [float('nan'), 1]])]):
            with self.assertRaises(DecoError):
                check_routes(s, bad)
        with self.assertRaises(DecoError):
            check_routes(s, line, width_m=0)

    def test_wall_gaps_report_narrow_seal_leaks_with_location(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = session()
        s.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-3.8, -2.6, 0], 0, instance_id='w2')])
        gaps = analyze(s)['wall_gaps']
        hit = [g for g in gaps if {g['a'], g['b']} == {'w1', 'w2'}]
        self.assertEqual(len(hit), 1, gaps)
        self.assertAlmostEqual(hit[0]['width_m'], 0.2, delta=0.05)
        self.assertAlmostEqual(hit[0]['at'][0], -5.9, delta=0.15)
        self.assertAlmostEqual(hit[0]['at'][1], -2.6, delta=0.5)
        s2 = session()
        s2.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-4.0, -2.6, 0], 0, instance_id='w2')])
        self.assertEqual([g for g in analyze(s2)['wall_gaps'] if {g['a'], g['b']} == {'w1', 'w2'}], [])
        s3 = session()
        s3.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-2.0, -2.6, 0], 0, instance_id='w2')])
        self.assertEqual([g for g in analyze(s3)['wall_gaps'] if {g['a'], g['b']} == {'w1', 'w2'}], [])

    def test_wall_gaps_ignore_gaps_bridged_by_a_third_piece(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = session()
        s.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-3.8, -2.6, 0], 0, instance_id='w2'), P(B, [-5.9, -2.0, 0], 0, instance_id='bridge')])
        self.assertEqual([g for g in analyze(s)['wall_gaps'] if {g['a'], g['b']} == {'w1', 'w2'}], [])

    def test_wall_gaps_ignore_a_slit_closed_by_a_full_height_furniture_pillar(self):
        from ffxiv_furniture.deco.analyze import analyze
        B = 'Blank Minimalist Partition'
        s = session()
        s.apply([P(B, [-8.0, -2.6, 0], 0, instance_id='w1'), P(B, [-3.8, -2.6, 0], 0, instance_id='w2'), P('Simple Hingan Pillar', [-5.9, -2.6, 0], 0, instance_id='post')])
        self.assertEqual([g for g in analyze(s)['wall_gaps'] if {g['a'], g['b']} == {'w1', 'w2'}], [])

    def test_raised_platform_is_walkable_but_a_table_is_not(self):
        from ffxiv_furniture.deco.analyze import analyze, check_routes, is_platform
        s = session()
        self.assertTrue(is_platform(s.cat.item(name='Tatami Loft')))
        self.assertFalse(is_platform(s.cat.item(name='Hingan Sitting Table')))
        s.apply([P('Tatami Loft', [0, -4, 0], instance_id='loft'), P('Zabuton Cushion', [0, -4, 0.5], instance_id='cushion')])
        a = analyze(s)
        self.assertNotIn('loft', [x['instance_id'] for x in a['reachability']['instances_without_access']])
        r = check_routes(s, [dict(name='over', points=[[-3, -4], [3, -4]])])[0]
        self.assertTrue(r['clear'], r)
        self.assertEqual([x['instance_id'] for x in r['steps']], ['loft'])
        s.apply([P('Hingan Sitting Table', [0, -4, 0.5], instance_id='t')])
        r = check_routes(s, [dict(name='over', points=[[-3, -4], [3, -4]])])[0]
        self.assertEqual([x['instance_id'] for x in r['blockers']], ['t'])

    def test_tall_pieces_crowding_the_entrance_are_listed(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = session()
        dx, dy = s.room.door_xy
        s.apply([P('Hingan Cupboard', [dx + 2.3, dy - 1.5, 0], 0, instance_id='near'), P('Hingan Cupboard', [dx + 8, dy - 6, 0], 0, instance_id='far'), P('Hingan Bench', [dx - 2.2, dy - 1.5, 0], 0, instance_id='low')])
        hits = {x['instance_id']: x for x in analyze(s)['entrance_tall']}
        self.assertIn('near', hits)
        self.assertNotIn('far', hits)
        self.assertNotIn('low', hits)
        self.assertGreaterEqual(hits['near']['height_m'], 2.0)
        self.assertLess(hits['near']['distance_to_lane_m'], 1.5)
        self.assertEqual(analyze(s, level='upper')['entrance_tall'], [])

    def test_seat_facing_error_reported(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t'), P('Hingan Chair', [0, -3.6, 0], instance_id='c'), dict(op='face', instance_id='c', target_id='t')])
        ok = [x for x in analyze(s)['seat_orientation'] if x['instance_id'] == 'c'][0]['facing_error_deg']
        s.apply([dict(op='rotate', instance_id='c', yaw_deg=(s.instances['c']['yaw'] + 40) % 360)])
        bad = [x for x in analyze(s)['seat_orientation'] if x['instance_id'] == 'c'][0]['facing_error_deg']
        self.assertLess(ok, 3)
        self.assertAlmostEqual(bad, 40, delta=3)

class AnalyzeFactsTest(unittest.TestCase):

    def test_overlapping_floor_items_flagged(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t1'), P('Hingan Sitting Table', [0.3, -5, 0], instance_id='t2')])
        pairs = {(x['a'], x['b']) for x in analyze(s)['overlaps']}
        self.assertIn(('t1', 't2'), pairs)

    def test_supported_stack_and_rug_are_not_overlaps(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t'), P('Combed Wool Rug', [0, -5, 0], instance_id='r'), dict(op='place_on', name='Encyclopedia Eorzea', target_id='t', offset_xy=[0, 0], instance_id='bk')])
        a = analyze(s)['overlaps']
        self.assertEqual([x for x in a if 'bk' in (x['a'], x['b']) or 'r' in (x['a'], x['b'])], [])

    def test_seat_tucked_at_its_table_not_front_blocked(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t'), P('Hingan Chair', [0, -4.2, 0], 180, instance_id='c')])
        self.assertNotIn('c', [x['instance_id'] for x in analyze(s)['front_clearance']])

    def test_seat_blocked_by_other_furniture_front_flagged(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = session()
        s.apply([P('Hingan Chair', [0, -4.2, 0], 0, instance_id='c'), P('Hingan Sofa', [0, -2.8, 0], 180, instance_id='sofa')])
        hits = [x for x in analyze(s)['front_clearance'] if x['instance_id'] == 'c']
        self.assertTrue(hits and hits[0]['front_blocked_fraction'] > 0.5)

class AnalyzeUpperTest(unittest.TestCase):

    def test_upper_level_sees_upper_items(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = session()
        s.apply([P('Hingan Sofa', [-8, -5, 7.0], instance_id='up')])
        a = analyze(s, level='upper')
        self.assertGreater(a['balance']['covered_fraction'], 0.0)

class ApartmentEnclosureTests(unittest.TestCase):

    def test_enclosure_reported_when_sealed(self):
        from ffxiv_furniture.deco.analyze import analyze
        s = session('Apartment', style='Mist')
        s.apply([P('Blank Minimalist Partition', [-4.0, 0.0, 0], instance_id='n'), P('Blank Minimalist Partition', [-2.0, -5.62, 0], 90, instance_id='e1'), P('Minimalist Partition Door', [-2.0, -1.62, 0], 90, instance_id='d')])
        enc = analyze(s)['enclosures']
        self.assertEqual(len(enc), 1)
        self.assertEqual(enc[0]['door_partitions'], ['d'])
        s.apply([dict(op='remove', instance_id='e1')])
        self.assertEqual(analyze(s)['enclosures'], [])
LOG = 28154

class WallGapTests(unittest.TestCase):

    def test_partition_near_wall_with_pillars_is_reported_on_both_sides(self):
        south = session()
        south.apply([dict(op='place', item_id=LOG, position=[1.5, 5.7, 0], yaw_deg=90)])
        north = session()
        north.apply([dict(op='place', item_id=LOG, position=[1.5, -5.7, 0], yaw_deg=90)])
        a, b = (an.analyze(south)['wall_gaps'], an.analyze(north)['wall_gaps'])
        self.assertEqual([g['b'] for g in a], ['room-wall'])
        self.assertEqual([g['b'] for g in b], ['room-wall'], b)
        self.assertAlmostEqual(a[0]['width_m'], b[0]['width_m'], 2)

    def test_at_is_slit_centre_end_to_end(self):
        s = session()
        s.apply([dict(op='place', item_id=LOG, position=[0, 0, 0], yaw_deg=0), dict(op='place', item_id=LOG, position=[4.2, 0, 0], yaw_deg=0)])
        g = an.analyze(s)['wall_gaps']
        self.assertEqual(len(g), 1)
        self.assertAlmostEqual(g[0]['at'][1], 0.0, delta=0.06)
        self.assertAlmostEqual(g[0]['at'][0], 2.1, delta=0.06)
        self.assertAlmostEqual(g[0]['width_m'], 0.2, delta=0.01)

class CheckRoutesLevelTests(unittest.TestCase):

    def test_unknown_level_for_house_rejected(self):
        s = session('Small')
        self.assertNotIn('upper', s.room.levels)
        with self.assertRaises(DecoError) as c:
            an.check_routes(s, [dict(name='r', points=[[0, 0], [1, 1]])], level='upper')
        self.assertEqual(c.exception.code, 'BAD_INPUT')
        r = an.check_routes(s, [dict(name='r', points=[[0, 0], [1, 1]])], level='basement')
        self.assertTrue(r[0]['clear'])
        with self.assertRaises(DecoError):
            an.check_routes(s, [dict(name='r', points=[[0, 0], [1, 1]])], level='bogus')
