"""Medium basement and Large (ground/upper/basement) interior profiles, built from native meshes and decoded map actors."""
import unittest
from pathlib import Path
from ffxiv_furniture.interiors import BASE, STYLES

HAVE = (BASE / 'Shirogane/Large/GroundFloor/GroundFloorFrame.uexp').exists()


@unittest.skipUnless(HAVE, 'extracted interior meshes absent')
class MediumBasementTests(unittest.TestCase):
    def test_medium_has_basement_level_from_native_frame_and_stair(self):
        from ffxiv_furniture.interiors import InteriorProfile
        p = InteriorProfile('Shirogane')
        self.assertEqual(p.levels, ('ground', 'upper', 'basement'))
        self.assertEqual(p.level_z['basement'], -7.0)
        b = p.polygon('basement')
        x0, y0, x1, y1 = b.bounds
        self.assertGreater(b.area, 200); self.assertLessEqual(b.area, 24 * 16 + 1)
        self.assertGreaterEqual(x0, -12.3); self.assertLessEqual(x1, 12.3); self.assertGreaterEqual(y0, -8.3); self.assertLessEqual(y1, 8.3)
        self.assertTrue(p.pillar_footprints('basement'))
        self.assertEqual((p.UP_STAIR, p.DOWN_STAIR), ('Stairs', 'Stairs2_9'))
        w, _ = p.actor_world(p.DOWN_STAIR)
        self.assertAlmostEqual(float(w[:, 2].min()), -7.0, delta=0.5)   # the down flight reaches the basement floor

    def test_every_style_has_a_medium_basement(self):
        from ffxiv_furniture.interiors import InteriorProfile
        for s in STYLES:
            with self.subTest(style=s):
                self.assertGreater(InteriorProfile(s).polygon('basement').area, 150)


@unittest.skipUnless(HAVE, 'extracted interior meshes absent')
class LargeProfileTests(unittest.TestCase):
    def test_large_levels_floors_stairs_door(self):
        from ffxiv_furniture.interiors import LargeProfile
        p = LargeProfile('Shirogane')
        self.assertEqual(p.house_size, 'Large'); self.assertEqual(p.limit, 600)
        self.assertEqual(p.levels, ('ground', 'upper', 'basement'))
        self.assertEqual(p.door_xy, (0.0, 12.0))
        g, u, b = (p.polygon(l) for l in p.levels)
        self.assertGreater(g.area, 800); self.assertGreater(u.area, 600); self.assertGreater(b.area, 600)
        self.assertEqual([round(v) for v in g.bounds], [-20, -12, 20, 12])
        up = p.actors[p.UP_STAIR]; down = p.actors[p.DOWN_STAIR]
        self.assertEqual(up['translation_m'], [0.0, -8.0, 0.0]); self.assertTrue(up['mesh'].endswith('Stair4.uexp'))
        self.assertEqual(down['translation_m'][2], -7.0); self.assertTrue(down['mesh'].endswith('Stair3.uexp'))
        wu, _ = p.actor_world(p.UP_STAIR); self.assertGreater(float(wu[:, 2].max()), 6.5)   # main stair reaches the upper floor
        wd, _ = p.actor_world(p.DOWN_STAIR); self.assertLess(float(wd[:, 2].min()), -6.5)
        for lvl in p.levels:
            self.assertTrue(p.pillar_footprints(lvl), lvl)
            for role in ('room-frame', 'pillars'):
                self.assertTrue(p.record(role, lvl)['source'], (lvl, role))
        self.assertTrue(p.ceiling_lights['ground'])

    def test_every_style_builds_a_large_profile(self):
        from ffxiv_furniture.interiors import LargeProfile
        for s in STYLES:
            with self.subTest(style=s):
                p = LargeProfile(s)
                self.assertGreater(p.polygon('basement').area, 500)


