"""Regression tests for the render-sweep bugs (B1-B16): lighting, level handling, cameras, fallbacks, manifest honesty."""
import json
import re
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image

from ffxiv_furniture.rendering.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[1]
SIZE = (96, 64)
CAM = [dict(name='o', position=[0, -20, 12], target=[0, 0, 0], fov=60)]


def seed(size):
    return json.loads((ROOT / f'data/seeds/{size.lower()}-seed.json').read_text(encoding='utf-8'))


def run(layout, cameras=CAM, **kw):
    with tempfile.TemporaryDirectory() as t:
        return run_pipeline(layout, Path(t), size=SIZE, cameras=cameras, mirror_view=False, **kw)


def ids(manifest):
    return [o.get('instance_id') for o in manifest['objects'].values()]


class LightingModuleTests(unittest.TestCase):
    def test_b3_non_lights_are_not_emitters(self):
        from ffxiv_furniture.rendering.lighting import emitter_light
        for name in ('Flame Desk', 'Flame Armoire', 'Flame Trophy (Left)', 'Loss, Fire, Faith Reproduction',
                     'Moonfire Faire MMXIV Advertisement', 'Immortal Flames Banner', 'Trophy of Light', 'Firewood',
                     'Firebloom', 'Flame Storage Bench', 'Sultana and Flame General Portrait'):
            self.assertIsNone(emitter_light(name), name)

    def test_b3_real_lamps_still_emit(self):
        from ffxiv_furniture.rendering.lighting import emitter_light
        for name in ('Classic Table Lamp', 'Alchemical Lantern', 'Assorted Candles', 'Far Eastern Brazier', 'Campfire',
                     'Manor Fireplace', 'Iron Torch', 'Crystal Chandelier', 'Pendant Wall Light', 'Cooking Stove',
                     'Riviera Lamppost', 'Cosmolamp', 'Pumpkin Candlestand', 'Candlelit Sundries',
                     'Riviera Path Light', 'Overhead Studio Light', 'Illuminated Tree', "Cold Knight's Cookfire"):
            self.assertIsNotNone(emitter_light(name), name)

    def test_b3_decoded_emissive_material_overrides_name(self):
        from ffxiv_furniture.rendering.lighting import emitter_light
        self.assertIsNotNone(emitter_light('Flame Desk', has_emissive_material=True))

    def test_b13_resolve_mood_accepts_every_form(self):
        from ffxiv_furniture.rendering.lighting import resolve_mood
        dusk = resolve_mood('dusk')
        self.assertEqual(resolve_mood(True), dusk)
        self.assertEqual(resolve_mood('warm'), dusk)
        custom = dict(lo=(.1, .1, .1), hi=(.2, .2, .2), exposure=1.0, scale=1.0)
        self.assertEqual(resolve_mood(custom)['exposure'], 1.0)
        with self.assertRaises(ValueError):
            resolve_mood('nope')

    def test_b4_light_budget_reports_and_strips_dropped_glow(self):
        from ffxiv_furniture.rendering.lighting import apply_light_budget
        lights = [dict(id=i, pos=[0, 0, 0], color=[1, 1, 1], intensity=float(i), radius=1.0) for i in range(1, 71)]
        meshes = [dict(id=i, emissive=(1, 1, 1)) for i in range(1, 71)]
        kept, dropped, message = apply_light_budget(lights, meshes, cap=64)
        self.assertEqual((len(kept), len(dropped)), (64, 6))
        self.assertIn('kept 64', message); self.assertIn('dropped 6', message)
        self.assertEqual({m['id'] for m in meshes if not m.get('emissive')}, {1, 2, 3, 4, 5, 6})
        self.assertEqual(apply_light_budget(lights[:3], meshes, cap=64)[2], None)

    def test_b13_exterior_accepts_true_and_dict_moods(self):
        layout = seed('Medium')
        for mood in (True, 'warm', dict(lo=(.1, .1, .1), hi=(.2, .2, .2), exposure=1.2, scale=1.0)):
            m = run(layout, cameras=None, scope='exterior', lighting=mood)
            self.assertTrue(m['views'][0]['camera']['lighting'] is not None, mood)


