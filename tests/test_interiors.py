"""Interior profiles, native transforms, floor polygons, openings, stairs and span rules."""
import numpy as np
import unittest
from ffxiv_furniture import interiors as I
from ffxiv_furniture.deco.core import DecoError, Room
from ffxiv_furniture.interiors import InteriorProfile, STYLES, level_for_span, medium_actor_transforms, transform_points
from shapely.geometry import Polygon
from shapely.ops import unary_union
from tests.support import needs_meshes
from unittest.mock import patch

class StructureRecordCacheTests(unittest.TestCase):
    def test_same_size_restored_mtime_invalidates_both_packages(self):
        import os
        import tempfile
        from pathlib import Path
        from ffxiv_furniture.house_profiles import structure_record
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'HouseAssets/InteriorStyles/test.uexp'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'body')
            header = path.with_suffix('.uasset'); header.write_bytes(b'head')
            def decode(p):
                return {'bytes': p.read_bytes() + p.with_suffix('.uasset').read_bytes()}
            with patch('ffxiv_furniture.config.source_path', return_value=root), patch('ffxiv_furniture.geometry.read_static_mesh_bounds', side_effect=decode):
                previous = structure_record(root, 'test.uexp')
                for target in (path, header):
                    stat = target.stat(); target.write_bytes(b'next')
                    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                    current = structure_record(root, 'test.uexp')
                    self.assertNotEqual(current, previous)
                    self.assertEqual(current, decode(path))
                    previous = current


class OpeningOrientationTests(unittest.TestCase):

    def test_openings_follow_their_wall_including_wrapped_native_yaw(self):
        rows = [tuple(sorted(dict(actor='W', kind='window', x=3.0, y=8.0, z=1.0, yaw=y).items())) for y in (-179.99997, 180.0, 0.0, 1e-05)]
        rows += [tuple(sorted(dict(actor='E', kind='window', x=12.0, y=0.0, z=1.0, yaw=y).items())) for y in (90.0, -90.0, 270.0)]
        with patch.object(I, '_map_openings', return_value=tuple(rows)):
            self.assertEqual([o['along'] for o in I.map_openings('X')], ['x'] * 4 + ['y'] * 3)
        for cls, hx, hy in ((I.InteriorProfile, 12.0, 8.0), (I.LargeProfile, 20.0, 12.0)):
            p = cls('Shirogane')
            seen = set()
            for lv in p.levels:
                for o in p.openings(lv):
                    x, y = o['xy']
                    if abs(abs(y) - hy) < 0.6:
                        self.assertEqual(o['along'], 'x', (cls.__name__, o))
                        seen.add('x')
                    elif abs(abs(x) - hx) < 0.6:
                        self.assertEqual(o['along'], 'y', (cls.__name__, o))
                        seen.add('y')
            self.assertEqual(seen, {'x', 'y'}, cls.__name__)
            self.assertTrue(any((o['kind'] == 'door' and o['along'] == 'x' for o in p.openings('ground'))), cls.__name__)

