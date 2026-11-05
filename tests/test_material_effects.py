"""Material effects the renderer used to drop (user request: support the missing effects; lighting/shadows stay out of scope).
- glass slots (/Game/Materials/M_MasterGlass referenced directly, file not extracted) -> translucent pass, not an opaque flat panel
- two-sided opacity-mask and foliage-vertex-colour masters -> alpha cutout (flower sets read as solid 'fences')
- emissive masters -> per-slot emissive colour (only the bulb/flame slot glows, not the whole lamp body)
- MI with an unsupported property layout -> base guessed from its only _d texture import (was a flat fallback colour)"""
import unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GA = ROOT / 'data/gameassets-legacy/MakePlace/Content/GameAssets'
HAVE = GA.exists() and any(GA.glob('**/ArmamentShowcase'))


def _load(folder):
    from ffxiv_furniture.geometry import read_static_mesh_bounds
    from ffxiv_furniture.rendering.assets import Assets
    f = next(GA.glob(f'**/{folder}'))
    rec = read_static_mesh_bounds(f / f'{folder}.uexp'); rec['item_id'] = -11
    a = Assets([rec], ROOT / 'outputs/render-pipeline/cache', mi_tint=True)
    return a.load(-11)


@unittest.skipUnless(HAVE, 'native furniture assets not extracted')
class MaterialEffectTests(unittest.TestCase):
    def test_glass_slot_is_translucent_not_missing(self):
        m = _load('ArmamentShowcase')
        glass = [d for d in m['materials'] if 'M_MasterGlass' in d['native_reference']]
        self.assertEqual(len(glass), 1)
        self.assertTrue(glass[0].get('glass'))
        self.assertGreater(glass[0]['glass_alpha'], 0.0); self.assertLess(glass[0]['glass_alpha'], 0.5)
        self.assertNotIn('No such file', glass[0].get('warning') or '')

    def test_waterfall_partition_water_is_visible_translucent_water(self):
        # Waterfall Partition: curtain slot binds M_Rain, basin glow binds a standalone M_BrightWater material.
        # Both used to vanish (alpha 0.12) or turn into an opaque brown fallback block.
        m = _load('WaterfallPartition')
        by = {d['native_reference'].rsplit('/', 1)[-1].split('.')[0]: d for d in m['materials']}
        rain, water = by['M_Rain'], by['M_BrightWater']
        self.assertTrue(rain.get('glass')); self.assertGreaterEqual(rain['glass_alpha'], 0.25)
        self.assertTrue(water.get('glass')); self.assertGreaterEqual(water['glass_alpha'], 0.4)
        r, g, b = water['flat_color']; self.assertGreater(b, r + 0.2, 'water reads blue, not the brown fallback')
        self.assertTrue(water.get('emissive'))

    def test_masked_masters_are_cut_out(self):
        for folder, slot in (('WalnutFlowerVases', 0), ('BluebirdMobile', 0)):
            with self.subTest(folder=folder):
                self.assertTrue(_load(folder)['materials'][slot].get('cutout'))

    def test_emissive_only_on_emissive_slots(self):
        m = _load('ClassicTableLamp')
        par = [str(d.get('parent', '')).split('.')[-1] for d in m['materials']]
        glow = [i for i, d in enumerate(m['materials']) if d.get('emissive')]
        self.assertTrue(glow)
        self.assertTrue(all(par[i].startswith('M_MasterEmissive') for i in glow), par)   # lamp body (Tint/Mat slots) does not glow
        full = [i for i in glow if par[i] == 'M_MasterEmissive']; masked = [i for i in glow if par[i] != 'M_MasterEmissive']
        self.assertTrue(full and masked, par)
        e = m['materials'][full[0]]['emissive']; self.assertEqual(len(e), 3); self.assertGreater(e[0], e[2])   # warm tint, not white
        self.assertLess(max(m['materials'][masked[0]]['emissive']), max(e))

    def test_tint_mi_without_tint_uses_master_default(self):
        if not (ROOT / 'data/gameassets-legacy/MakePlace/Content/Materials/M_MasterTint.uexp').exists(): self.skipTest('master materials not extracted')
        from ffxiv_furniture.rendering import native
        self.assertEqual([round(x, 4) for x in native.master_default_tint(ROOT / 'data/gameassets-legacy/MakePlace/Content/Materials/M_MasterTint.uasset')], [0.3613, 0.2423, 0.107])
        d = _load('WalnutFlowerVases')['materials'][2]   # walnut vase bodies: M_MasterTint MI with no Tint (rendered white before)
        self.assertEqual(d.get('mi_tint_source'), 'parent-default')
        rgb = np.asarray(d['texture'])[..., :3].reshape(-1, 3).mean(0)
        self.assertGreater(rgb[0], rgb[2] + 20, rgb)

    def test_unsupported_mi_layout_gets_guessed_base(self):
        m = _load('CarbuncleLantern')
        d = m['materials'][1]
        self.assertIsNotNone(d['texture'])
        self.assertIn('guessed', d['warning'])


class GlassRasterTests(unittest.TestCase):
    def test_glass_blends_and_keeps_object_behind_in_id_buffer(self):
        import tempfile
        from ffxiv_furniture.rendering.raster_gpu import render_gpu
        quad = lambda y, i, extra: dict(id=i, vertices=np.array([[-1, y, -1], [1, y, -1], [1, y, 1], [-1, y, 1]], float), triangles=np.array([[0, 1, 2], [0, 2, 3]]),
                                        uv=None, role='furniture', **{'material': None, **extra})
        back = quad(2.0, 1, dict(flat_color=(0.9, 0.1, 0.1)))
        glass = quad(1.0, 2, dict(flat_color=(0.8, 0.9, 0.95), material={'glass': True, 'glass_alpha': 0.25, 'texture': None}))
        cam = dict(position=[0, -3, 0], target=[0, 0, 0], fov=40)
        with tempfile.TemporaryDirectory() as tmp:
            r = render_gpu([back, glass], cam, Path(tmp) / 'g.png', size=(160, 160))
            from PIL import Image
            px = np.asarray(Image.open(Path(tmp) / 'g.png').convert('RGB'))[100, 80].astype(int)
            r2 = render_gpu([back], cam, Path(tmp) / 'b.png', size=(160, 160))
            px2 = np.asarray(Image.open(Path(tmp) / 'b.png').convert('RGB'))[100, 80].astype(int)
        self.assertGreater(px[1] + px[2], px2[1] + px2[2] + 20, 'glass must tint what is behind it')
        self.assertGreater(px[0], 80, 'red object must stay visible through glass')


if __name__ == '__main__':
    unittest.main()
