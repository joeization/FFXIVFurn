"""Exercise the real server render function/GPU with isolated session adapters."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from ffxiv_furniture.deco import server

ROOT=Path(__file__).resolve().parents[1]

class MCPFlatOutputTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        lay=json.loads((ROOT/'data/seeds/apartment-seed.json').read_bytes());lay.update(houseSize='Small',interiorFurniture=[])
        def write_layout(path):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(lay),encoding='utf-8')
        self.lay=lay
        self.session=SimpleNamespace(dir=self.root,revision=0,room=SimpleNamespace(house_size='Small',style='Shirogane'),instances={},layout_dict=lambda:deepcopy(lay),write_layout=write_layout)
        self.boot=patch.object(server,'_boot',return_value=self.session);self.boot.start();self.addCleanup(self.boot.stop)
        self.sess=patch.object(server,'_sess',self.session);self.sess.start();self.addCleanup(self.sess.stop)
    def render(self,view='entry',**kwargs):
        result=server.render(view=view,width=96,height=64,lighting='off',mirror=False,**kwargs)
        return json.loads(result[-1])
    def test_views_share_jpeg_only_directory_and_repeat_hits_cache(self):
        a=self.render();b=self.render('north');again=self.render()
        out=self.root/'renders'
        self.assertEqual(Path(a['image']).parent.resolve(),out.resolve())
        self.assertEqual(Path(b['image']).parent.resolve(),out.resolve())
        self.assertNotEqual(a['image'],b['image']);self.assertTrue(again['cache_hit'])
        self.assertEqual(a['image'],again['image'])
        self.assertEqual(len(list(out.iterdir())),2)
        self.assertTrue(all(p.is_file() and p.suffix=='.jpg' for p in out.iterdir()))
        self.assertFalse(list(out.rglob('*.json')))
    def sheet(self,views,**kwargs):
        result=server.render_sheet(views=views,width=96,height=64,lighting='off',mirror=False,**kwargs)
        return result[-1] if isinstance(result[-1],dict) else json.loads(result[-1])
    def test_render_sheet_returns_one_jpeg_with_every_panel(self):
        from PIL import Image
        views=[{'label':'A entry','view':'entry'},{'label':'B north','view':'north'},{'label':'C custom','view':{'position':[0,0,2],'target':[0,-3,1],'fov':70}}]
        m=self.sheet(views,cols=2)
        self.assertEqual(Path(m['image']).suffix,'.jpg')
        with Image.open(m['image']) as im:
            self.assertEqual(im.format,'JPEG')
            self.assertEqual(im.size,(2*96,2*(64+server.SHEET_TITLE_PX)))
        self.assertEqual([p['label'] for p in m['panels']],['A entry','B north','C custom'])
        out=self.root/'renders'
        self.assertEqual([p.name for p in out.iterdir()],[Path(m['image']).name])   # panels stay in memory: only the sheet is written
        again=self.sheet(views,cols=2)
        self.assertEqual(again['image'],m['image']);self.assertTrue(all(p['cache_hit'] for p in again['panels']))
        self.assertEqual(len(list(out.iterdir())),1)
    def bump(self):
        self.session.revision+=1;self.lay['revision_marker']=self.session.revision   # an edit changes the layout
    def test_old_revisions_are_pruned_but_kept_files_survive(self):
        out=self.root/'renders'
        kept=self.render(keep=True)['image'];self.assertIn('-keep',Path(kept).name)
        self.render();self.bump();self.render('north');self.bump();self.render();self.bump();self.render()
        revs=sorted({int(p.name.split('-')[0][1:]) for p in out.iterdir() if '-keep' not in p.name})
        self.assertEqual(revs,[2,3])   # only the newest two revisions on disk
        self.assertTrue(Path(kept).is_file())
        s=self.sheet([{'label':'A','view':'entry'}],keep=True);self.assertIn('-keep',Path(s['image']).name)
        self.bump();self.render();self.bump();self.render()
        self.assertTrue(Path(s['image']).is_file());self.assertTrue(Path(kept).is_file())
    def test_render_sheet_rejects_bad_input(self):
        from mcp.server.fastmcp.exceptions import ToolError
        for views,cols in (([],2),([{'label':'x','view':'entry'}]*13,2),([{'label':'x','view':'entry'}],0),([{'view':'entry'}],2)):
            with self.subTest(n=len(views),cols=cols),self.assertRaises(ToolError):
                server.render_sheet(views=views,cols=cols,width=96,height=64,lighting='off')
    def test_crop_is_jpeg(self):
        a=self.render(crop=[0,0,48,32])
        self.assertEqual(Path(a['image']).suffix,'.jpg')
        from PIL import Image
        with Image.open(a['image']) as im:self.assertEqual((im.format,im.size),('JPEG',(48,32)))
    def test_diagnostics_are_explicit_flat_and_named(self):
        a=self.render();b=self.render(diagnostics=True)
        self.assertTrue(b['artifacts'])
        for filename in b['artifacts'].values():self.assertEqual(Path(filename).parent.resolve(),(self.root/'renders').resolve());self.assertTrue(Path(filename).is_file())
        self.assertTrue(Path(a['image']).is_file())
        self.assertFalse(any(p.is_dir() for p in (self.root/'renders').iterdir()))
    def test_cache_missing_image_is_regenerated_and_labels_crop_work(self):
        a=self.render();Path(a['image']).unlink();b=self.render()
        self.assertFalse(b['cache_hit']);self.assertTrue(Path(b['image']).is_file())
        labeled=self.render(labels=True,crop=[0,0,64,48])
        from PIL import Image
        with Image.open(labeled['image']) as image:self.assertEqual(image.size,(64,48))
        self.assertIn('labeled',Path(labeled['image']).name)
        self.assertEqual(Path(labeled['image']).parent,self.root/'renders')
        self.assertFalse(list((self.root/'renders').rglob('*.json')))
    def test_bounded_cache_eviction_regenerates_without_new_folders(self):
        with patch.object(server,'_RENDER_CACHE_LIMIT',1):
            a=self.render();self.render('north');again=self.render()
            self.assertLessEqual(len(server._render_cache),1)
        self.assertFalse(again['cache_hit']);self.assertEqual(a['image'],again['image'])
        self.assertEqual(len(list((self.root/'renders').iterdir())),2)

if __name__=='__main__':unittest.main()
