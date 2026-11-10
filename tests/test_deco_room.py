"""Room geometry, levels, openings, stair access and under-stair clearance."""
import numpy as np
import unittest
from ffxiv_furniture.deco.core import Room
from ffxiv_furniture.interiors import BASE, InteriorProfile, STYLES
from tests.support import P, needs_meshes, room, session

class RoomStairClearanceTests(unittest.TestCase):

    def test_stair_clearance_reports_underside(self):
        cl = room().stair_clearance()
        self.assertTrue(cl['up']['cells'])
        self.assertTrue(any((c[2] < 1.0 for c in cl['up']['cells'])))
        self.assertTrue(any((c[2] >= 3.0 for c in cl['up']['cells'])))

class StairInfoTest(unittest.TestCase):

    def test_minimalist_native_stair_zones_and_warning(self):
        r = Room('Minimalist')
        u = r.stair_summary()['up']
        self.assertAlmostEqual(u['foot_xy_bounds'][0], 3.8, delta=0.2)
        self.assertGreater(u['foot_xy_bounds'][1], 4.5)
        self.assertGreater(u['upper_arrival_xy_bounds'][0], 8.5)
        self.assertLess(u['upper_arrival_xy_bounds'][1], 0.5)
        s = session(style='Minimalist')
        res = s.apply([P('Hingan Sofa', [4.2, 6.0, 0], instance_id='on_foot'), P('Hingan Sofa', [0, -5, 0], instance_id='fine')])
        self.assertIn('on_foot', [w.get('instance_id') for w in res['warnings'] if w['code'] in ('STAIR_ACCESS_BLOCKED', 'STAIR_INTERSECTION')])
        self.assertNotIn('fine', [w.get('instance_id') for w in res['warnings'] if w['code'].startswith('STAIR')])

class ApartmentRoomTests(unittest.TestCase):

    def test_room_is_single_floor_without_stairs(self):
        r = Room('Shirogane', 'Apartment')
        self.assertEqual((r.house_size, r.limit, r.levels), ('Apartment', 150, ('ground',)))
        self.assertEqual([round(v, 2) for v in r.floor.bounds], [-6.0, -8.0, 6.0, 8.0])
        self.assertEqual(r.walls_by_level['upper'], [])
        self.assertEqual({w['wall_id'] for w in r.walls_by_level['ground']}, {'north1', 'south1', 'east1', 'west1'})
        self.assertIn('no stairs', r.stair_summary()['note'])
        self.assertEqual(r.stairs, [])
HAVE_SMALL_STAIRS = (BASE / 'Mist/Small/BasementFrame.uexp').exists() and (BASE / 'Minimalist/Small/BasementFrame.uexp').exists()

@unittest.skipUnless(HAVE_SMALL_STAIRS, 'native Small interiors not extracted')
class SmallBasementStairTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from ffxiv_furniture.deco.core import Room
        cls.mist = Room('Mist', 'Small')
        cls.mini = Room('Minimalist', 'Small')

    def test_basement_outline_follows_style_walls(self):
        from shapely.geometry import Point
        mb, nb = (self.mist.basement, self.mini.basement)
        for xy in ((8.0, -3.0), (8.0, 2.0)):
            self.assertFalse(mb.contains(Point(*xy)), f'Mist walls off {xy}')
            self.assertTrue(nb.contains(Point(*xy)), f'Minimalist leaves {xy} open')
        for room in (self.mist, self.mini):
            self.assertTrue(room.basement.contains(Point(0.0, 4.0)))
            self.assertTrue(room.basement.contains(Point(8.0, 11.5)))
            self.assertGreater(room.basement.area, 240)

    def test_under_stair_space_per_style(self):
        m = self.mist.stair_summary()['basement']['under_stair']
        n = self.mini.stair_summary()['basement']['under_stair']
        self.assertGreater(m['enclosed_m2'], 25)
        self.assertLess(m['usable_ge_1p9m_m2'], 2)
        self.assertGreater(n['usable_ge_1p9m_m2'], 12)
        self.assertLess(n['enclosed_m2'], 3)
        cells = self.mini.stair_clearance()['basement']['cells']
        self.assertTrue(any((c[2] >= 2.5 and (not c[3]) for c in cells)))
        self.assertTrue(all((c[2] == 0 for c in self.mist.stair_clearance()['basement']['cells'] if c[3])))

    def test_validation_flags_boxed_underside_only(self):
        for room, expect in ((self.mist, True), (self.mini, False)):
            s = session('Small', style=room.style)
            r = s.apply([dict(op='place', instance_id='barrel', name='Wine Barrel', position=[8.0, 1.0, -7.0])])
            codes = {w['code'] for w in r['warnings'] if w.get('instance_id') == 'barrel'}
            self.assertEqual(bool(codes & {'STAIR_INTERSECTION', 'OUTSIDE_FLOOR'}), expect, (room.style, codes))

