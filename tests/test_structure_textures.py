import unittest
from pathlib import Path
try:
    import numpy as np
except ImportError:
    raise unittest.SkipTest('numpy not installed')
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / 'data/house-legacy/MakePlace/Content/HouseAssets/InteriorStyles/Shirogane/Material').exists()
                     and (ROOT / 'data/house-materials-legacy/MakePlace/Content/HouseAssets/Flooring/GladeFlooring').exists(), 'extracted game assets absent')
class StructureTextureTests(unittest.TestCase):
    def test_structure_meshes_resolve_native_textures_and_fixture_textures(self):
        import json
        from ffxiv_furniture.rendering.assets import Assets
        from ffxiv_furniture.rendering.house_materials import fixture_texture
        recs = json.loads((ROOT / 'outputs/house-layouts/native-bounds.json').read_text(encoding='utf-8'))['records']
        rec = next(r for r in recs if r['source'].replace(chr(92), '/').endswith('InteriorStyles/Shirogane/Stair/Stair1.uexp'))
        a = Assets([], ROOT / 'outputs/render-pipeline/cache'); a.records[-1] = {**rec, 'item_id': -1}; mesh = a.load(-1)
        textured = [m for m in mesh['materials'] if m['texture'] is not None]
        self.assertGreaterEqual(len(textured), 7)                      # stair/frame/ceiling slots decode their own Base texture
        self.assertEqual(textured[0]['texture'].shape[2], 4)
        fx = [{'type': 'Floor', 'level': 'Ground Floor', 'name': 'Glade Flooring', 'itemId': 6459}]
        t = fixture_texture('Floor', fx)
        self.assertEqual(t['texture'].dtype, np.uint8); self.assertEqual(t['provenance']['item_id'], 6459)
        with self.assertRaises(ValueError): fixture_texture('Wall', fx)  # no silent substitution

    def test_unextracted_fixture_is_refused_not_guessed(self):
        from ffxiv_furniture.rendering.house_materials import fixture_texture
        with self.assertRaises(FileNotFoundError):
            fixture_texture('Floor', [{'type': 'Floor', 'level': 'Ground Floor', 'name': 'No Such Flooring', 'itemId': 1}])


if __name__ == '__main__':
    unittest.main()
