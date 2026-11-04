"""Real schematic CLI regression; source layouts stay local."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT/'outputs/deco-sessions/s-woodland/S_Woodland_Retreat-r34.json'

@unittest.skipUnless(LAYOUT.exists(), 'Local example layout absent')
class SchematicPlanningTests(unittest.TestCase):
    def test_default_plan_does_not_allocate_furniture_inventory_space(self):
        with tempfile.TemporaryDirectory() as folder:
            p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'scripts/layout_schematic.py'), str(LAYOUT), '--out', folder], cwd=ROOT, capture_output=True, text=True, check=True)
            report = json.loads(p.stdout)
            with Image.open(report['image']) as image:
                self.assertEqual(image.height, 1800)
            self.assertFalse(report['furniture_index'])

if __name__ == '__main__':
    unittest.main()
