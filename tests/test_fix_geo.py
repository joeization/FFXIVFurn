"""Geometry/plan regressions: opening orientation, per-level stairs, floor assignment, index sizing, labels, summaries."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from shapely.geometry import MultiPolygon, Point, Polygon, box

from ffxiv_furniture import interiors as I

ROOT = Path(__file__).resolve().parents[1]
HAVE = I.BASE.exists()


class OpeningOrientationTests(unittest.TestCase):
    def test_native_negative_yaw_wraps(self):
        rows = [tuple(sorted(dict(actor='W', kind='window', x=3.0, y=8.0, z=1.0, yaw=y).items())) for y in (-179.99997, 180.0, 0.0, 1e-5)]
        rows += [tuple(sorted(dict(actor='E', kind='window', x=12.0, y=0.0, z=1.0, yaw=y).items())) for y in (90.0, -90.0, 270.0)]
        with patch.object(I, '_map_openings', return_value=tuple(rows)):
            got = [o['along'] for o in I.map_openings('X')]
        self.assertEqual(got, ['x'] * 4 + ['y'] * 3)

    @unittest.skipUnless(HAVE, 'extracted interior meshes absent')
    def test_medium_and_large_openings_follow_their_wall(self):
        for cls, hx, hy in ((I.InteriorProfile, 12.0, 8.0), (I.LargeProfile, 20.0, 12.0)):
            p = cls('Shirogane'); seen = set()
            for lv in p.levels:
                for o in p.openings(lv):
                    x, y = o['xy']
                    if abs(abs(y) - hy) < 0.6: self.assertEqual(o['along'], 'x', (cls.__name__, o)); seen.add('x')
                    elif abs(abs(x) - hx) < 0.6: self.assertEqual(o['along'], 'y', (cls.__name__, o)); seen.add('y')
            self.assertEqual(seen, {'x', 'y'}, cls.__name__)
            self.assertTrue(any(o['kind'] == 'door' and o['along'] == 'x' for o in p.openings('ground')), cls.__name__)


@unittest.skipUnless(HAVE, 'extracted interior meshes absent')
class StairFootprintLevelTests(unittest.TestCase):
    def test_hull_vertices_stay_within_the_level_band(self):
        import numpy as np
        from shapely.geometry import MultiPoint
        for p, names in ((I.InteriorProfile('Shirogane'), ('Stairs', 'Stairs2_9')), (I.LargeProfile('Shirogane'), ('MainStairs', 'BasementStairs'))):
            for lv in p.levels:
                z0 = p.level_z[lv]; want = []
                for n in names:
                    w, _ = p.actor_world(n); pts = w[(w[:, 2] >= z0 - 0.3) & (w[:, 2] < z0 + 6.5), :2]
                    if len(pts): want.append(MultiPoint(pts).convex_hull)
                got = p.stair_footprints(lv)
                self.assertEqual(len(got), len(want), (type(p).__name__, lv))
                for g, w_ in zip(got, want): self.assertLess(g.symmetric_difference(w_).area, 1e-9, (type(p).__name__, lv))
            self.assertEqual(len(p.stair_footprints('basement')), 1, 'only the ground->basement flight reaches the basement panel')

    def test_small_honours_level(self):
        p = I.SmallProfile('Shirogane')
        self.assertEqual(p.stair_footprints('upper'), [])
        self.assertEqual(len(p.stair_footprints('basement')), 1)
        self.assertGreater(p.stair_footprints('basement')[0].area, p.stair_footprints('ground')[0].area)

    def test_unknown_level_is_empty_everywhere(self):
        for p in (I.InteriorProfile('Shirogane'), I.SmallProfile('Shirogane'), I.LargeProfile('Shirogane'), I.ApartmentProfile('Shirogane')):
            self.assertEqual(p.stair_footprints('roof'), [], type(p).__name__)
            self.assertEqual(p.pillar_footprints('roof'), [], type(p).__name__)
            self.assertTrue(p.polygon('roof').is_empty, type(p).__name__)


class SummaryAndOpeningTextTests(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'extracted interior meshes absent')
    def test_summaries_report_every_level(self):
        self.assertEqual(I.SmallProfile('Shirogane').summary()['levels'], {'ground': 0.0, 'basement': -7.0})
        self.assertEqual(I.ApartmentProfile('Shirogane').summary()['levels'], {'ground': 0.0})
        self.assertEqual(I.LargeProfile('Shirogane').summary()['levels'], {'ground': 0.0, 'upper': 7.0, 'basement': -7.0})
        self.assertEqual(I.InteriorProfile('Shirogane').summary()['levels'], {'ground': 0.0, 'upper': 7.0, 'basement': -7.0})

    @unittest.skipUnless(HAVE, 'extracted interior meshes absent')
    def test_large_limitations_do_not_claim_windows_are_undecoded(self):
        text = ' '.join(I.LargeProfile('Shirogane').summary()['limitations'])
        self.assertNotIn('not decoded', text)
        self.assertEqual(len(I.LargeProfile('Shirogane').openings('ground')), 9)

    @unittest.skipUnless(HAVE, 'extracted interior meshes absent')
    def test_small_actors_do_not_share_or_leak_mutable_lists(self):
        p = I.SmallProfile('Shirogane'); a = p.actors
        self.assertIsNot(a['Stairs2_9']['scale'], a['StairCeiling']['scale'])
        self.assertIsNot(a['Stairs2_9']['translation_m'], a['StairCeiling']['translation_m'])
        s = p.summary(); s['stairs']['Stairs2_9']['scale'][0] = 9; s['stairs']['Stairs2_9']['translation_m'][0] = 99
        self.assertEqual(p.actors['Stairs2_9']['scale'], [1.0, 1.0, 1.0]); self.assertEqual(p.actors['Stairs2_9']['translation_m'][0], 8.0)

    @unittest.skipUnless(HAVE, 'extracted interior meshes absent')
    def test_apartment_entry_door_is_assumed_on_ground_only(self):
        p = I.ApartmentProfile('Shirogane'); g = p.openings('ground')
        self.assertEqual([(o['kind'], o['xy'], o['along'], o.get('assumed')) for o in g], [('door', [0.0, 8.0], 'x', True)])
        self.assertEqual(p.openings('basement'), []); self.assertEqual(p.openings('upper'), [])

    @unittest.skipUnless(HAVE, 'extracted interior meshes absent')
    def test_list_interiors_is_per_size(self):
        self.assertEqual({x['house_size'] for x in I.list_interiors('Small')}, {'Small'})
        self.assertEqual([x['style'] for x in I.list_interiors('Small')], list(I.SMALL_STYLES))
        self.assertEqual(I.list_interiors('Small')[0]['levels'], ['ground', 'basement'])
        self.assertEqual(I.list_interiors('Apartment')[0]['levels'], ['ground'])
        self.assertEqual(I.list_interiors('Large')[0]['levels'], ['ground', 'upper', 'basement'])
        self.assertEqual([x['style'] for x in I.list_interiors()], list(I.STYLES))


class FloorAssignmentTests(unittest.TestCase):
    def _db(self, folder, rows):
        db = Path(folder) / 'b.sqlite3'
        with closing(sqlite3.connect(db)) as con:
            con.execute('create table furniture_bounds(id integer,min_x real,min_y real,min_z real,max_x real,max_y real,max_z real)')
            for r in rows: con.execute('insert into furniture_bounds values(?,?,?,?,?,?,?)', r)
            con.commit()
        return db

    def test_level_follows_span_rule_and_height_is_relative_to_that_floor(self):
        from scripts.layout_schematic import load_items
        with tempfile.TemporaryDirectory() as folder:
            db = self._db(folder, [(1, -1, -1, -1, 1, 1, 0), (2, -1, -1, 0, 1, 1, 1), (3, -1, -1, -1, 1, 1, 1)])
            def item(i, z): return {'name': 'x', 'itemId': i, 'transform': {'location': [0, 0, z], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}}
            # id1 hangs from the basement ceiling (pivot z -0.5 > -3, span -1.5..-0.5); id2 stands on the basement floor (pivot -7)
            layout = {'houseSize': 'Medium', 'interiorScale': 100, 'interiorFurniture': [item(1, -50), item(2, -700), item(3, 0), item(2, 100)]}
            rows = load_items(layout, db)
            self.assertEqual([r['level'] for r in rows], ['basement', 'basement', 'ground', 'ground'])
            self.assertAlmostEqual(rows[0]['height'], -1.5 + 7.0); self.assertAlmostEqual(rows[1]['height'], 0.0)
            self.assertAlmostEqual(rows[2]['height'], -1.0); self.assertAlmostEqual(rows[3]['height'], 1.0)

    def test_small_item_on_a_missing_floor_is_a_clear_error(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as folder:
            db = self._db(folder, [(1, -1, -1, 0, 1, 1, 1)])
            lay = Path(folder) / 'a-r1.json'
            lay.write_text(json.dumps({'houseSize': 'Small', 'interiorScale': 100, 'interiorFixture': [], 'interiorFurniture': [
                {'name': 'x', 'itemId': 1, 'transform': {'location': [0, 0, 700], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}}]}), encoding='utf-8')
            p = subprocess.run([__import__('sys').executable, '-X', 'utf8', str(ROOT / 'scripts/layout_schematic.py'), str(lay), '--db', str(db), '--out', folder],
                               cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0); self.assertIn('unsupported schematic floors', p.stderr + p.stdout)


class PlanCommonTests(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'extracted interior meshes absent')
    def test_index_cli_grows_canvas_for_all_items(self):
        import subprocess, sys
        from scripts._plan_common import index_geometry
        with tempfile.TemporaryDirectory() as folder:
            db = FloorAssignmentTests()._db(folder, [(1, -0.1, -0.1, 0, 0.1, 0.1, 0.1)])
            lay = Path(folder) / 'Winter-Floor-r1.json'
            item = {'name': 'x', 'itemId': 1, 'transform': {'location': [0, 0, 0], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}}
            lay.write_text(json.dumps({'houseSize': 'Small', 'interiorScale': 100, 'interiorFixture': [], 'interiorFurniture': [item] * 174}), encoding='utf-8')
            p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/layout_schematic.py'), str(lay), '--db', str(db), '--out', folder, '--index', '--no-labels', '--scale', '1'],
                               cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            result = json.loads(p.stdout)
            self.assertEqual(result['items'], 174)
            with Image.open(result['image']) as im:
                self.assertEqual(im.width, 3200)
                self.assertGreaterEqual(im.height, index_geometry(174, im.width)[2])

    def test_index_area_fits_every_item(self):
        from scripts._plan_common import index_geometry
        for n, width in ((0, 3200), (28, 3200), (112, 3200), (113, 3200), (600, 3200), (600, 5000)):
            cols, rows, height = index_geometry(n, width)
            self.assertGreaterEqual(cols * rows, n); self.assertGreaterEqual(cols, 1)
            self.assertLessEqual(85 + (cols - 1) * 785 + 745, width, (n, width))   # last column's text stays on the canvas
            self.assertGreaterEqual(height, 1775 + rows * 35)
        self.assertGreater(index_geometry(600, 3200)[2], index_geometry(112, 3200)[2])

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
        im = Image.new('RGB', (100, 100), 'white'); d = ImageDraw.Draw(im)
        mp = MultiPolygon([box(0, 0, 1, 1), box(2, 2, 3, 3)])
        for g in (mp, Polygon(), Point(1, 1), Point(0, 0).buffer(0).union(Point(1, 1)), box(0, 0, 5, 5).boundary, mp.convex_hull):
            draw_geom(d, lambda x, y: (x * 10, y * 10), g, fill='red', outline='black', width=2)
        self.assertEqual(im.getpixel((5, 5)), (255, 0, 0)); self.assertEqual(im.getpixel((25, 25)), (255, 0, 0))


class YardNoteTests(unittest.TestCase):
    def test_orientation_note_is_outside_the_plot_box(self):
        import scripts.yard_schematic as y
        self.assertGreaterEqual(y.NOTE_XY[1], y.BOX[3])


if __name__ == '__main__':
    unittest.main()