@unittest.skipUnless(I.BASE.exists(), 'extracted interior meshes absent')
class StairFootprintLevelTests(unittest.TestCase):

    def test_stair_footprints_stay_within_the_level_band(self):
        import numpy as np
        from shapely.geometry import MultiPoint
        for p, names in ((I.InteriorProfile('Shirogane'), ('Stairs', 'Stairs2_9')), (I.LargeProfile('Shirogane'), ('MainStairs', 'BasementStairs'))):
            for lv in p.levels:
                z0 = p.level_z[lv]
                want = []
                for n in names:
                    w, _ = p.actor_world(n)
                    pts = w[(w[:, 2] >= z0 - 0.3) & (w[:, 2] < z0 + 6.5), :2]
                    if len(pts):
                        want.append(MultiPoint(pts).convex_hull)
                got = p.stair_footprints(lv)
                self.assertEqual(len(got), len(want), (type(p).__name__, lv))
                for g, w_ in zip(got, want):
                    self.assertLess(g.symmetric_difference(w_).area, 1e-09, (type(p).__name__, lv))
            self.assertEqual(len(p.stair_footprints('basement')), 1, 'only the ground->basement flight reaches the basement panel')
        s = I.SmallProfile('Shirogane')
        self.assertEqual(s.stair_footprints('upper'), [])
        self.assertEqual(len(s.stair_footprints('basement')), 1)
        self.assertGreater(s.stair_footprints('basement')[0].area, s.stair_footprints('ground')[0].area)

    def test_unknown_level_is_empty_everywhere(self):
        for p in (I.InteriorProfile('Shirogane'), I.SmallProfile('Shirogane'), I.LargeProfile('Shirogane'), I.ApartmentProfile('Shirogane')):
            self.assertEqual(p.stair_footprints('roof'), [], type(p).__name__)
            self.assertEqual(p.pillar_footprints('roof'), [], type(p).__name__)
            self.assertTrue(p.polygon('roof').is_empty, type(p).__name__)

class SummaryAndOpeningTextTests(unittest.TestCase):

    @unittest.skipUnless(I.BASE.exists(), 'extracted interior meshes absent')
    def test_summaries_report_every_level(self):
        self.assertEqual(I.SmallProfile('Shirogane').summary()['levels'], {'ground': 0.0, 'basement': -7.0})
        self.assertEqual(I.ApartmentProfile('Shirogane').summary()['levels'], {'ground': 0.0})
        self.assertEqual(I.LargeProfile('Shirogane').summary()['levels'], {'ground': 0.0, 'upper': 7.0, 'basement': -7.0})
        self.assertEqual(I.InteriorProfile('Shirogane').summary()['levels'], {'ground': 0.0, 'upper': 7.0, 'basement': -7.0})

    @unittest.skipUnless(I.BASE.exists(), 'extracted interior meshes absent')
    def test_large_limitations_do_not_claim_windows_are_undecoded(self):
        text = ' '.join(I.LargeProfile('Shirogane').summary()['limitations'])
        self.assertNotIn('not decoded', text)
        self.assertEqual(len(I.LargeProfile('Shirogane').openings('ground')), 9)

    @unittest.skipUnless(I.BASE.exists(), 'extracted interior meshes absent')
    def test_small_actors_do_not_share_or_leak_mutable_lists(self):
        p = I.SmallProfile('Shirogane')
        a = p.actors
        self.assertIsNot(a['Stairs2_9']['scale'], a['StairCeiling']['scale'])
        self.assertIsNot(a['Stairs2_9']['translation_m'], a['StairCeiling']['translation_m'])
        s = p.summary()
        s['stairs']['Stairs2_9']['scale'][0] = 9
        s['stairs']['Stairs2_9']['translation_m'][0] = 99
        self.assertEqual(p.actors['Stairs2_9']['scale'], [1.0, 1.0, 1.0])
        self.assertEqual(p.actors['Stairs2_9']['translation_m'][0], 8.0)

    @unittest.skipUnless(I.BASE.exists(), 'extracted interior meshes absent')
    def test_apartment_entry_door_is_assumed_on_ground_only(self):
        p = I.ApartmentProfile('Shirogane')
        g = p.openings('ground')
        self.assertEqual([(o['kind'], o['xy'], o['along'], o.get('assumed')) for o in g], [('door', [0.0, 8.0], 'x', True)])
        self.assertEqual(p.openings('basement'), [])
        self.assertEqual(p.openings('upper'), [])

    @unittest.skipUnless(I.BASE.exists(), 'extracted interior meshes absent')
    def test_list_interiors_is_per_size(self):
        self.assertEqual({x['house_size'] for x in I.list_interiors('Small')}, {'Small'})
        self.assertEqual([x['style'] for x in I.list_interiors('Small')], list(I.SMALL_STYLES))
        self.assertEqual(I.list_interiors('Small')[0]['levels'], ['ground', 'basement'])
        self.assertEqual(I.list_interiors('Apartment')[0]['levels'], ['ground'])
        self.assertEqual(I.list_interiors('Large')[0]['levels'], ['ground', 'upper', 'basement'])
        self.assertEqual([x['style'] for x in I.list_interiors()], list(I.STYLES))