@unittest.skipUnless(HAVE, 'extracted interior meshes absent')
class RoomSizeTests(unittest.TestCase):
    def test_medium_room_has_three_levels_and_basement_stair_facts(self):
        from ffxiv_furniture.deco.core import Room
        r = Room('Shirogane', 'Medium')
        self.assertEqual(r.levels, ('ground', 'upper', 'basement')); self.assertEqual(r.limit, 450)
        bs = r.stair_info()['basement']
        self.assertIsNotNone(bs['foot']); self.assertIsNotNone(bs['foot_access'])
        self.assertLess(bs['foot'].centroid.x, -3)   # Medium down stair runs along the west hole
        self.assertIn('basement', r.stair_summary()); self.assertTrue(r.pillars_by_level['basement'])
        self.assertIn('basement', r.stair_clearance())

    def test_large_room_levels_stairs_door_cap(self):
        from ffxiv_furniture.deco.core import Room
        r = Room('Mist', 'Large')
        self.assertEqual(r.levels, ('ground', 'upper', 'basement')); self.assertEqual(r.limit, 600)
        self.assertEqual(r.door_xy, (0.0, 12.0))
        si = r.stair_info()
        for k in ('foot', 'top', 'foot_access', 'arrival_access'):
            self.assertIsNotNone(si['up'][k], k)
        self.assertIsNotNone(si['basement']['foot_access']); self.assertIsNotNone(si['down']['entry_access'])
        s = r.stair_summary(); self.assertIn('up', s); self.assertIn('basement', s)
        self.assertTrue(all(r.walls_by_level[l] for l in r.levels))


SEEDS = Path(__file__).resolve().parents[1] / 'data/seeds'


