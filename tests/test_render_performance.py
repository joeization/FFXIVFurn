"""Regression tests for redundant render work; no timing thresholds."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from ffxiv_furniture.rendering.assets import Assets

class AssetReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.content=self.root/'Content';self.content.mkdir()
        record={'item_id':42,'source':str(self.content/'Mesh.uexp'),'source_sha256':'source'}
        self.assets=Assets([record],self.root/'cache',mi_tint=True)
        self.geometry=self.patch('ffxiv_furniture.rendering.assets.read_static_mesh_triangles',return_value=(np.array([[0,0,0],[1,0,0],[0,1,0]]),np.array([[0,1,2]])))
        self.patch('ffxiv_furniture.rendering.assets.uvs',return_value=np.zeros((3,2)))
        self.patch('ffxiv_furniture.rendering.assets.mesh_materials',return_value=[{'resolved':'/Game/Material.MI'}])
        self.patch('ffxiv_furniture.rendering.assets.sections',return_value=[{'material_index':0,'first_triangle':0,'triangle_count':1}])
        self.patch('ffxiv_furniture.rendering.assets.native.material_instance',return_value={'parent':'/Game/M_MasterTint','parameters':{'Base':{'kind':'texture','value':'/Game/Base'},'Tint':{'value':[1,1,1,1]}},'source_sha256':'material'})
        self.decode=self.patch('ffxiv_furniture.rendering.assets.native.decode_texture',side_effect=lambda p:(Image.new('RGBA',(2,2),(255,255,255,255)),{'source_file_hashes':{'Base.uexp':'texture'}}))
    def patch(self,*args,**kwargs):
        p=patch(*args,**kwargs);m=p.start();self.addCleanup(p.stop);return m
    def test_same_asset_returns_same_decoded_mesh(self):
        a=self.assets.load(42);b=self.assets.load(42)
        self.assertIs(a,b)
        self.assertEqual(self.geometry.call_count,1)
        self.assertEqual(self.decode.call_count,1)
        self.assertEqual(len(self.assets.coverage),1)
    def test_dye_variants_are_independent_and_reused(self):
        red=self.assets.load(42,(255,0,0));green=self.assets.load(42,(0,255,0));red2=self.assets.load(42,(255,0,0))
        self.assertIs(red,red2);self.assertIsNot(red,green)
        self.assertFalse(np.array_equal(red['materials'][0]['texture'],green['materials'][0]['texture']))
        self.assertEqual(self.geometry.call_count,2);self.assertEqual(len(self.assets.coverage),2)

    def shared(self):
        import inspect
        from ffxiv_furniture.rendering import assets
        self.assertIn('resource_cache',inspect.signature(Assets).parameters,'cross-view decoded resource reuse is missing')
        return assets.DecodedAssetCache(max_bytes=1024*1024,max_entries=4)
    def clone(self,cache):
        return Assets(list(self.assets.records.values()),self.root/'cache',mi_tint=True,resource_cache=cache)
    def test_cross_view_resource_reuse_and_source_invalidation(self):
        cache=self.shared();a=self.clone(cache).load(42);b=self.clone(cache).load(42)
        self.assertIs(a,b);self.assertEqual(self.geometry.call_count,1)
        (self.content/'Mesh.uexp').write_bytes(b'changed source')
        c=self.clone(cache).load(42);self.assertIsNot(a,c);self.assertEqual(self.geometry.call_count,2)
    def test_missing_material_creation_invalidates_cached_fallback(self):
        cache=self.shared();a=self.clone(cache).load(42)
        (self.content/'Material.uasset').write_bytes(b'new higher-priority asset')
        b=self.clone(cache).load(42);self.assertIsNot(a,b)
    def test_resource_cache_is_bounded(self):
        from ffxiv_furniture.rendering import assets
        self.shared();cache=assets.DecodedAssetCache(max_bytes=1,max_entries=4)
        self.clone(cache).load(42);self.clone(cache).load(42)
        self.assertEqual(cache.stats()['entries'],0);self.assertEqual(self.geometry.call_count,2)
    def test_cross_view_dye_variants_do_not_alias(self):
        cache=self.shared();a=self.clone(cache).load(42,(255,0,0));b=self.clone(cache).load(42,(0,255,0));c=self.clone(cache).load(42,(255,0,0))
        self.assertIs(a,c);self.assertIsNot(a,b)

class ProjectionReuseTests(unittest.TestCase):
    def api(self):
        import importlib
        try:return importlib.import_module('ffxiv_furniture.rendering.projection')
        except ModuleNotFoundError:self.fail('camera-independent exact projection cache is missing')
    def ring(self):
        v=np.array([[-2,-2,0],[2,-2,0],[2,2,0],[-2,2,0],[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],float)
        t=np.array([(0,1,4),(1,5,4),(1,2,5),(2,6,5),(2,3,6),(3,7,6),(3,0,7),(0,4,7)])
        return v,t
    def test_exact_hole_and_concavity_not_a_bbox(self):
        from shapely.geometry import Point
        api=self.api();v,t=self.ring();p=api.projected_footprint(v,t)
        self.assertAlmostEqual(p.area,12);self.assertFalse(p.covers(Point(0,0)));self.assertTrue(p.covers(Point(1.5,0)))
    def test_identical_content_reuses_projection_but_edits_do_not(self):
        api=self.api();v,t=self.ring();p=api.projected_footprint(v,t)
        self.assertIs(p,api.projected_footprint(v.copy(),t.copy()))
        changed=v.copy();changed[:,0]+=10;q=api.projected_footprint(changed,t)
        self.assertAlmostEqual(q.bounds[0],8);self.assertIsNot(p,q)
    def test_tilted_geometry_and_degenerate_triangles(self):
        api=self.api();v,t=self.ring();original_y=v[:,1].copy();v[:,1]*=.5;v[:,2]=original_y*np.sqrt(3)/2
        self.assertAlmostEqual(api.projected_footprint(v,t).area,6)
        self.assertTrue(api.projected_footprint(np.array([[0,0,0],[0,0,1],[0,0,2]]),[(0,1,2)]).is_empty)

class GpuTextureReuseTests(unittest.TestCase):
    def test_repeated_material_uploads_texture_only_once(self):
        import inspect
        from types import SimpleNamespace
        from ffxiv_furniture.rendering.raster_gpu import _prepare
        self.assertIn('texture_pool',inspect.signature(_prepare).parameters,'per-scene GPU texture reuse is missing')
        class Context:
            def __init__(self):self.uploads=0
            def buffer(self,data):return SimpleNamespace()
            def vertex_array(self,*args):return SimpleNamespace()
            def texture(self,*args,**kwargs):self.uploads+=1;return SimpleNamespace()
        ctx=Context();pool={};tex=np.full((4,4,4),255,np.uint8);mesh={'id':1,'vertices':np.array([[0,1,0],[1,1,0],[0,1,1]],float),'triangles':[(0,1,2)],'material':{'texture':tex}}
        a=_prepare(ctx,None,mesh,None,texture_pool=pool);b=_prepare(ctx,None,{**mesh,'id':2},None,texture_pool=pool)
        self.assertIs(a['texture'],b['texture']);self.assertEqual(ctx.uploads,1)
        c=_prepare(ctx,None,{**mesh,'material':{'texture':tex,'cutout':True}},None,texture_pool=pool)
        self.assertIsNot(a['texture'],c['texture']);self.assertEqual(ctx.uploads,2)

class RendererVersionTests(unittest.TestCase):
    def test_helper_code_changes_invalidate_image_cache(self):
        import os
        from ffxiv_furniture.deco import server
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d=root/'ffxiv_furniture/rendering';d.mkdir(parents=True)
            for name in ('pipeline','raster','raster_gpu','house_materials','assets','native','projection','resources'):(d/(name+'.py')).write_text('# fixture')
            for name in ('interiors.py','geometry_mesh.py','house_profiles.py','deco/server.py','deco/core.py','deco/exterior.py','exteriors.py','rendering/exterior.py'):
                p=root/'ffxiv_furniture'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# fixture')
            for size in ('Small','Medium','Large'):
                for ext in ('.umap','.uexp'):
                    p=root/'data/house-legacy/MakePlace/Content/Maps'/('XIV'+size+'Exterior'+ext);p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# fixture')
            with patch.object(server,'ROOT',root):
                before=server._renderer_version();p=d/'projection.py';st=p.stat();os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns+1000000000));after=server._renderer_version()
            self.assertNotEqual(before,after,'new render helpers must invalidate completed image caches')

if __name__=='__main__':unittest.main()