class LevelForSpanTests(unittest.TestCase):

    def test_rule(self):
        cases = {(0.0, 0.02): 'ground', (-0.4, 1.0): 'ground', (6.2, 6.5): 'ground', (7.0, 8.0): 'upper', (6.4, 9.0): 'upper', (-7.0, -6.0): 'basement', (-3.38, -2.66): 'basement', (-4.4, -2.69): 'basement', (-1.1, -0.9): 'basement', (-2.4, 3.6): 'ground'}
        for (zb, zt), want in cases.items():
            with self.subTest(zb=zb, zt=zt):
                self.assertEqual(level_for_span(zb, zt), want)

@needs_meshes
class MediumBasementTests(unittest.TestCase):

    def test_medium_has_basement_level_from_native_frame_and_stair(self):
        from ffxiv_furniture.interiors import InteriorProfile
        p = InteriorProfile('Shirogane')
        self.assertEqual(p.levels, ('ground', 'upper', 'basement'))
        self.assertEqual(p.level_z['basement'], -7.0)
        b = p.polygon('basement')
        x0, y0, x1, y1 = b.bounds
        self.assertGreater(b.area, 200)
        self.assertLessEqual(b.area, 24 * 16 + 1)
        self.assertGreaterEqual(x0, -12.3)
        self.assertLessEqual(x1, 12.3)
        self.assertGreaterEqual(y0, -8.3)
        self.assertLessEqual(y1, 8.3)
        self.assertTrue(p.pillar_footprints('basement'))
        self.assertEqual((p.UP_STAIR, p.DOWN_STAIR), ('Stairs', 'Stairs2_9'))
        w, _ = p.actor_world(p.DOWN_STAIR)
        self.assertAlmostEqual(float(w[:, 2].min()), -7.0, delta=0.5)

    def test_every_style_has_a_medium_basement(self):
        from ffxiv_furniture.interiors import InteriorProfile
        for s in STYLES:
            with self.subTest(style=s):
                self.assertGreater(InteriorProfile(s).polygon('basement').area, 150)

@needs_meshes
class LargeProfileTests(unittest.TestCase):

    def test_large_levels_floors_stairs_door(self):
        from ffxiv_furniture.interiors import LargeProfile
        p = LargeProfile('Shirogane')
        self.assertEqual(p.house_size, 'Large')
        self.assertEqual(p.limit, 600)
        self.assertEqual(p.levels, ('ground', 'upper', 'basement'))
        self.assertEqual(p.door_xy, (0.0, 12.0))
        g, u, b = (p.polygon(l) for l in p.levels)
        self.assertGreater(g.area, 800)
        self.assertGreater(u.area, 600)
        self.assertGreater(b.area, 600)
        self.assertEqual([round(v) for v in g.bounds], [-20, -12, 20, 12])
        up = p.actors[p.UP_STAIR]
        down = p.actors[p.DOWN_STAIR]
        self.assertEqual(up['translation_m'], [0.0, -8.0, 0.0])
        self.assertTrue(up['mesh'].endswith('Stair4.uexp'))
        self.assertEqual(down['translation_m'][2], -7.0)
        self.assertTrue(down['mesh'].endswith('Stair3.uexp'))
        wu, _ = p.actor_world(p.UP_STAIR)
        self.assertGreater(float(wu[:, 2].max()), 6.5)
        wd, _ = p.actor_world(p.DOWN_STAIR)
        self.assertLess(float(wd[:, 2].min()), -6.5)
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

