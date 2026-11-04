from contextlib import closing,redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.database import SCHEMA
from ffxiv_furniture.housing import HOUSING_LIMITS,validate_layout_budget,floor_access_policy
from ffxiv_furniture.layout import build_layout
from ffxiv_furniture.__main__ import main


class HousingTests(unittest.TestCase):
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

    @unittest.skipUnless(importlib.util.find_spec('sqlite_vec'),'optional sqlite_vec absent')
    def test_semantic_scope_filter_before_topk(self):
        from ffxiv_furniture.semantic import SemanticIndex,vector_blob
        with FurnitureDB(':memory:') as db:
            for i,scope in [(1,'exterior'),(2,'interior'),(3,None)]:db.add_furniture(i,str(i),'visual description',scope=scope)
            index=SemanticIndex(db,local_files_only=True)
            # Explicit mocked inference; real sqlite-vec SQL/filtering exercised.
            with patch.object(index.embedder,'embed',side_effect=lambda texts,**kw:[vector_blob([1]+[0]*383) for _ in texts]):
                index.refresh()
                self.assertEqual([r['furniture']['id'] for r in index.search('same appearance',top_k=1,scope='interior')],[2])
                self.assertEqual([r['furniture']['id'] for r in index.search('same appearance',top_k=1,scope='exterior')],[1])

if __name__=='__main__':unittest.main()
