"""Renderer guards and real-asset regressions; no model inference."""
from copy import deepcopy
import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
if not all(importlib.util.find_spec(m) for m in ['numpy','shapely','PIL']):raise unittest.SkipTest('Optional render dependencies not installed')
import numpy as np
from PIL import Image
from ffxiv_furniture.rendering.raster import render
from ffxiv_furniture.rendering.pipeline import quaternion_matrix,apply_patch,run_pipeline
from ffxiv_furniture.rendering.assets import mesh_materials,sections
from ffxiv_furniture.rendering.native import material_instance
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
ROOT=Path(__file__).resolve().parents[1]

class RenderTests(unittest.TestCase):
    def test_depth_id16_and_near_clipping(self):
        near=np.array([[-1,2,-1],[1,2,-1],[0,2,1]]);far=near*2
        camera={'position':[0,0,0],'target':[0,1,0]}
        with tempfile.TemporaryDirectory() as temp:
            for meshes in [[{'id':300,'vertices':near,'triangles':[(0,1,2)]},{'id':400,'vertices':far,'triangles':[(0,1,2)]}],
                           [{'id':400,'vertices':far,'triangles':[(0,1,2)]},{'id':300,'vertices':near,'triangles':[(0,1,2)]}]]:
                path=Path(temp)/'view.png';render(meshes,camera,path,size=(160,120),debug_buffers=True)
                with Image.open(Path(temp)/'view-ids.png') as im:self.assertEqual(np.asarray(im)[60,80],300)
                self.assertAlmostEqual(float(np.load(Path(temp)/'view-depth.npy')[60,80]),2)
            vertices=np.array([[-.05,.05,-.05],[.1,.3,-.05],[0,.3,.15]])
            result=render([{'id':1,'vertices':vertices,'triangles':[(0,1,2)]}],camera,Path(temp)/'clip.png',size=(160,120))
            self.assertEqual(result['near_clipped_triangles'],1);self.assertTrue(result['visible_object_pixels'])

    def test_only_requested_image_is_written(self):
        mesh=[{'id':300,'vertices':np.array([[-1,2,-1],[1,2,-1],[0,2,1]]),'triangles':[(0,1,2)],'role':'furniture'}]
        camera={'position':[0,0,0],'target':[0,1,0]}
        for fn in (render,):
            for labels in (False,True):
                with self.subTest(backend=fn.__name__,labels=labels), tempfile.TemporaryDirectory() as tmp:
                    result=fn(mesh,camera,Path(tmp)/'view.png',size=(160,120),labels=labels)
                    files={f.name for f in Path(tmp).iterdir()}
                    expected='view-labeled.png' if labels else 'view.png'
                    self.assertEqual(files,{expected})
                    self.assertEqual(Path(result['image']).name,expected)
                    self.assertEqual('labeled' in result,labels)
                    self.assertNotIn('ids',result);self.assertNotIn('depth',result)
                    self.assertGreater(result['visible_object_pixels']['300'],0)

    def test_debug_buffers_are_explicit_and_do_not_add_plain_duplicate(self):
        mesh=[{'id':300,'vertices':np.array([[-1,2,-1],[1,2,-1],[0,2,1]]),'triangles':[(0,1,2)],'role':'furniture'}]
        camera={'position':[0,0,0],'target':[0,1,0]}
        with tempfile.TemporaryDirectory() as tmp:
            result=render(mesh,camera,Path(tmp)/'view.png',size=(160,120),labels=True,debug_buffers=True)
            self.assertEqual({f.name for f in Path(tmp).iterdir()},{'view-labeled.png','view-ids.png','view-depth.npy'})
            self.assertEqual(np.asarray(Image.open(result['ids']))[60,80],300)
            self.assertAlmostEqual(float(np.load(result['depth'])[60,80]),2)

    def layout(self):
        return {'houseSize':'Medium','interiorScale':100,'interiorFurniture':[{'itemId':1,'name':'fixture','transform':{'location':[400,-300,0],'rotation':[0,0,0,1],'scale':[1,1,1]}}],'unknown':'keep'}

    def test_free_yaw_patch_preserves_source(self):
        layout=self.layout();before=deepcopy(layout)
        result=apply_patch(layout,{'base_layout_sha256':'a','changes':[{'instance_id':'furniture-0001','yaw_delta_degrees':17.5}]},'a')
        self.assertEqual(layout,before);self.assertEqual(result['unknown'],'keep')
        q=result['interiorFurniture'][0]['transform']['rotation'];m=quaternion_matrix(q)
        self.assertAlmostEqual(np.linalg.det(m),1);self.assertGreater(abs(q[2]),0)

    def test_bad_patch_bounds_and_identity_rejected(self):
        for patch in [{'base_layout_sha256':'wrong','changes':[]},{'base_layout_sha256':'a','changes':[{'instance_id':'furniture-0001','item_id':999}]},
            {'base_layout_sha256':'a','changes':[{'instance_id':'furniture-0001','delta_translation_m':[3,0,0]}]},
            {'base_layout_sha256':'a','changes':[{'instance_id':'furniture-0001','yaw_delta_degrees':float('nan')}]}]:
            with self.assertRaises(ValueError):apply_patch(self.layout(),patch,'a')