@needs_meshes
class RoomSizeTests(unittest.TestCase):

    def test_medium_room_has_three_levels_and_basement_stair_facts(self):
        from ffxiv_furniture.deco.core import Room
        r = Room('Shirogane', 'Medium')
        self.assertEqual(r.levels, ('ground', 'upper', 'basement'))
        self.assertEqual(r.limit, 450)
        bs = r.stair_info()['basement']
        self.assertIsNotNone(bs['foot'])
        self.assertIsNotNone(bs['foot_access'])
        self.assertLess(bs['foot'].centroid.x, -3)
        self.assertIn('basement', r.stair_summary())
        self.assertTrue(r.pillars_by_level['basement'])
        self.assertIn('basement', r.stair_clearance())

    def test_large_room_levels_stairs_door_cap(self):
        from ffxiv_furniture.deco.core import Room
        r = Room('Mist', 'Large')
        self.assertEqual(r.levels, ('ground', 'upper', 'basement'))
        self.assertEqual(r.limit, 600)
        self.assertEqual(r.door_xy, (0.0, 12.0))
        si = r.stair_info()
        for k in ('foot', 'top', 'foot_access', 'arrival_access'):
            self.assertIsNotNone(si['up'][k], k)
        self.assertIsNotNone(si['basement']['foot_access'])
        self.assertIsNotNone(si['down']['entry_access'])
        s = r.stair_summary()
        self.assertIn('up', s)
        self.assertIn('basement', s)
        self.assertTrue(all((r.walls_by_level[l] for l in r.levels)))

@needs_meshes
class StairTreadTests(unittest.TestCase):

    def test_medium_shirogane_u_stair_foot_is_the_first_treads_not_the_whole_flight(self):
        from ffxiv_furniture.deco.core import Room
        r = Room('Shirogane', 'Medium')
        si = r.stair_info()
        x0, y0, x1, y1 = si['up']['foot'].bounds
        self.assertLess(x1, 6.0)
        self.assertGreater(y0, 0.8)
        self.assertLess(y1, 5.5)
        bx0, by0, bx1, by1 = si['basement']['foot'].bounds
        self.assertGreater(bx0, -7.0)
        self.assertGreater(by0, 0.8)
        self.assertLess(by1, 5.5)
        hx0, hy0, hx1, hy1 = si['down']['hole'].bounds
        self.assertAlmostEqual(hx1, -4.0, delta=0.6)
        self.assertAlmostEqual(hy0, 2.0, delta=0.6)
        self.assertFalse(si['up']['foot_access'].intersects(__import__('shapely.geometry', fromlist=['box']).box(0.2, -3.0, 1.5, 0.5)))

class RoomStyleGeometryTests(unittest.TestCase):

    def test_room_uses_style_profile_floors_and_stair_points(self):
        for style in STYLES:
            with self.subTest(style=style):
                r = Room(style)
                p = InteriorProfile(style)
                self.assertLess(r.floor.symmetric_difference(p.polygon('ground')).area, 1e-09)
                self.assertLess(r.upper.symmetric_difference(p.polygon('upper')).area, 1e-09)
                np.testing.assert_allclose(r._stair_world('Stairs')[0], p.actor_world('Stairs')[0])
        self.assertGreater(Room('DarkMinimalist').floor.symmetric_difference(Room('Shirogane').floor).area, 10)
