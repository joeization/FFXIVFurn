import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from ffxiv_furniture import FurnitureDB

ROOT=Path(__file__).resolve().parents[1]


class DyeTests(unittest.TestCase):
    def test_tristate_channel_validation_and_clear(self):
        with FurnitureDB(':memory:') as db:
            self.assertIsNone(db.add_furniture(1,'unknown')['dyeable'])
            item=db.update_furniture(1,dyeable=True,dye_channels=2)
            self.assertIs(item['dyeable'],True)
            self.assertEqual(item['dye_channels'],2)
            item=db.update_furniture(1,dyeable=False,dye_channels=0)
            self.assertIs(item['dyeable'],False)
            self.assertEqual(item['dye_channels'],0)
            item=db.update_furniture(1,dyeable=None,dye_channels=None)
            self.assertIsNone(item['dyeable']);self.assertIsNone(item['dye_channels'])
            for value in (-1,1.5,True,'2'):
                with self.assertRaises(ValueError):db.update_furniture(1,dye_channels=value)
            for value in (0,'false'):
                with self.assertRaises(ValueError):db.update_furniture(1,dyeable=value)
            for value in (-1,1.5):
                with self.assertRaises(sqlite3.IntegrityError),db.connection:
                    db.connection.execute('UPDATE furniture SET dye_channels=? WHERE id=1',(value,))

    def test_v2_upgrade_preserves_furniture_and_tags(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'old.sqlite3'
            with closing(sqlite3.connect(p)) as c:
                c.executescript("""CREATE TABLE furniture(id INTEGER PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',image_path TEXT,length REAL,width REAL,height REAL,patch TEXT,marketable INTEGER,cash_shop INTEGER);
                CREATE TABLE tags(id INTEGER PRIMARY KEY,category TEXT NOT NULL,name TEXT NOT NULL,UNIQUE(category,name));
                CREATE TABLE furniture_tags(furniture_id INTEGER,tag_id INTEGER,source TEXT,confidence REAL,PRIMARY KEY(furniture_id,tag_id));
                INSERT INTO furniture(id,name,description) VALUES(1,'old','keep');
                INSERT INTO tags VALUES(1,'style','keep');
                INSERT INTO furniture_tags VALUES(1,1,'manual',1);
                PRAGMA user_version=2;""")
            for _ in range(2):
                with FurnitureDB(p) as db:
                    item=db.get_furniture(1)
                    self.assertEqual(item['description'],'keep')
                    self.assertEqual(item['tags'][0]['name'],'keep')
                    self.assertIsNone(item['dyeable']);self.assertIsNone(item['dye_channels'])
                    self.assertEqual(db.connection.execute('PRAGMA user_version').fetchone()[0],4)

    def test_cli_add_update_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/'cli.sqlite3')
            def cli(*args):
                r=subprocess.run([sys.executable,'-m','ffxiv_furniture','--db',path,*args],cwd=ROOT,
                    capture_output=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
                self.assertEqual(r.returncode,0,r.stderr)
                return json.loads(r.stdout)
            item=cli('furniture-add','--id','1','--name','test','--dyeable','--dye-channels','2')
            self.assertIs(item['dyeable'],True);self.assertEqual(item['dye_channels'],2)
            item=cli('furniture-update','1','--no-dyeable','--dye-channels','0')
            self.assertIs(item['dyeable'],False)
            item=cli('furniture-update','1','--clear','dyeable','--clear','dye_channels')
            self.assertIsNone(item['dyeable']);self.assertIsNone(item['dye_channels'])