@unittest.skipUnless((ROOT/'outputs/geometry/fill-result.json').exists(),'Local assets absent')
class NativeRenderTests(unittest.TestCase):
    def test_all57_material_slot_and_section_ranges(self):
        records=json.loads((ROOT/'outputs/geometry/fill-result.json').read_text())['records']
        for r in records:
            v,t=read_static_mesh_triangles(r);m=mesh_materials(Path(r['source']).with_suffix('.uasset'));s=sections(r,t,len(m))
            self.assertEqual(sum(x['triangle_count'] for x in s),len(t))

    def test_scalar_vector_texture_fields_do_not_overwrite_outer_header(self):
        p=ROOT/'data/geometry-legacy/MakePlace/Content/GameAssets/Furniture/Chair/LeatherSofa/MI_LeatherSofa_0.uasset'
        m=material_instance(p)
        self.assertTrue({'Base','Normal','Specular','Tint'}<=set(m['parameters']))

    def test_actual_layout_to_artifacts(self):
        p=ROOT/'outputs/opus-one-floor/Opus_GroundFloor.json'
        if not p.exists():self.skipTest('Sample layout absent')
        layout=json.loads(p.read_bytes());item=next(i for i in layout['interiorFurniture'] if i['itemId']==28639);layout['interiorFurniture']=[item]
        item['transform']['location']=[450,-300,2.0934982299804688]
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.json';source.write_text(json.dumps(layout),encoding='utf-8');out=Path(temp)/'out'
            db=ROOT/'data/furniture-test.sqlite3';before_hash=hashlib.sha256(db.read_bytes()).hexdigest()
            m=run_pipeline(source,out,cameras=[{'position':[0,7,1.65],'target':[4.5,-3,.7]}],size=(160,120),artifacts=True)
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),before_hash)
            self.assertTrue(Path(m['views'][0]['image']).exists())
            self.assertNotIn('ids',m['views'][0]);self.assertNotIn('labeled',m['views'][0])
            self.assertFalse(list(out.glob('*-ids.png')));self.assertFalse(list(out.glob('*-labeled.png')))
            self.assertEqual(m['geometry_assets'],1);self.assertEqual(m['textured_slots'],1);self.assertTrue((out/'review-request.json').exists())
            self.assertEqual(json.loads((out/'layout.json').read_bytes())['interiorFurniture'][0]['name'],'Leather Sofa')
            with self.assertRaises(ValueError):run_pipeline(source,out)

if __name__=='__main__':unittest.main()


@unittest.skipUnless((ROOT/'data/furniture.sqlite3').exists() and (ROOT/'outputs/render-pipeline/multi-size/Large.json').exists(),'real DB / demo layouts absent')
class DbGeometryRenderTests(unittest.TestCase):
    def test_non_57_furniture_in_large_house_from_db_geometry(self):
        import tempfile
        known={r['item_id'] for r in json.loads((ROOT/'outputs/geometry/fill-result.json').read_text())['records']}
        source=ROOT/'outputs/render-pipeline/multi-size/Large.json'
        raw=source.read_bytes();layout=json.loads(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8'))
        self.assertTrue({i['itemId'] for i in layout['interiorFurniture']}-known,'demo must use furniture outside the original 57')
        with tempfile.TemporaryDirectory() as tmp:
            m=run_pipeline(source,Path(tmp)/'run',db_path=ROOT/'data/furniture.sqlite3',size=(160,120))
            self.assertEqual(len(m['views']),4);self.assertGreater(m['material_slots'],0)
            self.assertTrue(any('auto-framed' in w for w in m['warnings']))

    def test_unknown_house_size_refused(self):
        import tempfile
        raw=(ROOT/'outputs/render-pipeline/multi-size/Large.json').read_bytes();layout=json.loads(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8'))
        layout['houseSize']='Gigantic'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'l.json';p.write_text(json.dumps(layout),encoding='utf-8')
            with self.assertRaises(ValueError):run_pipeline(p,Path(tmp)/'run',db_path=ROOT/'data/furniture.sqlite3')


class MirrorViewTests(unittest.TestCase):
    def test_mirror_is_exact_horizontal_flip_of_raw_projection(self):
        mesh=[{'id':1,'vertices':np.array([[0.5,4,0],[2.5,4,0],[1.0,4,2]],float),'triangles':np.array([[0,1,2]]),'role':'furniture'}]
        cam={'position':[0,0,1],'target':[0,4,1],'fov':70}
        with tempfile.TemporaryDirectory() as tmp:
            render(mesh,cam,Path(tmp)/'a.png',size=(96,64),debug_buffers=True);render(mesh,{**cam,'mirror_x':True},Path(tmp)/'b.png',size=(96,64),debug_buffers=True)
            a=np.asarray(Image.open(Path(tmp)/'a-ids.png'));b=np.asarray(Image.open(Path(tmp)/'b-ids.png'))
        self.assertTrue((a!=a[:, ::-1]).any(),'scene must be asymmetric for the test to mean anything')
        self.assertTrue(np.array_equal(b,a[:, ::-1]),'object-ID mask must be an exact left-right flip')
