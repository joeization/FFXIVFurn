"""Regression checks for shared native Medium interior geometry/state/render."""
import copy,json,tempfile,unittest
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from ffxiv_furniture.interiors import STYLES,InteriorProfile,medium_actor_transforms,transform_points,geometry
from ffxiv_furniture.deco.core import Catalog,Room,Session,DecoError,ROOT
from ffxiv_furniture.rendering.pipeline import run_pipeline

SEED=json.loads((ROOT/'outputs/designs/hand-tea-room/final-layout.json').read_bytes());SEED['interiorFurniture']=[]

class InteriorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cat=Catalog();self.addCleanup(self.cat.db.close)
    def session(self):return Session('test',self.cat,Room(),self.tmp.name,seed_layout=copy.deepcopy(SEED))

    def test_unknown_style_never_silently_uses_shirogane(self):
        with self.assertRaises(DecoError):Room('Dark Minimalist')
        with self.assertRaises(ValueError):InteriorProfile('unknown')

    def test_named_overrides_not_duplicate_global_transform(self):
        a=medium_actor_transforms()
        self.assertEqual(a['Stairs']['default']['translation_m'],[8,5,0])
        self.assertEqual(a['Stairs']['default']['yaw_degrees'],0)
        self.assertEqual(a['Stairs']['overrides']['Minimalist']['scale'],[-1,1,1])
        self.assertEqual(a['Stairs2_9']['default']['translation_m'],[-8,5,-7])
        self.assertEqual(a['Stairs2_9']['default']['scale'],[-1,1,1])

    def test_full_scale_rotation_translation(self):
        a=dict(scale=[-1,2,3],yaw_degrees=90,translation_m=[7,4,0])
        np.testing.assert_allclose(transform_points([[1,2,3]],a),[[3,3,9]],atol=1e-12)

    def test_room_uses_style_profile_floors_and_stair_points(self):
        for style in STYLES:
            with self.subTest(style=style):
                r=Room(style);p=InteriorProfile(style)
                self.assertLess(r.floor.symmetric_difference(p.polygon('ground')).area,1e-9)
                self.assertLess(r.upper.symmetric_difference(p.polygon('upper')).area,1e-9)
                np.testing.assert_allclose(r._stair_world('Stairs')[0],p.actor_world('Stairs')[0])
        self.assertGreater(Room('DarkMinimalist').floor.symmetric_difference(Room('Shirogane').floor).area,10)

    def test_native_stair_upper_landing_adjacency_all_styles(self):
        for style in STYLES:
            p=InteriorProfile(style);v,t=p.actor_world('Stairs')
            landing=unary_union([g for tr in t if all(abs(v[i,2]-7)<.18 for i in tr) and (g:=Polygon(v[tr,:2])).area>.01])
            # Styles have different tread/trim geometry; require a real band,
            # not an invented common area or a hull-inside-wall rule (ornament
            # can extend 0.3m into enclosure geometry).
            self.assertGreater(landing.area,.001,style)
            self.assertLess(landing.distance(p.polygon('upper')),.02,style)
            self.assertTrue(np.isfinite(v).all(),style)
            self.assertLess(v[:,2].min(),.1,style)
            self.assertGreater(v[:,2].max(),7,style)

    def test_ceiling_material_is_selected_per_style_not_shirogane_for_all(self):
        for style in STYLES:
            if style == 'DarkMinimalist':
                with self.assertRaises(ValueError): InteriorProfile(style).ceiling_texture()
            else:
                texture=InteriorProfile(style).ceiling_texture()
                self.assertIn('/'+style+'/',texture['provenance']['texture'].replace(chr(92),'/'))
                self.assertEqual(texture['provenance']['style'],style)

    def test_style_switch_preserves_furniture_undo_redo_snapshot(self):
        s=self.session();s.apply([dict(op='place',name='Hingan Chair',position=[0,-4,0],yaw_deg=37,instance_id='chair')]);before=copy.deepcopy(s.instances)
        snap=s.snapshot('original')['snapshot_id']
        s.apply([dict(op='interior',style='Minimalist')]);self.assertEqual(s.instances,before)
        self.assertEqual(s.room.style,'Minimalist');s.undo();self.assertEqual(s.room.style,'Shirogane')
        s.redo();self.assertEqual(s.room.style,'Minimalist');s.restore(snap);self.assertEqual(s.room.style,'Shirogane');self.assertEqual(s.instances,before)

    def test_style_persistence_and_export_district(self):
        s=self.session();s.apply([dict(op='interior',style='DarkMinimalist')])
        s2=Session('test',self.cat,Room('Mist'),self.tmp.name,seed_layout=copy.deepcopy(SEED))
        self.assertEqual(s2.room.style,'DarkMinimalist')
        result=s2.export('changed');back=json.loads(Path(result['layout']['path']).read_bytes())
        # Persisted geometry token stays compact; app export uses the display name.
        self.assertEqual(next(f['name'] for f in back['interiorFixture'] if f['type']=='District'),'Dark Minimalist')
        self.assertEqual(next(f['name'] for f in s2.layout_dict()['interiorFixture'] if f['type']=='District'),'Dark Minimalist')
        self.assertEqual(next(f['name'] for f in SEED['interiorFixture'] if f['type']=='District'),'Shirogane')

    def test_rejected_batch_does_not_change_style_or_geometry(self):
        s=self.session();before=s.state_hash();rev=s.revision
        with self.assertRaises(DecoError):s.apply([dict(op='interior',style='Minimalist'),dict(op='place',name='No Such Item',position=[0,0,0])])
        self.assertEqual(s.room.style,'Shirogane');self.assertEqual(s.state_hash(),before);self.assertEqual(s.revision,rev)
        with self.assertRaises(DecoError):s.apply([dict(op='interior',style='Typo')])
        self.assertEqual(s.state_hash(),before)

    def test_upper_wall_helpers_have_upper_geometry_and_relative_height(self):
        s=self.session();s.apply([dict(op='interior',style='Minimalist')]);info=s.inspect(level='upper')
        self.assertEqual(info['level'],'upper');self.assertEqual(info['style'],'Minimalist')
        w=next(w for w in info['walls'] if w['length']>8)
        s.apply([dict(op='place_along_wall',name='Oriental Wall Scroll',instance_id='scroll',level='upper',wall_id=w['wall_id'],along_m=w['length']/2,height_m=2)])
        self.assertEqual(s.instances['scroll']['pivot'][2],9)
        with self.assertRaises(DecoError):s.inspect(level='basement')

    def test_legacy_state_without_style_uses_original_seed(self):
        s=self.session();raw=json.loads((s.dir/'state.json').read_text());raw['state'].pop('style')
        (s.dir/'state.json').write_text(json.dumps(raw),encoding='utf-8')
        s2=Session('test',self.cat,Room('Minimalist'),self.tmp.name,seed_layout=copy.deepcopy(SEED))
        self.assertEqual(s2.room.style,'Shirogane')

    def test_render_native_mesh_sources_transforms_and_empty_house_all_styles(self):
        for style in STYLES:
            with self.subTest(style=style):
                s=self.session();s.apply([dict(op='interior',style=style)])
                lp=Path(self.tmp.name)/(style+'.json');s.write_layout(lp)
                m=run_pipeline(lp,Path(self.tmp.name)/('render-'+style),room_context=True,upper_context=True,size=(96,96),mirror_view=False,cameras=[dict(name='top',position=[0,0,50],target=[0,0,0],fov=40,cutaway=True)])
                objects={v['instance_id']:v for v in m['objects'].values()};p=s.room.profile
                self.assertEqual(Path(objects['up-floor']['source']),p.paths['upper']['floor'])
                self.assertEqual(Path(objects['floor']['source']),p.paths['ground']['floor'])
                for actor,label in [('Stairs','stair-up'),('Stairs2_9','stair-down'),('Railing','railing-upper')]:
                    self.assertEqual(objects[label]['decoded_actor_transform'],p.actors[actor])
                self.assertEqual(m['interior_profile']['style'],style);self.assertFalse(m['app_equivalence_verified'])
                self.assertTrue(Path(m['views'][0]['image']).is_file())

if __name__=='__main__':unittest.main()
