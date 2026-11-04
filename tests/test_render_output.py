"""Normal previews are flat PNG-only output; diagnostics must be explicit."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
import numpy as np
from PIL import Image
from ffxiv_furniture.rendering.pipeline import run_pipeline

ROOT=Path(__file__).resolve().parents[1]
SEED=json.loads((ROOT/'data/seeds/apartment-seed.json').read_bytes())
CAM=dict(name='entry',position=[0,5,1.65],target=[0,-4,1.65],fov=85)

class MinimalRenderOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source.json'
        self.layout=deepcopy(SEED);self.layout.update(houseSize='Small',interiorFurniture=[])
        self.source.write_text(json.dumps(self.layout),encoding='utf-8')
    def run_scene(self,out,**kwargs):
        return run_pipeline(self.source,out,room_context=True,db_path=ROOT/'data/furniture.sqlite3',cameras=[CAM],size=(96,64),mirror_view=False,**kwargs)
    def test_default_writes_only_requested_png(self):
        out=self.root/'renders';m=self.run_scene(out)
        self.assertEqual({p.name for p in out.iterdir()},{'view-01.png'})
        self.assertIsNone(m['rendered_layout'])
        self.assertTrue(m['views'][0]['visible_object_pixels'])
    def test_different_prefixes_share_one_flat_directory(self):
        out=self.root/'renders'
        a=self.run_scene(out,image_prefix='r0-entry-abc')
        b=self.run_scene(out,image_prefix='r0-north-def')
        self.assertEqual({p.name for p in out.iterdir()},{'r0-entry-abc-01.png','r0-north-def-01.png'})
        self.assertNotEqual(a['views'][0]['image'],b['views'][0]['image'])
        with self.assertRaises(ValueError):self.run_scene(out,image_prefix='r0-entry-abc')
    def test_explicit_artifacts_preserve_diagnostics_and_pixels(self):
        out=self.root/'renders';a=self.run_scene(out,image_prefix='plain')
        b=self.run_scene(out,image_prefix='debug',artifacts=True)
        self.assertEqual({p.name for p in out.iterdir()},{'plain-01.png','debug-01.png','debug-layout.json','debug-manifest.json','debug-review-request.json'})
        self.assertTrue(np.array_equal(np.asarray(Image.open(a['views'][0]['image'])),np.asarray(Image.open(b['views'][0]['image']))))
        self.assertEqual(json.loads((out/'debug-manifest.json').read_text(encoding='utf-8'))['rendered_layout'],b['rendered_layout'])
    def test_in_memory_layout_needs_no_source_file(self):
        before=deepcopy(self.layout);out=self.root/'renders'
        m=run_pipeline(self.layout,out,room_context=True,db_path=ROOT/'data/furniture.sqlite3',cameras=[CAM],size=(96,64))
        self.assertEqual(self.layout,before);self.assertIsNone(m['input_layout'])
        self.assertEqual({p.name for p in out.iterdir()},{'view-01.png'})
    def test_unsafe_prefix_is_refused_before_output(self):
        out=self.root/'renders'
        for prefix in ('../escape','a/b','a\\b','', 'dot.name'):
            with self.subTest(prefix=prefix),self.assertRaises(ValueError):self.run_scene(out,image_prefix=prefix)
        self.assertFalse(out.exists())
    def test_cli_explicit_prefix_defaults_to_png_only(self):
        out=self.root/'renders';cams=self.root/'cameras.json';cams.write_text(json.dumps([CAM]),encoding='utf-8')
        result=subprocess.run([sys.executable,'-m','ffxiv_furniture.rendering','--layout',str(self.source),'--output-dir',str(out),'--cameras',str(cams),'--room-context','--image-prefix','entry','--width','96','--height','64'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual({p.name for p in out.iterdir()},{'entry-01.png'})

if __name__=='__main__':unittest.main()
