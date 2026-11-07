import importlib
import unittest
import tempfile,json
from unittest.mock import patch
from pathlib import Path

class ExteriorProfileTests(unittest.TestCase):
    def test_native_small_component_transforms_and_slots(self):
        mod=importlib.import_module('ffxiv_furniture.exteriors')
        actors=mod.native_exterior_actors('Small')
        self.assertEqual(len(actors),30)
        byname={a['name']:a for a in actors}
        self.assertEqual(byname['MainDoor']['category'],'MainDoor')
        self.assertEqual(byname['MainDoor']['translation_m'],[-4.0,2.0,.5])
        self.assertEqual(byname['MistSmallOutsideWall']['translation_m'],[-4.,-4.,0.])
        self.assertEqual(byname['OutsideGround_2']['translation_m'],[0.,0.,0.])
        self.assertAlmostEqual(byname['OutsideWall2_9']['yaw_degrees'],-90.,places=3)
        self.assertTrue(all(a['map_sha256'] and a['component_export'] for a in actors))
    def test_fixture_replacement_preserves_native_poses_and_size_guard(self):
        mod=importlib.import_module('ffxiv_furniture.exteriors')
        p=mod.ExteriorProfile('Small',[dict(type='Roof',name='Glade Cottage Roof (Wood)'),dict(type='Fence',name='Glade Hedgewall')])
        actors=p.scene()
        self.assertTrue(any('GladeCottageRoof' in a['mesh'] for a in actors))
        fences=[a for a in actors if a['category']=='Fence']
        self.assertEqual(len(fences),19)
        self.assertTrue(all('GladeHedgewall' in a['mesh'] for a in fences))
        self.assertEqual(next(a for a in actors if a['name']=='MainDoor')['translation_m'],[-4.,2.,.5])
        with self.assertRaises(ValueError):mod.ExteriorProfile('Small',[dict(type='Roof',name='Riviera Mansion Roof (Wood)')]).scene()
        for size,n in [('Small',30),('Medium',42),('Large',60)]:
            self.assertEqual(len(mod.native_exterior_actors(size)),n)
            self.assertGreater(mod.ExteriorProfile(size).polygon().area,100)
    def test_outdoor_pipeline_renders_furniture_and_native_selected_structure(self):
        from ffxiv_furniture.rendering.pipeline import run_pipeline
        root=Path(__file__).resolve().parents[1]
        lay=json.loads((root/'data/seeds/apartment-seed.json').read_bytes())
        lay.update(houseSize='Small',exteriorScale=100,exteriorFixture=[dict(type='Roof',name='Glade Cottage Roof (Wood)')],exteriorFurniture=[dict(itemId=6475,name='Moogle Letter Box',transform=dict(location=[600,500,0],rotation=[0,0,0,1],scale=[1,1,1]),properties={},attachments=[])])
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'renders'
            m=run_pipeline(lay,out,scope='exterior',size=(160,120),image_prefix='yard')
            self.assertEqual(m['scope'],'exterior')
            self.assertTrue(any(x.get('item_id')==6475 for x in m['objects'].values()))
            self.assertTrue(any('GladeCottageRoof' in x.get('source','') for x in m['objects'].values()))
            self.assertTrue(all(p.suffix=='.jpg' for p in out.iterdir()))
            self.assertTrue(any(v['visible_object_pixels'].get('1',0)>0 for v in m['views']))
    def test_yard_session_scope_fixtures_history_and_export_preserve_indoor_data(self):
        from ffxiv_furniture.deco.exterior import ExteriorCatalog,ExteriorRoom,ExteriorSession
        from ffxiv_furniture.deco.core import DecoError
        root=Path(__file__).resolve().parents[1];lay=json.loads((root/'data/seeds/apartment-seed.json').read_bytes());lay.update(houseSize='Small',exteriorScale=10)
        indoor=dict(itemId=123,name='untouched indoor sentinel',transform={'unknown':'preserve'},properties={'on':True})
        lay['interiorFurniture']=[indoor]
        cat=ExteriorCatalog('Small');self.addCleanup(cat.db.close)
        self.assertEqual(cat.item(6475)['name'],'Moogle Letter Box')
        with self.assertRaises(DecoError):cat.item(6583)
        with tempfile.TemporaryDirectory() as tmp:
            session=ExteriorSession('test',cat,ExteriorRoom('Small'),tmp,seed_layout=lay,max_patch=7.2)
            session.apply([dict(op='place',item_id=6475,position=[6,5,0])])
            snap=session.snapshot('before roof')
            session.apply([dict(op='fixture',type='Roof',name='Glade Cottage Roof (Wood)')])
            self.assertTrue(any(f['name']=='Glade Cottage Roof (Wood)' for f in session.layout_dict()['exteriorFixture']))
            session.undo();session.redo();session.restore(snap['snapshot_id'])
            self.assertFalse(any(f['name']=='Glade Cottage Roof (Wood)' for f in session.layout_dict()['exteriorFixture']))
            exported=session.export('yard');back=json.loads(Path(exported['layout']['path']).read_bytes())
            self.assertEqual(back['interiorFurniture'],[indoor]);self.assertEqual(back['interiorFixture'],lay['interiorFixture'])
            self.assertEqual(back['exteriorScale'],10);self.assertEqual(len(back['exteriorFurniture']),1)
            resumed=ExteriorSession('test',cat,ExteriorRoom('Small'),tmp)
            self.assertEqual(resumed.state_hash(),session.state_hash())
            from ffxiv_furniture.deco import server
            with patch.object(server,'_boot',return_value=session),patch.object(server,'_sess',session),patch.object(server,'_cat',cat):
                result=server.set_exterior(roof='Glade Cottage Roof (Wood)',fence='Glade Hedgewall',expected_revision=session.revision)
                self.assertTrue(result['ok'])
                rendered=server.render(view='overview',width=160,height=120,lighting='off')
                meta=json.loads(rendered[-1]);self.assertEqual(meta['scope'],'exterior')
                self.assertEqual(Path(meta['image']).parent.resolve(),(session.dir/'renders').resolve())

    def test_refresh_indoor_replaces_only_non_exterior_fields(self):
        from ffxiv_furniture.deco.exterior import ExteriorCatalog,ExteriorRoom,ExteriorSession
        from ffxiv_furniture.deco.core import DecoError
        root=Path(__file__).resolve().parents[1];lay=json.loads((root/'data/seeds/apartment-seed.json').read_bytes());lay.update(houseSize='Small',exteriorScale=10)
        lay['interiorFurniture']=[dict(itemId=1,name='old indoor',transform={},properties={})]
        cat=ExteriorCatalog('Small');self.addCleanup(cat.db.close)
        with tempfile.TemporaryDirectory() as tmp:
            session=ExteriorSession('test',cat,ExteriorRoom('Small'),tmp,seed_layout=lay,max_patch=7.2)
            session.apply([dict(op='place',item_id=6475,position=[6,5,0],instance_id='box')])
            session.apply([dict(op='fixture',type='Roof',name='Glade Cottage Roof (Wood)')])
            before=session.layout_dict();rev=session.revision
            newer=json.loads(json.dumps(lay));newer['interiorFurniture']=[dict(itemId=2,name='new indoor',transform={},properties={})]
            newer['interiorFixture']=newer['interiorFixture'][:1];newer['exteriorFurniture']=[];newer['exteriorFixture']=[]
            src=Path(tmp)/'interior-r9.json';src.write_bytes(b'\xff\xfe'+json.dumps(newer).encode('utf-16-le'))
            r=session.refresh_indoor(src)
            self.assertEqual(r['revision'],rev+1);self.assertIn('interiorFurniture',r['changed_fields'])
            after=session.layout_dict()
            self.assertEqual(after['interiorFurniture'],newer['interiorFurniture']);self.assertEqual(after['interiorFixture'],newer['interiorFixture'])
            self.assertEqual(after['exteriorFurniture'],before['exteriorFurniture']);self.assertEqual(after['exteriorFixture'],before['exteriorFixture'])
            self.assertEqual(ExteriorSession('test',cat,ExteriorRoom('Small'),tmp).layout_dict()['interiorFurniture'],newer['interiorFurniture'])
            other=json.loads(json.dumps(newer));other['houseSize']='Medium';bad=Path(tmp)/'m.json';bad.write_text(json.dumps(other),encoding='utf-8')
            with self.assertRaises(DecoError):session.refresh_indoor(bad)
            self.assertEqual(session.revision,rev+1)
            from ffxiv_furniture.deco import server
            from mcp.server.fastmcp.exceptions import ToolError
            with patch.object(server,'_boot',return_value=session),patch.object(server,'_sess',session):
                self.assertEqual(server.refresh_indoor(layout_path=str(src))['revision'],rev+2)
                with self.assertRaises(ToolError):server.refresh_indoor(layout_path=str(bad))

if __name__=='__main__':unittest.main()
