"""Phasmascape scene slots (M_bgUvScroll, DiffuseA/DiffuseB, no Base) must render their scene picture, not a flat grey panel.
User-facing reason: blank Phasmascapes made scenic windows/skylights impossible to judge in design renders."""
import unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GA = ROOT / 'data/gameassets-legacy/MakePlace/Content/GameAssets'
LB = GA / 'Furniture/Others/LavenderBedsPhasmascape'


@unittest.skipUnless(LB.exists(), 'Local Phasmascape assets not present')
class PhasmascapeSceneTests(unittest.TestCase):
    def test_uv_scroll_mi_exposes_both_diffuse_layers(self):
        from ffxiv_furniture.rendering import native
        mi = native.material_instance(LB / '0_fun_b0_m1374_0c_bguv_const/fun_b0_m1373_0c.uasset')
        self.assertTrue(mi['parent'].endswith('M_bgUvScroll'))
        self.assertIn('fun_b0_m1373_0c_d', mi['parameters']['DiffuseA']['value'])
        self.assertIn('fun_b0_m1374_0d_d', mi['parameters']['DiffuseB']['value'])
        self.assertIn('fun_b0_m1374_0d_d', mi['parameters']['Normal']['value'])  # unchanged existing key

    def test_scene_slot_textured_with_diffuse_b(self):
        from ffxiv_furniture.geometry import read_static_mesh_bounds
        from ffxiv_furniture.rendering.assets import Assets
        for folder in (LB, GA / 'Fixture/SunsetPhasmascape', GA / 'Furniture/Others/MistPhasmascape'):
            with self.subTest(folder=folder.name):
                rec = read_static_mesh_bounds(folder / (folder.name + '.uexp')); rec['item_id'] = -5
                a = Assets([rec], ROOT / 'outputs/render-pipeline/cache', mi_tint=True); m = a.load(-5)
                cov = a.coverage[-1]
                self.assertEqual(cov['textured_slots'], cov['material_slots'], cov['materials'])
                scene = [d for d in m['materials'] if d.get('uv_scroll_layer')]
                self.assertEqual(len(scene), 1); self.assertEqual(scene[0]['uv_scroll_layer'], 'DiffuseB')
                self.assertIn('static DiffuseB', scene[0]['warning'])
                self.assertGreater(np.asarray(scene[0]['texture'])[..., :3].std(), 20, 'scene must be a picture, not a flat fill')


if __name__ == '__main__':
    unittest.main()