@needs_meshes
class OpeningTests(unittest.TestCase):

    def test_map_windows_decode_and_match_small_hand_values(self):
        from ffxiv_furniture.interiors import map_openings, SmallProfile
        got = sorted(((round(o['xy'][0]), round(o['xy'][1])) for o in map_openings('XIVSmallHouse') if o['kind'] == 'window'))
        want = sorted(((round(x), round(y)) for x, y, _z, _yaw in SmallProfile.WINDOWS))
        self.assertEqual(got, want)

    def test_openings_are_per_level(self):
        from ffxiv_furniture.interiors import InteriorProfile, LargeProfile, SmallProfile
        from ffxiv_furniture.deco.core import Room
        m = InteriorProfile('Shirogane')
        self.assertEqual(len([o for o in m.openings('ground') if o['kind'] == 'window']), 4)
        self.assertEqual(len([o for o in m.openings('upper') if o['kind'] == 'window']), 4)
        self.assertEqual(m.openings('basement'), [])
        self.assertEqual([o['xy'] for o in m.openings('ground') if o['kind'] == 'door'], [[0.0, 8.0]])
        self.assertAlmostEqual(m.openings('upper')[0]['z'][0], 8.0)
        L = LargeProfile('Shirogane')
        self.assertEqual(len(L.openings('ground')), 9)
        self.assertEqual(len(L.openings('upper')), 6)
        self.assertEqual(SmallProfile('Shirogane').openings('basement'), [])
        r = Room('Shirogane', 'Medium')
        self.assertEqual(len(r.openings_by_level['upper']), 4)
        self.assertEqual(r.openings_by_level['basement'], [])

class InteriorGeometryTests(unittest.TestCase):

    def test_unknown_style_never_silently_uses_shirogane(self):
        with self.assertRaises(DecoError):
            Room('Dark Minimalist')
        with self.assertRaises(ValueError):
            InteriorProfile('unknown')

    def test_named_overrides_not_duplicate_global_transform(self):
        a = medium_actor_transforms()
        self.assertEqual(a['Stairs']['default']['translation_m'], [8, 5, 0])
        self.assertEqual(a['Stairs']['default']['yaw_degrees'], 0)
        self.assertEqual(a['Stairs']['overrides']['Minimalist']['scale'], [-1, 1, 1])
        self.assertEqual(a['Stairs2_9']['default']['translation_m'], [-8, 5, -7])
        self.assertEqual(a['Stairs2_9']['default']['scale'], [-1, 1, 1])

    def test_full_scale_rotation_translation(self):
        a = dict(scale=[-1, 2, 3], yaw_degrees=90, translation_m=[7, 4, 0])
        np.testing.assert_allclose(transform_points([[1, 2, 3]], a), [[3, 3, 9]], atol=1e-12)

    def test_native_stair_upper_landing_adjacency_all_styles(self):
        for style in STYLES:
            p = InteriorProfile(style)
            v, t = p.actor_world('Stairs')
            landing = unary_union([g for tr in t if all((abs(v[i, 2] - 7) < 0.18 for i in tr)) and (g := Polygon(v[tr, :2])).area > 0.01])
            self.assertGreater(landing.area, 0.001, style)
            self.assertLess(landing.distance(p.polygon('upper')), 0.02, style)
            self.assertTrue(np.isfinite(v).all(), style)
            self.assertLess(v[:, 2].min(), 0.1, style)
            self.assertGreater(v[:, 2].max(), 7, style)

    def test_ceiling_material_is_selected_per_style_not_shirogane_for_all(self):
        for style in STYLES:
            if style == 'DarkMinimalist':
                with self.assertRaises(ValueError):
                    InteriorProfile(style).ceiling_texture()
            else:
                texture = InteriorProfile(style).ceiling_texture()
                self.assertIn('/' + style + '/', texture['provenance']['texture'].replace(chr(92), '/'))
                self.assertEqual(texture['provenance']['style'], style)
