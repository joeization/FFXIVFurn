import json, sqlite3, unittest
from pathlib import Path
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.layout import apply_fixtures

ROOT = Path(__file__).resolve().parents[1]


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.db = FurnitureDB(':memory:')
        self.db.connection.execute('CREATE TABLE house_materials(asset_key TEXT,item_id INTEGER,category TEXT,name TEXT)')
        self.db.connection.executemany('INSERT INTO house_materials VALUES(?,?,?,?)', [
            ('a', 6459, 'Flooring', 'Glade Flooring'), ('b', 14070, 'Wallpaper', 'Alpine Inner Wall'), ('c', 16013, 'CeilingLight', 'Crystal Chandelier'),
            ('d', 7000, 'Roof', 'Some Roof'), ('e', 7001, 'Fence', 'Some Fence')])
        self.seed = {'houseSize': 'Medium', 'interiorFixture': [{'level': l, 'type': t, 'name': 'x', 'itemId': 1, 'color': ''}
                     for t in ('Wall', 'Floor', 'Light') for l in ('Ground Floor', 'Upper Floor')],
                     'exteriorFixture': [{'level': '', 'type': 'Door', 'name': 'd', 'itemId': 2, 'color': ''}]}

    def test_interior_replaces_slot_only(self):
        out, w = apply_fixtures(self.db, self.seed, [{'item_id': 14070, 'level': 'Ground Floor'}, {'item_id': 6459, 'level': 'Upper Floor'}])
        wall = [x for x in out['interiorFixture'] if x['type'] == 'Wall']
        self.assertEqual([x['itemId'] for x in wall], [14070, 1])
        self.assertEqual(len(out['interiorFixture']), len(self.seed['interiorFixture']))
        self.assertEqual(self.seed['interiorFixture'][0]['itemId'], 1)  # input untouched
        self.assertEqual(w, [])

    def test_rejections(self):
        with self.assertRaises(ValueError): apply_fixtures(self.db, self.seed, [{'item_id': 99999, 'level': 'Ground Floor'}])
        with self.assertRaises(ValueError): apply_fixtures(self.db, self.seed, [{'item_id': 6459, 'level': 'Basement'}])
        with self.assertRaises(ValueError): apply_fixtures(self.db, self.seed, [{'item_id': 6459}])
        with self.assertRaises(ValueError): apply_fixtures(self.db, self.seed, [{'item_id': 7000, 'level': 'Ground Floor'}])

    def test_exterior_unobserved_type_warns(self):
        out, w = apply_fixtures(self.db, self.seed, [{'item_id': 7001}])
        self.assertEqual(out['exteriorFixture'][-1]['type'], 'Fence'); self.assertTrue(any('never seen' in x for x in w))

    @unittest.skipUnless((ROOT / 'data/furniture.sqlite3').exists(), 'real DB missing')
    def test_known_real_ids_match_real_save(self):
        c = sqlite3.connect('file:' + str(ROOT / 'data/furniture.sqlite3') + '?mode=ro', uri=True)
        for iid, name in [(6459, 'Glade Flooring'), (14070, 'Alpine Inner Wall'), (16013, 'Crystal Chandelier')]:
            self.assertEqual(c.execute('SELECT name FROM house_materials WHERE item_id=?', (iid,)).fetchone()[0], name)
        c.close()


if __name__ == '__main__':
    unittest.main()