class CeilingLightTests(unittest.TestCase):
    def test_b1_point_lights_follow_spot_xy(self):
        m = run(seed('Large'), room_context=True, lighting='dusk')
        lights = m['views'][0]['camera']['lighting']['lights']
        xs = sorted(round(l['pos'][0]) for l in lights)
        self.assertIn(14, xs); self.assertIn(-14, xs)
        for l in lights:
            if abs(l['pos'][0]) > 13:
                self.assertAlmostEqual(l['pos'][2], 6.5 - 1.2, places=3)

    def test_b2_no_ceiling_light_for_absent_levels(self):
        for size, kw in (('Small', dict(upper_context=True)), ('Apartment', dict(upper_context=True, basement_context=True))):
            m = run(seed(size), room_context=True, **kw)
            names = ids(m)
            self.assertFalse([n for n in names if n and n.startswith('ceiling-light-upper')], (size, names))
            if size == 'Apartment':
                self.assertFalse([n for n in names if n and n.startswith('ceiling-light-basement')], names)
            self.assertTrue(any('no upper' in w.lower() for w in m['warnings']), m['warnings'])

    def test_b15_instance_ids_are_size_independent(self):
        for size in ('Medium', 'Large'):
            names = set(ids(run(seed(size), room_context=True)))
            self.assertTrue({'stair-up', 'stair-down', 'railing-ground', 'railing-upper'} <= names, (size, sorted(n for n in names if n)))

    def test_b15_ceiling_lights_named_consistently(self):
        names = [n for n in ids(run(seed('Large'), room_context=True, upper_context=True)) if n and n.startswith('ceiling-light')]
        self.assertTrue(len(names) >= 5, names)
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(all(re.fullmatch(r'ceiling-light-(ground|upper|basement)-\d+', n) for n in names), names)

    def test_folder_resolves_special_characters(self):
        from ffxiv_furniture.rendering.house_materials import fixture_folder
        from ffxiv_furniture.config import catalog_path
        with sqlite3.connect(catalog_path().as_uri() + '?mode=ro', uri=True) as db:
            self.assertEqual(fixture_folder(db, 'CeilingLight', dict(name='Flame Ceiling Fan & Lamp', itemId=6471)), 'FlameCeilingFan0x26Lamp')
            self.assertEqual(fixture_folder(db, 'CeilingLight', dict(name="Watcher's Palace Ceiling Lamp")), 'Watcher_sPalaceCeilingLamp')
            self.assertEqual(fixture_folder(db, 'Wallpaper', dict(name='Palace of the Dead Interior Wall')), 'PalaceOfTheDeadInteriorWall')
        self.assertEqual(fixture_folder(None, 'CeilingLight', dict(name='Flame Ceiling Fan & Lamp')), 'FlameCeilingFan0x26Lamp')


class StairSectionTests(unittest.TestCase):
    def test_b5_cut_stairs_default_is_relative_to_plan_level(self):
        cams = [dict(name='up', position=[0, .01, 40], target=[0, 0, 7], fov=40, cutaway=True, hide_below_z=6.9),
                dict(name='gr', position=[0, .01, 40], target=[0, 0, 0], fov=40, cutaway=True),
                dict(name='bs', position=[0, .01, 40], target=[0, 0, -7], fov=40, cutaway=True, hide_above_z=-0.6),
                dict(name='explicit', position=[0, .01, 40], target=[0, 0, 0], fov=40, cutaway=True, cut_stairs_z=1.5)]
        m = run(seed('Medium'), cameras=cams, room_context=True, upper_context=True, basement_context=True)
        cut = {v['camera']['name']: v['camera'].get('cut_stairs_z') for v in m['views']}
        self.assertAlmostEqual(cut['up'], 10.0); self.assertAlmostEqual(cut['gr'], 3.0)
        self.assertAlmostEqual(cut['bs'], -4.0); self.assertAlmostEqual(cut['explicit'], 1.5)


