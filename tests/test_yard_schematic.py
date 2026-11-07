"""Yard plan CLI: SVG by default, JPEG on request; generic house size/gate/door; source files untouched."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
_FOUND = sorted((ROOT / 'outputs/deco-sessions/s-hingan-ryokan-yard-final').glob('*-full-r*[0-9].json'), key=lambda p: p.stat().st_mtime)
LAYOUT = _FOUND[-1] if _FOUND else ROOT / 'outputs/deco-sessions/_no-local-yard-export.json'   # newest local yard export, if any
NS = {'s': 'http://www.w3.org/2000/svg'}


def run(*extra):
    with tempfile.TemporaryDirectory() as folder:
        p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/yard_schematic.py'), str(LAYOUT), '--out', folder, *extra],
                           cwd=ROOT, capture_output=True, text=True, check=True)
        report = json.loads(p.stdout)
        path = Path(report['image'])
        data = path.read_bytes()
    return report, path, data


@unittest.skipUnless(LAYOUT.exists(), 'Local example yard export absent')
class YardSchematicTests(unittest.TestCase):
    def test_default_is_svg_with_gate_door_and_budget(self):
        before = LAYOUT.read_bytes()
        report, path, data = run('--limit', '20')
        self.assertEqual(path.suffix, '.svg')
        root = ET.fromstring(data)
        texts = ' | '.join(t.text or '' for t in root.findall('.//s:text', NS))
        for word in ('GATE', 'DOOR', f"{report['count']} / 20"):
            self.assertIn(word, texts)
        layout = json.loads(before)
        self.assertEqual(report['count'], len(layout['exteriorFurniture']))
        self.assertGreaterEqual(len(root.findall('.//s:polygon', NS)), report['count'])
        self.assertEqual(LAYOUT.read_bytes(), before)
        self.assertTrue(report['protected_files_unchanged'])

    def test_jpg_format(self):
        report, path, data = run('--format', 'jpg')
        self.assertEqual(path.suffix, '.jpg')
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(data)
        try:
            with Image.open(f.name) as im:
                self.assertEqual(im.format, 'JPEG')
        finally:
            Path(f.name).unlink()

    def test_gate_and_door_come_from_native_actors(self):
        from ffxiv_furniture.exteriors import native_exterior_actors
        actors = {a['name']: a for a in native_exterior_actors('Small')}
        self.assertEqual(actors['OutsideEntrance']['translation_m'][:2], [4.0, 12.0])
        self.assertEqual(actors['MainDoor']['translation_m'][:2], [-4.0, 2.0])


if __name__ == '__main__':
    unittest.main()
