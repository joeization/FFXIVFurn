"""Real native roof regression; no proprietary fixture is distributed."""
from pathlib import Path
import tempfile
import unittest
from ffxiv_furniture.config import source_path
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.rendering.assets import Assets

NAME = 'HighlandCottageRoof0x28Wood0x29'
SOURCE = source_path('materials') / 'HouseAssets/Roof' / NAME / (NAME + '.uexp')

@unittest.skipUnless(SOURCE.is_file(), 'Local native Highland roof absent')
class HighlandRoofTests(unittest.TestCase):
    def test_all_native_roof_sections_have_real_textures(self):
        record = read_static_mesh_bounds(SOURCE)
        record['item_id'] = 'roof-regression'
        with tempfile.TemporaryDirectory() as cache:
            assets = Assets([record], Path(cache), mi_tint=True)
            loaded = assets.load('roof-regression')
            coverage = assets.coverage[0]
            self.assertEqual(coverage['material_slots'], 5)
            self.assertEqual(coverage['textured_slots'], 5, coverage['materials'])
            self.assertFalse(coverage['notes'])
            for material in loaded['materials']:
                self.assertIsNotNone(material['texture'])
                self.assertIsNone(material['warning'])
                self.assertGreater(float(material['texture'][..., :3].std()), 1.0)

if __name__ == '__main__':
    unittest.main()
