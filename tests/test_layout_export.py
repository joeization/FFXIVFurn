import importlib.util
import math
from pathlib import Path
import unittest
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.layout import build_layout

spec=importlib.util.spec_from_file_location('build_test_catalog',Path(__file__).resolve().parents[1]/'scripts/build_test_catalog.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class LayoutTests(unittest.TestCase):
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
        self.assertEqual(module.canonical_id(concepts,'old'),'wood')
        self.assertEqual(module.canonical_id(concepts,'dark'),'dark')
        self.assertEqual(module.canonical_id(concepts,'carved-style'),'carved-ornament')
        self.assertIsNone(module.canonical_id(concepts,'unknown'))
        concepts['wood']={'status':'merged','merged_into':'old'}
        with self.assertRaises(ValueError):module.canonical_id(concepts,'old')


if __name__=='__main__':unittest.main()
