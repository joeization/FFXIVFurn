import json
import os
from contextlib import closing
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from ffxiv_furniture import FurnitureDB

ROOT = Path(__file__).resolve().parents[1]


class DatabaseTests(unittest.TestCase):
    def test_availability_tristate_and_filter(self):
        self.db.add_furniture(1, 'unknown')
        self.db.add_furniture(2, 'market', marketable=True, cash_shop=False)
        self.db.add_furniture(3, 'cash', marketable=False, cash_shop=True)
        self.assertIsNone(self.db.get_furniture(1)['marketable'])
        self.assertIs(self.db.get_furniture(2)['marketable'], True)
        self.assertEqual([r['id'] for r in self.db.search_furniture(marketable=False)], [3])
        self.assertEqual([r['id'] for r in self.db.search_furniture(cash_shop=False)], [2])
        self.assertIsNone(self.db.update_furniture(2, cash_shop=None)['cash_shop'])
        for value in (1, 'false', 0.0):
            with self.assertRaises(ValueError):
                self.db.update_furniture(1, marketable=value)
            with self.assertRaises(ValueError):
                self.db.search_furniture(cash_shop=value)

    def test_v1_migration_preserves_data(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'v1.sqlite3'
            with closing(sqlite3.connect(path)) as c:
                c.executescript("CREATE TABLE furniture(id INTEGER PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',image_path TEXT,length REAL,width REAL,height REAL,patch TEXT); INSERT INTO furniture(id,name,patch) VALUES(1,'existing','7.5'); PRAGMA user_version=1;")
            for _ in range(2):
                with FurnitureDB(path) as db:
                    self.assertEqual(db.get_furniture(1)['patch'], '7.5')
                    self.assertIsNone(db.get_furniture(1)['marketable'])
                    self.assertEqual(db.connection.execute('PRAGMA user_version').fetchone()[0],4)

    def setUp(self):
        self.db = FurnitureDB(':memory:')

    def tearDown(self):
        self.db.close()

    def test_furniture_crud_and_nullable_dimensions(self):
        item = self.db.add_furniture(28639, '皮革沙發', description='粉色', patch='5.1')
        self.assertIsNone(item['height'])
        self.assertEqual(item['tags'], [])
        item = self.db.update_furniture(28639, name='Leather Sofa', height=1.2, image_path='images/B.png')
        self.assertEqual(item['height'], 1.2)
        self.assertEqual(self.db.update_furniture(28639, height=None)['height'], None)
        self.assertTrue(self.db.delete_furniture(28639))
        self.assertFalse(self.db.delete_furniture(28639))
        self.assertIsNone(self.db.get_furniture(28639))
        with self.assertRaises(KeyError):
            self.db.update_furniture(28639, name='missing')

    def test_validation_and_duplicate_id(self):
        self.db.add_furniture(1, 'one')
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_furniture(1, 'duplicate')
        for value in (0, -1, True, '1'):
            with self.assertRaises(ValueError):
                self.db.add_furniture(value, 'bad')
        for value in (0, -1, math.nan, math.inf, True, '1'):
            with self.assertRaises(ValueError):
                self.db.update_furniture(1, width=value)
        for change in ({'name':' '}, {'description':None}, {'image_path':42}, {'patch':7.2}, {'oops':1}):
            with self.assertRaises(ValueError):
                self.db.update_furniture(1, **change)
        self.assertEqual(self.db.get_furniture(1)['name'], 'one')

    def test_tag_crud_uniqueness(self):
        tag = self.db.add_tag('style', '古典')
        self.assertEqual(self.db.get_tag(tag['id']), tag)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_tag('style', '古典')
        self.db.add_tag('function', '古典')
        self.assertEqual(len(self.db.list_tags('style')), 1)
        self.assertEqual(self.db.update_tag(tag['id'], name='現代')['name'], '現代')
        self.assertTrue(self.db.delete_tag(tag['id']))
        self.assertFalse(self.db.delete_tag(tag['id']))
        self.assertIsNone(self.db.get_tag(tag['id']))
        with self.assertRaises(KeyError):
            self.db.update_tag(tag['id'], name='missing')

    def test_associations_provenance_and_cascades(self):
        self.db.add_furniture(1, 'one')
        tag = self.db.add_tag('style', 'modern')['id']
        self.db.add_furniture_tag(1, tag, source='qwen-trial117', confidence=.7)
        self.db.add_furniture_tag(1, tag, source='manual', confidence=1)
        rows = self.db.get_furniture(1)['tags']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], 'manual')
        self.assertTrue(self.db.remove_furniture_tag(1, tag))
        self.assertFalse(self.db.remove_furniture_tag(1, tag))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_furniture_tag(999, tag)
        for value in (-.1, 1.1, math.nan, True):
            with self.assertRaises(ValueError):
                self.db.add_furniture_tag(1, tag, confidence=value)
        self.db.add_furniture_tag(1, tag)
        self.db.delete_tag(tag)
        self.assertEqual(self.db.get_furniture(1)['tags'], [])
        tag = self.db.add_tag('color','pink')['id']
        self.db.add_furniture_tag(1, tag)
        self.db.delete_furniture(1)
        self.assertEqual(self.db.connection.execute('SELECT COUNT(*) FROM furniture_tags').fetchone()[0], 0)
        self.assertIsNotNone(self.db.get_tag(tag))

    def test_search_text_tags_all_any_and_paging(self):
        self.db.add_furniture(1, '皮革沙發', description='粉紅色軟包')
        self.db.add_furniture(2, '木桌', description='簡潔')
        self.db.add_furniture(3, '櫃子')
        style = self.db.add_tag('style', '現代')['id']
        color = self.db.add_tag('color', '粉紅')['id']
        self.db.add_furniture_tag(1, style)
        self.db.add_furniture_tag(1, color)
        self.db.add_furniture_tag(2, style)
        ids = lambda **kw: [x['id'] for x in self.db.search_furniture(**kw)]
        self.assertEqual(ids(query='沙發'), [1])
        self.assertEqual(ids(query='軟包'), [1])
        self.assertEqual(ids(query='現代'), [1,2])
        self.assertEqual(ids(query='color'), [1])
        self.assertEqual(ids(name='木', description='潔'), [2])
        self.assertEqual(ids(tag_ids=[style,color]), [1])
        self.assertEqual(ids(tag_ids=[style,color], tag_mode='any'), [1,2])
        self.assertEqual(ids(tag_ids=[style,style]), [1,2])
        self.assertEqual(ids(tag_ids=[style,999]), [])
        self.assertEqual(ids(limit=1,offset=1), [2])
        self.assertEqual(ids(name='木',tag_ids=[color]), [])
        self.assertEqual(ids(query="' OR 1=1 --"), [])

    def test_literal_wildcards(self):
        self.db.add_furniture(1, '100%_wood\\test')
        self.db.add_furniture(2, 'wood')
        for q in ('%', '_', '\\'):
            self.assertEqual([x['id'] for x in self.db.search_furniture(query=q)], [1])

    def test_search_invalid_parameters(self):
        for kw in ({'limit':0}, {'limit':1001}, {'offset':-1}, {'tag_mode':'bad'}, {'tag_ids':[True]}, {'query':1}):
            with self.assertRaises(ValueError):
                self.db.search_furniture(**kw)

    def test_persistence_and_reopen(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'nested'/'db.sqlite3'
            with FurnitureDB(path) as db:
                db.add_furniture(1, 'persist')
            with FurnitureDB(path) as db:
                self.assertEqual(db.get_furniture(1)['name'], 'persist')
                self.assertEqual(db.connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
                self.assertEqual(db.connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_future_schema_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'future.sqlite3'
            with closing(sqlite3.connect(path)) as c:
                c.execute('PRAGMA user_version=99')
            with self.assertRaises(ValueError):
                FurnitureDB(path)


class CLITests(unittest.TestCase):
    def test_full_cli_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/'cli.sqlite3')
            def cli(*args, success=True):
                p=subprocess.run([sys.executable,'-m','ffxiv_furniture','--db',path,*args],
                    cwd=ROOT,capture_output=True,encoding='utf-8',env={**__import__('os').environ,'PYTHONIOENCODING':'utf-8'})
                self.assertEqual(p.returncode, 0 if success else 1, p.stdout+p.stderr)
                return json.loads(p.stdout if success else p.stderr)
            cli('init')
            cli('furniture-add','--id','28639','--name','皮革沙發','--description','粉色軟包','--height','1.2','--marketable','--no-cash-shop')
            self.assertEqual(len(cli('search','--marketable','--no-cash-shop')),1)
            self.assertEqual(cli('search','--cash-shop'),[])
            cli('furniture-update','28639','--clear','marketable')
            self.assertIsNone(cli('furniture-get','28639')['marketable'])
            tag=cli('tag-add','--category','style','--name','現代')['id']
            cli('tag-attach','28639',str(tag),'--source','qwen','--confidence','.8')
            self.assertEqual(len(cli('search','--query','現代','--tag-id',str(tag))),1)
            cli('tag-update',str(tag),'--name','簡約')
            cli('furniture-update','28639','--clear','height','--name','沙發')
            self.assertIsNone(cli('furniture-get','28639')['height'])
            self.assertEqual(len(cli('tag-list','--category','style')),1)
            self.assertTrue(cli('tag-detach','28639',str(tag))['removed'])
            self.assertTrue(cli('tag-delete',str(tag))['deleted'])
            cli('furniture-update','28639','--height','-2',success=False)
            cli('furniture-update','28639','--height','2','--clear','height',success=False)
            self.assertTrue(cli('furniture-delete','28639')['deleted'])
            cli('furniture-get','28639',success=False)
            self.assertEqual(cli('search'),[])


if __name__ == '__main__':
    unittest.main()
