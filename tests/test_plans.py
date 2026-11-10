"""Layout and yard schematic CLIs, shared plan geometry, labels and floor assignment."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from PIL import Image, ImageDraw
from contextlib import closing
from pathlib import Path
from shapely.geometry import MultiPolygon, Point, Polygon, box
from tests.support import ROOT

class FloorAssignmentTests(unittest.TestCase):

    def _db(self, folder, rows):
        db = Path(folder) / 'b.sqlite3'
        with closing(sqlite3.connect(db)) as con:
            con.execute('create table furniture_bounds(id integer,min_x real,min_y real,min_z real,max_x real,max_y real,max_z real)')
            for r in rows:
                con.execute('insert into furniture_bounds values(?,?,?,?,?,?,?)', r)
            con.commit()
        return db

    def test_level_follows_span_rule_and_height_is_relative_to_that_floor(self):
        from scripts.layout_schematic import load_items
        with tempfile.TemporaryDirectory() as folder:
            db = self._db(folder, [(1, -1, -1, -1, 1, 1, 0), (2, -1, -1, 0, 1, 1, 1), (3, -1, -1, -1, 1, 1, 1), (4, -1, -1, -7, 1, 1, 0)])

            def item(i, z):
                return {'name': 'x', 'itemId': i, 'transform': {'location': [0, 0, z], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}}
            layout = {'houseSize': 'Medium', 'interiorScale': 100, 'interiorFurniture': [item(1, -50), item(2, -700), item(3, 0), item(2, 100), item(2, 700), item(2, 400), item(4, 700)]}
            rows = load_items(layout, db)
            self.assertEqual([r['level'] for r in rows], ['basement', 'basement', 'ground', 'ground', 'upper', 'ground', 'ground'])
            self.assertEqual([round(r['height'], 3) for r in rows], [5.5, 0.0, -1.0, 1.0, 0.0, 4.0, 0.0])

    def test_small_item_on_a_missing_floor_is_a_clear_error(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as folder:
            db = self._db(folder, [(1, -1, -1, 0, 1, 1, 1)])
            lay = Path(folder) / 'a-r1.json'
            lay.write_text(json.dumps({'houseSize': 'Small', 'interiorScale': 100, 'interiorFixture': [], 'interiorFurniture': [{'name': 'x', 'itemId': 1, 'transform': {'location': [0, 0, 700], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}}]}), encoding='utf-8')
            p = subprocess.run([__import__('sys').executable, '-X', 'utf8', str(ROOT / 'scripts/layout_schematic.py'), str(lay), '--db', str(db), '--out', folder], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('unsupported schematic floors', p.stderr + p.stdout)

class PlanCommonTests(unittest.TestCase):

    def test_index_fits_every_item(self):
        import subprocess, sys
        from scripts._plan_common import index_geometry
        for n, width in ((0, 3200), (28, 3200), (112, 3200), (113, 3200), (600, 3200), (600, 5000)):
            cols, rows, height = index_geometry(n, width)
            self.assertGreaterEqual(cols * rows, n)
            self.assertGreaterEqual(cols, 1)
            self.assertLessEqual(85 + (cols - 1) * 785 + 745, width, (n, width))
            self.assertGreaterEqual(height, 1775 + rows * 35)
        with tempfile.TemporaryDirectory() as folder:
            db = FloorAssignmentTests()._db(folder, [(1, -0.1, -0.1, 0, 0.1, 0.1, 0.1)])
            lay = Path(folder) / 'Winter-Floor-r1.json'
            item = {'name': 'x', 'itemId': 1, 'transform': {'location': [0, 0, 0], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}}
            lay.write_text(json.dumps({'houseSize': 'Small', 'interiorScale': 100, 'interiorFixture': [], 'interiorFurniture': [item] * 174}), encoding='utf-8')
            p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/layout_schematic.py'), str(lay), '--db', str(db), '--out', folder, '--index', '--no-labels', '--scale', '1'], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            result = json.loads(p.stdout)
            self.assertEqual(result['items'], 174)
            with Image.open(result['image']) as im:
                self.assertEqual(im.width, 3200)
                self.assertGreaterEqual(im.height, index_geometry(174, im.width)[2])

    def test_title_and_revision_only_strip_a_trailing_r_number(self):
        from scripts._plan_common import title_revision
        self.assertEqual(title_revision('Winter_Garden-r12'), ('Winter Garden', 'r12'))
        self.assertEqual(title_revision('Silver-Chapter-r2'), ('Silver-Chapter', 'r2'))
        self.assertEqual(title_revision('Silver-Chapter'), ('Silver-Chapter', 'r?'))
        self.assertEqual(title_revision('Winter-Floor'), ('Winter-Floor', 'r?'))
        self.assertEqual(title_revision('Mirror'), ('Mirror', 'r?'))
        self.assertEqual(title_revision('x-ryokan'), ('x-ryokan', 'r?'))
        self.assertEqual(title_revision('s-hingan-ryokan-full-R14'), ('s-hingan-ryokan-full', 'R14'))

    def test_scale_bar_digits_sit_on_their_ticks(self):
        from scripts._plan_common import scale_bar_labels
        self.assertEqual(scale_bar_labels(100.0, 70.0), [(100.0, '0'), (170.0, '1'), (240.0, '2')])
        self.assertEqual(scale_bar_labels(100.0, 140.0)[2], (380.0, '2'))

    def test_draw_geom_handles_multi_degenerate_and_empty(self):
        from scripts._plan_common import draw_geom
        im = Image.new('RGB', (100, 100), 'white')
        d = ImageDraw.Draw(im)
        mp = MultiPolygon([box(0, 0, 1, 1), box(2, 2, 3, 3)])
        for g in (mp, Polygon(), Point(1, 1), Point(0, 0).buffer(0).union(Point(1, 1)), box(0, 0, 5, 5).boundary, mp.convex_hull):
            draw_geom(d, lambda x, y: (x * 10, y * 10), g, fill='red', outline='black', width=2)
        self.assertEqual(im.getpixel((5, 5)), (255, 0, 0))
        self.assertEqual(im.getpixel((25, 25)), (255, 0, 0))

class YardNoteTests(unittest.TestCase):

    def test_orientation_note_is_outside_the_plot_box(self):
        import scripts.yard_schematic as y
        self.assertGreaterEqual(y.NOTE_XY[1], y.BOX[3])
LAYOUT = ROOT / 'outputs/deco-sessions/s-woodland/S_Woodland_Retreat-r34.json'
M_LAYOUT = ROOT / 'outputs/deco-sessions/m-hingan-ryokan/m-hingan-ryokan-r27.json'

@unittest.skipUnless(LAYOUT.exists(), 'Local example layout absent')
class SchematicPlanningTests(unittest.TestCase):

    def test_default_plan_does_not_allocate_furniture_inventory_space(self):
        with tempfile.TemporaryDirectory() as folder:
            p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/layout_schematic.py'), str(LAYOUT), '--out', folder], cwd=ROOT, capture_output=True, text=True, check=True)
            report = json.loads(p.stdout)
            self.assertEqual(Path(report['image']).suffix, '.jpg')
            with Image.open(report['image']) as image:
                self.assertEqual((image.format, image.size), ('JPEG', (1920, 1080)))
            self.assertFalse(report['furniture_index'])

@unittest.skipUnless(M_LAYOUT.exists(), 'Local three-floor example absent')
class ThreeFloorSchematicTests(unittest.TestCase):

    def test_every_floor_gets_a_panel_on_the_canvas(self):
        with tempfile.TemporaryDirectory() as folder:
            p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/layout_schematic.py'), str(M_LAYOUT), '--out', folder], cwd=ROOT, capture_output=True, text=True, check=True)
            report = json.loads(p.stdout)
            self.assertEqual(set(report['floors']), {'ground', 'upper', 'basement'})
            self.assertEqual(sum(report['floors'].values()), report['items'])
            with Image.open(report['image']) as image:
                w, h = image.size
                self.assertGreaterEqual(w, round(0.6 * (65 + 3 * 1500 + 2 * 70)))
                crop = image.convert('L').crop((1980, 180, 2820, 840))
                self.assertGreater(len(set(crop.getdata())), 20)
_FOUND = sorted((ROOT / 'outputs/deco-sessions/s-hingan-ryokan-yard-final').glob('*-full-r*[0-9].json'), key=lambda p: p.stat().st_mtime)
YARD_LAYOUT = _FOUND[-1] if _FOUND else ROOT / 'outputs/deco-sessions/_no-local-yard-export.json'

def run(*extra):
    with tempfile.TemporaryDirectory() as folder:
        p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/yard_schematic.py'), str(YARD_LAYOUT), '--out', folder, *extra], cwd=ROOT, capture_output=True, text=True, check=True)
        report = json.loads(p.stdout)
        path = Path(report['image'])
        data = path.read_bytes()
    return (report, path, data)

@unittest.skipUnless(YARD_LAYOUT.exists(), 'Local example yard export absent')
class YardSchematicTests(unittest.TestCase):

    def test_plan_is_jpeg_counts_budget_and_leaves_source_untouched(self):
        before = YARD_LAYOUT.read_bytes()
        report, path, data = run('--limit', '20')
        self.assertEqual(path.suffix, '.jpg')
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(data)
        try:
            with Image.open(f.name) as im:
                self.assertEqual((im.format, im.size), ('JPEG', (960, 930)))
        finally:
            Path(f.name).unlink()
        layout = json.loads(before.decode('utf-16') if before[:2] in (b'\xff\xfe', b'\xfe\xff') else before)
        self.assertEqual(report['count'], len(layout['exteriorFurniture']))
        self.assertEqual(report['limit'], 20)
        self.assertEqual(YARD_LAYOUT.read_bytes(), before)
        self.assertTrue(report['protected_files_unchanged'])

    def test_gate_and_door_come_from_native_actors(self):
        from ffxiv_furniture.exteriors import native_exterior_actors
        actors = {a['name']: a for a in native_exterior_actors('Small')}
        self.assertEqual(actors['OutsideEntrance']['translation_m'][:2], [4.0, 12.0])
        self.assertEqual(actors['MainDoor']['translation_m'][:2], [-4.0, 2.0])