@unittest.skipUnless(HAVE and (SEEDS / 'medium-seed.json').exists() and (SEEDS / 'large-seed.json').exists(), 'local seeds absent')
class SizeRenderTests(unittest.TestCase):
    def render(self, size, cameras, **kw):
        import json, tempfile
        from ffxiv_furniture.rendering.pipeline import run_pipeline
        lay = json.loads((SEEDS / f'{size.lower()}-seed.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as t:
            return run_pipeline(lay, Path(t), room_context=True, size=(160, 120), cameras=cameras, mirror_view=False, **kw)

    def test_medium_basement_context_renders_frame_floor_and_down_stair(self):
        cam = dict(name='bs', position=[14, -10, 6], target=[0, 0, -7], fov=60, cutaway=True, hide_above_z=-0.6)
        m = self.render('Medium', [cam], basement_context=True)
        ids = {o.get('instance_id') for o in m['objects'].values()}
        self.assertTrue({'bs-room-frame', 'bs-pillars', 'bs-floor-synthetic'} <= ids, ids)
        self.assertGreater(sum(m['views'][0]['visible_object_pixels'].values()), 5000)

    def test_large_renders_all_three_floors_stairs_and_door(self):
        cams = [dict(name='g', position=[0, 11, 2.0], target=[0, -12, 1.2], fov=85),
                dict(name='u', position=[0, 10, 9.0], target=[0, -12, 8.2], fov=85, upper=True),
                dict(name='b', position=[16, 10, -5.0], target=[-10, -8, -6.0], fov=85, basement=True)]
        m = self.render('Large', cams, basement_context=True, upper_context=True)
        ids = {o.get('instance_id') for o in m['objects'].values()}
        for need in ('room-frame', 'up-room-frame', 'bs-room-frame'):
            self.assertIn(need, ids)
        self.assertIn('main-door', m['objects'])
        actors = {o.get('source_actor') for o in m['objects'].values()}
        self.assertTrue({'MainStairs', 'BasementStairs'} <= actors, actors)
        for v in m['views']:
            self.assertGreater(sum(v['visible_object_pixels'].values()), 5000, v.get('camera'))


@unittest.skipUnless(HAVE and (SEEDS / 'large-seed.json').exists(), 'local seeds absent')
class ServerSizeTests(unittest.TestCase):
    def session(self, size, style='Shirogane'):
        import json, tempfile
        from ffxiv_furniture.deco.core import Catalog, Room, Session
        seed = json.loads((SEEDS / f'{size.lower()}-seed.json').read_text(encoding='utf-8'))
        return Session('t', Catalog(), Room(style, size), tempfile.mkdtemp(), seed_layout=seed)

    def test_cameras_cover_every_level_and_listing_reports_real_levels(self):
        from unittest.mock import patch
        from ffxiv_furniture.deco import server
        for size in ('Medium', 'Large'):
            s = self.session(size)
            with patch.object(server, '_boot', return_value=s), patch.object(server, '_sess', s):
                cams = server._cameras()
                for need in ('overview', 'top', 'entry', 'up_overview', 'up_top', 'bs_overview', 'bs_top', 'bs_stair'):
                    self.assertIn(need, cams, (size, need))
                self.assertTrue(cams['bs_top']['basement']); self.assertTrue(cams['up_top']['upper'])
                listing = server.list_interiors()['interiors']
                self.assertTrue(all(x['house_size'] == size and x['levels'] == ['ground', 'upper', 'basement'] for x in listing), listing[:1])
        s = self.session('Small') if (SEEDS / 'small-seed.json').exists() else None
        if s is not None:
            with patch.object(server, '_boot', return_value=s), patch.object(server, '_sess', s):
                self.assertEqual(server.list_interiors()['interiors'][0]['levels'], ['ground', 'basement'])

    def test_large_basement_furniture_renders_and_validates(self):
        import json
        from unittest.mock import patch
        from ffxiv_furniture.deco import server
        s = self.session('Large')
        r = s.apply([dict(op='place', instance_id='bench', name='Hingan Bench', position=[0, 0, -7.0], yaw_deg=0)])
        self.assertNotIn('OUTSIDE_FLOOR', [w['code'] for w in r.get('warnings', [])])
        self.assertEqual(s.inspect(level='basement')['level'], 'basement')
        with patch.object(server, '_boot', return_value=s), patch.object(server, '_sess', s):
            meta = json.loads(server.render(view='bs_top', width=160, height=120, lighting='off')[-1])
            self.assertIn('bench', [v['instance_id'] for v in meta['visible']])


class CeilingLightCutawayTests(unittest.TestCase):
    def test_plan_cutaway_drops_ceiling_lights_but_eye_level_keeps_them(self):
        import tempfile, numpy as np
        from pathlib import Path as _P
        from ffxiv_furniture.rendering.raster import render
        floor = {'id': 1, 'vertices': np.array([[-3, -3, 0], [3, -3, 0], [3, 3, 0], [-3, 3, 0]], float), 'triangles': np.array([[0, 1, 2], [0, 2, 3]]), 'role': 'furniture', 'flat_color': [0.5, 0.5, 0.5]}
        lamp = {'id': 2, 'vertices': np.array([[-1, -1, 2], [1, -1, 2], [1, 1, 2], [-1, 1, 2]], float), 'triangles': np.array([[0, 1, 2], [0, 2, 3]]), 'role': 'ceiling_light', 'flat_color': [0.9, 0.9, 0.9]}
        with tempfile.TemporaryDirectory() as t:
            plan = render([floor, lamp], {'position': [0, -0.01, 10], 'target': [0, 0, 0], 'fov': 60, 'cutaway': True}, _P(t) / 'a.jpg', size=(96, 64))
            eye = render([floor, lamp], {'position': [0, -0.01, 10], 'target': [0, 0, 0], 'fov': 60}, _P(t) / 'b.jpg', size=(96, 64))
        self.assertNotIn('2', plan['visible_object_pixels']); self.assertIn('2', eye['visible_object_pixels'])


@unittest.skipUnless(HAVE, 'extracted interior meshes absent')
class OpeningTests(unittest.TestCase):
    def test_map_windows_decode_and_match_small_hand_values(self):
        from ffxiv_furniture.interiors import map_openings, SmallProfile
        got = sorted((round(o['xy'][0]), round(o['xy'][1])) for o in map_openings('XIVSmallHouse') if o['kind'] == 'window')
        want = sorted((round(x), round(y)) for x, y, _z, _yaw in SmallProfile.WINDOWS)
        self.assertEqual(got, want)

    def test_openings_are_per_level(self):
        from ffxiv_furniture.interiors import InteriorProfile, LargeProfile, SmallProfile
        m = InteriorProfile('Shirogane')
        self.assertEqual(len([o for o in m.openings('ground') if o['kind'] == 'window']), 4)
        self.assertEqual(len([o for o in m.openings('upper') if o['kind'] == 'window']), 4)
        self.assertEqual(m.openings('basement'), [])
        self.assertEqual([o['xy'] for o in m.openings('ground') if o['kind'] == 'door'], [[0.0, 8.0]])
        up = m.openings('upper')[0]; self.assertAlmostEqual(up['z'][0], 8.0)
        L = LargeProfile('Shirogane')
        self.assertEqual(len(L.openings('ground')), 9); self.assertEqual(len(L.openings('upper')), 6)   # RivieraArchedWindow11-16
        self.assertEqual(SmallProfile('Shirogane').openings('basement'), [])

    def test_inspect_reports_level_openings(self):
        from ffxiv_furniture.deco.core import Room
        r = Room('Shirogane', 'Medium')
        self.assertEqual(len(r.openings_by_level['upper']), 4); self.assertEqual(r.openings_by_level['basement'], [])


@unittest.skipUnless(HAVE, 'extracted interior meshes absent')
class StairTreadTests(unittest.TestCase):
    def test_medium_shirogane_u_stair_foot_is_the_first_treads_not_the_whole_flight(self):
        from ffxiv_furniture.deco.core import Room
        r = Room('Shirogane', 'Medium'); si = r.stair_info()
        x0, y0, x1, y1 = si['up']['foot'].bounds
        self.assertLess(x1, 6.0); self.assertGreater(y0, 0.8); self.assertLess(y1, 5.5)       # flight 1 treads start at x~3.6, y 0.9..4.9
        bx0, by0, bx1, by1 = si['basement']['foot'].bounds
        self.assertGreater(bx0, -7.0); self.assertGreater(by0, 0.8); self.assertLess(by1, 5.5)   # basement arrival at x~-4
        hx0, hy0, hx1, hy1 = si['down']['hole'].bounds                                          # the stair well, not pillar notches
        self.assertAlmostEqual(hx1, -4.0, delta=0.6); self.assertAlmostEqual(hy0, 2.0, delta=0.6)
        self.assertFalse(si['up']['foot_access'].intersects(__import__('shapely.geometry', fromlist=['box']).box(0.2, -3.0, 1.5, 0.5)))


@unittest.skipUnless(HAVE and (SEEDS / 'medium-seed.json').exists(), 'local seeds absent')
class WindowRenderTests(unittest.TestCase):
    def test_medium_and_large_draw_their_decoded_windows(self):
        import json, tempfile
        from ffxiv_furniture.rendering.pipeline import run_pipeline
        for size, n in (('Medium', 8), ('Large', 14)):
            lay = json.loads((SEEDS / f'{size.lower()}-seed.json').read_text(encoding='utf-8'))
            with tempfile.TemporaryDirectory() as t:
                m = run_pipeline(lay, Path(t), room_context=True, upper_context=True, size=(96, 64), mirror_view=False,
                                 cameras=[dict(name='o', position=[0, -30, 30], target=[0, 0, 0], fov=60)])
            wins = [o for o in m['objects'].values() if str(o.get('instance_id', '')).startswith('native-window')]
            self.assertEqual(len(wins), n, (size, len(wins)))


class WindowCutawayTests(unittest.TestCase):
    def test_plan_cutaway_drops_wall_windows(self):
        import tempfile, numpy as np
        from pathlib import Path as _P
        from ffxiv_furniture.rendering.raster import render
        floor = {'id': 1, 'vertices': np.array([[-3, -3, 0], [3, -3, 0], [3, 3, 0], [-3, 3, 0]], float), 'triangles': np.array([[0, 1, 2], [0, 2, 3]]), 'role': 'furniture', 'flat_color': [0.5, 0.5, 0.5]}
        win = {'id': 2, 'vertices': np.array([[-1, -1, 2], [1, -1, 2], [1, 1, 2], [-1, 1, 2]], float), 'triangles': np.array([[0, 1, 2], [0, 2, 3]]), 'role': 'window', 'flat_color': [0.9, 0.9, 0.9]}
        with tempfile.TemporaryDirectory() as t:
            plan = render([floor, win], {'position': [0, -0.01, 10], 'target': [0, 0, 0], 'fov': 60, 'cutaway': True}, _P(t) / 'a.jpg', size=(96, 64))
            eye = render([floor, win], {'position': [0, -0.01, 10], 'target': [0, 0, 0], 'fov': 60}, _P(t) / 'b.jpg', size=(96, 64))
        self.assertNotIn('2', plan['visible_object_pixels']); self.assertIn('2', eye['visible_object_pixels'])


if __name__ == '__main__':
    unittest.main()