class DefaultCameraTests(unittest.TestCase):
    def test_b6_entry_camera_is_inside_the_room(self):
        for size in ('Small', 'Large', 'Apartment'):
            m = run(seed(size), cameras=None, room_context=True)
            entry = next(v for v in m['views'] if v['camera']['name'] == 'entry')
            pixels = entry['visible_object_pixels']; total = sum(pixels.values())
            walls = sum(n for k, n in pixels.items() if m['objects'][k].get('instance_id') in ('walls', 'room-frame', 'ceiling'))
            floor = sum(n for k, n in pixels.items() if m['objects'][k].get('instance_id') in ('floor', 'floor-synthetic'))
            self.assertLess(walls / total, 0.9, (size, pixels)); self.assertGreater(floor, 0, size)


class CameraValidationTests(unittest.TestCase):
    def test_b10_bad_cameras_raise_valueerror_before_any_render(self):
        layout = seed('Medium')
        for bad in (dict(name='x', position=[0, 0, 1], target=[1, 0, 1]), [], [CAM[0]] * 9, [1], 'x'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                run(layout, cameras=bad, room_context=True)
        with self.assertRaises(ValueError):
            run(seed('Medium'), cameras=dict(name='x'), scope='exterior')


class FallbackTests(unittest.TestCase):
    def test_b7_missing_floor_wall_fixture_falls_back_with_warning(self):
        layout = seed('Medium')
        layout['interiorFixture'] = [f for f in layout['interiorFixture'] if not (f['type'] == 'Wall' and f['level'] == 'Ground Floor')]
        m = run(layout, room_context=True, rough_room_finish=True)
        self.assertTrue(any('finish' in w.lower() and 'unavailable' in w.lower() for w in m['warnings']), m['warnings'])

    def test_b8_substituted_levels_are_warned_and_marked(self):
        layout = seed('Medium')
        layout['interiorFixture'] = [f for f in layout['interiorFixture'] if not (f['type'] in ('Floor', 'Wall') and f['level'] in ('Basement', 'Upper Floor'))]
        m = run(layout, room_context=True, rough_room_finish=True, basement_context=True, upper_context=True)
        joined = ' '.join(m['warnings'])
        self.assertIn('Basement', joined); self.assertIn('Upper Floor', joined); self.assertIn('substitut', joined)
        marked = [o for o in m['objects'].values() if str(o.get('instance_id', '')).startswith(('bs-', 'up-')) and 'texture' in o]
        self.assertTrue(marked)
        self.assertTrue(all(o['texture'].get('substituted_from') == 'Ground Floor' for o in marked if o['instance_id'] in ('bs-floor', 'bs-walls', 'up-floor', 'up-walls')))

    def test_b8_synthetic_basement_floor_has_provenance(self):
        m = run(seed('Medium'), room_context=True, rough_room_finish=True, basement_context=True)
        synth = [o for o in m['objects'].values() if o.get('instance_id') == 'bs-floor-synthetic']
        if synth:
            self.assertIn('texture', synth[0])

    def test_b9_missing_window_fixture_warns(self):
        layout = seed('Small')
        layout['exteriorFixture'] = [f for f in layout['exteriorFixture'] if f['type'] != 'Window']
        m = run(layout, room_context=True)
        self.assertTrue(any('window' in w.lower() and 'no window' in w.lower() for w in m['warnings']), m['warnings'])

    def test_b14_missing_item_colors_table_is_reported(self):
        from ffxiv_furniture.rendering.common import load_fallback_colours
        db = sqlite3.connect(':memory:'); warnings = []
        self.assertEqual(load_fallback_colours(db, warnings), {})
        self.assertTrue(any('item_colors' in w for w in warnings))

    def test_b14_decode_failures_aggregate_into_one_warning(self):
        from ffxiv_furniture.rendering.common import coverage_warnings
        coverage = [dict(item_id=1, notes=['No unique cross-validated section layout'], material_slots=2, textured_slots=1,
                         materials=[dict(warning='No explicit Base texture parameter'), dict(warning=None)]),
                    dict(item_id=2, notes=[], material_slots=1, textured_slots=1, materials=[dict(warning=None)])]
        out = coverage_warnings(coverage)
        self.assertEqual(len(out), 1)
        self.assertIn('1 of 3', out[0]); self.assertIn('No explicit Base texture parameter', out[0]); self.assertIn('section layout', out[0])
        self.assertEqual(coverage_warnings([coverage[1]]), [])


class ManifestTests(unittest.TestCase):
    def test_b11_pixel_counts_are_not_called_triangle_updates(self):
        m = run(seed('Medium'), room_context=True)
        for v in m['views']:
            self.assertNotIn('visible_triangle_updates', v); self.assertNotIn('textured_triangle_updates', v)

    def test_b12_banner_pixels_are_not_counted(self):
        from ffxiv_furniture.rendering.raster import render, BANNER_HEIGHT
        mesh = [dict(id=5, vertices=np.array([[-50, 2, -50], [50, 2, -50], [0, 2, 80]], float), triangles=[(0, 1, 2)], role='furniture')]
        with tempfile.TemporaryDirectory() as t:
            r = render(mesh, dict(position=[0, 0, 0], target=[0, 1, 0], fov=70), Path(t) / 'v.jpg', size=(96, 64), debug_buffers=True)
            idm = np.asarray(Image.open(Path(t) / 'v-ids.png'))
        self.assertEqual(r['visible_object_pixels']['5'], int((idm[BANNER_HEIGHT:] == 5).sum()))
        self.assertLess(r['visible_object_pixels']['5'], int((idm == 5).sum()))

    def test_b16_exterior_manifest_has_interior_keys(self):
        interior = run(seed('Medium'), room_context=True)
        exterior = run(seed('Medium'), cameras=None, scope='exterior')
        self.assertFalse(set(interior) - set(exterior), sorted(set(interior) - set(exterior)))
        self.assertTrue(exterior['mirror_view'] is False and exterior['display_gamma'] == 0.7)

    def test_b16_exterior_default_dye_mode_is_flagged(self):
        m = run(seed('Medium'), cameras=None, scope='exterior', dye_mode='default')
        self.assertTrue(any('dye_mode' in w and 'default' in w for w in m['warnings']), m['warnings'])
        self.assertEqual(m['dye_mode'], 'default')


class GpuResourceTests(unittest.TestCase):
    def test_framebuffer_released_when_draw_raises(self):
        import ffxiv_furniture.rendering.raster_gpu as g
        ctx, _ = g._Gpu.context()
        bad = [dict(id=0, vertices=np.array([[0, 2, 0], [1, 2, 0], [0, 2, 1]], float), triangles=[(0, 1, 2)])]   # id 0 -> ValueError mid-render
        before = len(ctx.objects) if hasattr(ctx, 'objects') else None
        from unittest.mock import patch
        allocated = []
        original = ctx.framebuffer
        def track(*args, **kwargs):
            fbo = original(*args, **kwargs)
            allocated.append((fbo, (*fbo.color_attachments, fbo.depth_attachment)))
            return fbo
        with patch.object(ctx, 'framebuffer', side_effect=track):
            for _ in range(3):
                with tempfile.TemporaryDirectory() as t, self.assertRaises(ValueError):
                    g.render_gpu(bad, dict(position=[0, 0, 0], target=[0, 1, 0]), Path(t) / 'v.jpg', size=(64, 64))
        self.assertEqual(len(allocated), 3)
        for fbo, textures in allocated:
            for resource in (fbo, *textures):
                self.assertEqual(type(resource.mglo).__name__, 'InvalidObject')
        if before is not None:
            self.assertEqual(len(ctx.objects), before)
        self.assertEqual(g._Gpu.live_framebuffers, 0)


if __name__ == '__main__':
    unittest.main()
