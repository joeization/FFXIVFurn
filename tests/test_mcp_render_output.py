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
        self.session=SimpleNamespace(dir=self.root,revision=0,room=SimpleNamespace(house_size='Small',style='Shirogane'),instances={},layout_dict=lambda:deepcopy(lay),write_layout=write_layout)
        self.boot=patch.object(server,'_boot',return_value=self.session);self.boot.start();self.addCleanup(self.boot.stop)
        self.sess=patch.object(server,'_sess',self.session);self.sess.start();self.addCleanup(self.sess.stop)
    def render(self,view='entry',**kwargs):
        result=server.render(view=view,width=96,height=64,lighting='off',mirror=False,**kwargs)
        return json.loads(result[-1])
    def test_views_share_png_only_directory_and_repeat_hits_cache(self):
        a=self.render();b=self.render('north');again=self.render()
        out=self.root/'renders'
        self.assertEqual(Path(a['image']).parent,out)
        self.assertEqual(Path(b['image']).parent,out)
        self.assertNotEqual(a['image'],b['image']);self.assertTrue(again['cache_hit'])
        self.assertEqual(a['image'],again['image'])
        self.assertEqual(len(list(out.iterdir())),2)
        self.assertTrue(all(p.is_file() and p.suffix=='.png' for p in out.iterdir()))
        self.assertFalse(list(out.rglob('*.json')))
    def test_diagnostics_are_explicit_flat_and_named(self):
        a=self.render();b=self.render(diagnostics=True)
        self.assertTrue(b['artifacts'])
        for filename in b['artifacts'].values():self.assertEqual(Path(filename).parent,self.root/'renders');self.assertTrue(Path(filename).is_file())
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
