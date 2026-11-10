"""Catalog CRUD, migrations, fixtures, layout budgets, export and thumbnail decoding."""

import importlib.util
import io
import json
import math
import os
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.__main__ import main
from ffxiv_furniture.database import SCHEMA
from ffxiv_furniture.housing import HOUSING_LIMITS, validate_layout_budget, floor_access_policy
from ffxiv_furniture.layout import apply_fixtures, build_layout
from pathlib import Path
from tests.support import ROOT

def load_script(name):
    """Load one repository script without repeating importlib boilerplate."""
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


catalog_builder = load_script('build_test_catalog')
thumbnail_decoder = load_script('prepare_thumbnails')


class FurnitureDBTests(unittest.TestCase):
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


class CatalogCLITests(unittest.TestCase):
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


class CatalogDyeTests(unittest.TestCase):
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


class LayoutFixtureTests(unittest.TestCase):
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


class LayoutExportTests(unittest.TestCase):
    def test_db_id_name_and_seed_preserved(self):
        seed={'houseSize':'Medium','interiorScale':100,'interiorFurniture':[{'old':True}], 'metaData':{'version':144},'unknown':{'keep':[1]}}
        with FurnitureDB(':memory:') as db:
            db.add_furniture(28639,'Leather Sofa',scope='interior')
            result=build_layout(db,seed,[{'item_id':28639,'location':[1,2,3],'yaw_degrees':180}])
        self.assertEqual(seed['interiorFurniture'],[{'old':True}])
        self.assertEqual(result['unknown'],seed['unknown'])
        item=result['interiorFurniture'][0]
        self.assertEqual((item['itemId'],item['name']),(28639,'Leather Sofa'))
        self.assertEqual(item['transform']['location'],[1,2,3])
        self.assertAlmostEqual(sum(v*v for v in item['transform']['rotation']),1)
        self.assertAlmostEqual(item['transform']['rotation'][2],1)

    def test_no_unknown_ids_nonfinite_or_empty_layout(self):
        with FurnitureDB(':memory:') as db:
            db.add_furniture(1,'known',scope='interior')
            for seed,placements in [({'interiorScale':0},[{'item_id':1,'location':[0,0,0]}]),
                ({'interiorScale':100},[]),({'interiorScale':100},[{'item_id':999,'location':[0,0,0]}]),
                ({'interiorScale':100},[{'item_id':1,'location':[0,0,math.nan]}]),
                ({'interiorScale':100},[{'item_id':1,'location':[0,0,0],'yaw_degrees':math.inf}])]:
                with self.assertRaises(ValueError):build_layout(db,seed,placements)

    def test_canonical_mapping_preserves_specificity_and_category_refactor(self):
        concepts={'old':{'status':'merged','merged_into':'wood'},'wood':{'status':'accepted'},
                  'dark':{'status':'provisional'},'carved-style':{'status':'provisional','superseded_by':'carved-ornament'},
                  'carved-ornament':{'status':'provisional'},'unknown':{'status':'unresolved'}}
        self.assertEqual(catalog_builder.canonical_id(concepts,'old'),'wood')
        self.assertEqual(catalog_builder.canonical_id(concepts,'dark'),'dark')
        self.assertEqual(catalog_builder.canonical_id(concepts,'carved-style'),'carved-ornament')
        self.assertIsNone(catalog_builder.canonical_id(concepts,'unknown'))
        concepts['wood']={'status':'merged','merged_into':'old'}
        with self.assertRaises(ValueError):catalog_builder.canonical_id(concepts,'old')


