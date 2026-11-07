"""Yard plan CLI: one JPEG; generic house size/gate/door; source files untouched."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
_FOUND = sorted((ROOT / 'outputs/deco-sessions/s-hingan-ryokan-yard-final').glob('*-full-r*[0-9].json'), key=lambda p: p.stat().st_mtime)
LAYOUT = _FOUND[-1] if _FOUND else ROOT / 'outputs/deco-sessions/_no-local-yard-export.json'   # newest local yard export, if any


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
    def test_plan_is_jpeg_counts_budget_and_leaves_source_untouched(self):
        before = LAYOUT.read_bytes()
        report, path, data = run('--limit', '20')
        self.assertEqual(path.suffix, '.jpg')
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(data)
        try:
            with Image.open(f.name) as im:
                self.assertEqual((im.format, im.size), ('JPEG', (960, 930)))   # 1600x1550 canvas at the default 0.6
        finally:
            Path(f.name).unlink()
        layout = json.loads(before.decode('utf-16') if before[:2] in (b'\xff\xfe', b'\xfe\xff') else before)
        self.assertEqual(report['count'], len(layout['exteriorFurniture']))
        self.assertEqual(report['limit'], 20)
        self.assertEqual(LAYOUT.read_bytes(), before)
        self.assertTrue(report['protected_files_unchanged'])

    def test_gate_and_door_come_from_native_actors(self):
        from ffxiv_furniture.exteriors import native_exterior_actors
        actors = {a['name']: a for a in native_exterior_actors('Small')}
        self.assertEqual(actors['OutsideEntrance']['translation_m'][:2], [4.0, 12.0])
        self.assertEqual(actors['MainDoor']['translation_m'][:2], [-4.0, 2.0])


if __name__ == '__main__':
    unittest.main()