class HousingConstraintTests(unittest.TestCase):
    def test_scope_crud_and_strict_search(self):
        with FurnitureDB(':memory:') as db:
            db.add_furniture(1,'inside',scope='interior');db.add_furniture(2,'outside',scope='exterior');db.add_furniture(3,'unknown')
            self.assertEqual([r['id'] for r in db.search_furniture(scope='interior')],[1])
            self.assertEqual([r['id'] for r in db.search_furniture(scope='exterior')],[2])
            self.assertEqual(db.update_furniture(3,scope='interior')['scope'],'interior')
            self.assertIsNone(db.update_furniture(3,scope=None)['scope'])
            for bad in ('both','indoor',True,[],42):
                with self.assertRaises(ValueError):db.update_furniture(1,scope=bad)
            with self.assertRaises(sqlite3.IntegrityError):db.connection.execute("UPDATE furniture SET scope='both'")

    def test_migrate_v3_unknown_stays_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'old.db'
            old=SCHEMA.replace(",\n scope TEXT CHECK(scope IS NULL OR scope IN ('interior','exterior'))",'')
            with closing(sqlite3.connect(path)) as c:
                c.executescript(old+"INSERT INTO furniture(id,name) VALUES(1,'old');PRAGMA user_version=3;")
            with FurnitureDB(path) as db:
                self.assertEqual(db.connection.execute('PRAGMA user_version').fetchone()[0],4)
                self.assertIsNone(db.get_furniture(1)['scope'])

    def test_export_rejects_wrong_and_unknown_scope(self):
        seed={'houseSize':'Small','interiorScale':100,'exteriorScale':100}
        with FurnitureDB(':memory:') as db:
            for i,scope in [(1,'interior'),(2,'exterior'),(3,None)]:db.add_furniture(i,str(i),scope=scope)
            placement=lambda i:[{'item_id':i,'location':[0,0,0]}]
            self.assertEqual(build_layout(db,seed,placement(1))['interiorFurniture'][0]['itemId'],1)
            self.assertEqual(build_layout(db,seed,placement(2),scope='exterior')['exteriorFurniture'][0]['itemId'],2)
            for i in (2,3):
                with self.assertRaises(ValueError):build_layout(db,seed,placement(i))
            with self.assertRaises(ValueError):build_layout(db,seed,placement(1),scope='exterior')

    def test_all_cap_boundaries_separate_scopes(self):
        for size,limits in HOUSING_LIMITS.items():
            for scope,limit in limits.items():
                layout={'houseSize':size,scope+'Furniture':[{} for _ in range(limit)]}
                self.assertEqual(validate_layout_budget(layout)['scope_budgets'][scope]['remaining'],0)
                layout[scope+'Furniture'].append({})
                with self.assertRaises(ValueError):validate_layout_budget(layout)

    def test_whole_house_attachments_and_overlap_count(self):
        # Same position/group does not merge furniture instances into one slot.
        items=[{'transform':{'location':[0,0,0]},'group':'same'} for _ in range(449)]
        items[0]['attachments']=[{},{}]
        with self.assertRaises(ValueError):validate_layout_budget({'houseSize':'Medium','interiorFurniture':items})
        with self.assertRaises(ValueError):validate_layout_budget({'houseSize':'unverified-type'})
        with self.assertRaises(ValueError):validate_layout_budget({'houseSize':'Apartment','exteriorFurniture':[{}]})

    def test_close_unused_floors_not_used_routes(self):
        policy=floor_access_policy('Medium',['ground'])
        self.assertEqual(len(policy['may_conceal_connections']),2)
        self.assertEqual(policy['required_open_connections'],[])
        self.assertTrue(policy['main_entrance_must_remain_accessible'])
        policy=floor_access_policy('Medium',['ground','basement'])
        self.assertEqual(policy['required_open_connections'],[{'from':'ground','to':'basement'}])
        self.assertEqual(policy['may_conceal_connections'],[{'from':'ground','to':'upper'}])
        self.assertEqual(floor_access_policy('Apartment')['may_conceal_connections'],[])
        for bad in (['basement'],['ground','attic'],'ground'):
            with self.assertRaises(ValueError):floor_access_policy('Medium',bad)

    def test_cli_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.db'
            for argv in [ ['furniture-add','--id','1','--name','inside','--scope','interior'],['search','--scope','interior'] ]:
                with redirect_stdout(io.StringIO()) as output:self.assertEqual(main(['--db',str(path),*argv]),0)
                result=json.loads(output.getvalue())
            self.assertEqual(result[0]['scope'],'interior')


try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None,'optional Pillow is not installed')
class ThumbnailTests(unittest.TestCase):
    def fixture(self,fmt,payload,offset):
        w=h=4
        header=bytearray(offset)
        marker=(fmt+'\0').encode()
        start=93 if fmt=='PF_DXT1' else offset-20
        struct.pack_into('<III',header,start-16,w,h,1)
        struct.pack_into('<i',header,start-4,len(marker))
        header[start:start+len(marker)]=marker
        trailer=struct.pack('<6I',w,h,1,0,0,0)+bytes.fromhex('c1832a9e')
        return bytes(header)+payload+trailer

    def decode(self,b):
        # Use a project-specific scratch override if supplied by the test runner.
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.uexp';path.write_bytes(b)
            return thumbnail_decoder.decode_thumbnail(path)

    def test_bgra_channels(self):
        for offset in (117,120):
            b=self.fixture('PF_B8G8R8A8',bytes([10,20,30,255])*16,offset)
            image,meta=self.decode(b)
            self.assertEqual(image.getpixel((0,0)),(30,20,10,255))
            self.assertEqual(meta['payload_offset'],offset)

    def test_bc1(self):
        # RGB565 red endpoint and zero selectors => red block.
        b=self.fixture('PF_DXT1',struct.pack('<HHI',0xf800,0,0),113)
        image,meta=self.decode(b)
        self.assertEqual(image.size,(4,4))
        self.assertEqual(image.getpixel((0,0))[:3],(255,0,0))

    def test_invalid_footer_and_layout_rejected(self):
        b=self.fixture('PF_DXT1',struct.pack('<HHI',0xf800,0,0),113)
        with self.assertRaises(ValueError):self.decode(b[:-1]+b'X')
        with self.assertRaises(ValueError):self.decode(b[:113]+b'X'+b[113:])


if __name__ == '__main__':
    unittest.main()
