"""Native-layout scene assembly, bounded transform patches and multiview artifacts."""
from collections import Counter
from copy import deepcopy
from contextlib import closing
import hashlib
import json
import math
import re
from pathlib import Path
import time
import sqlite3
import numpy as np
from .assets import Assets, DecodedAssetCache
from ..config import source_path, catalog_path
from .native import ROOT
from .raster import render

from ..geometry_mesh import read_static_mesh_triangles
from ..housing import validate_layout_budget

from ..house_profiles import HOUSE_PROFILES,DEFAULT_CATALOG_CANDIDATES,room_keepouts,stair_actors,structure_record

# Process-local only: bounded and checked against source companions on every
# cross-view hit. Per-run identity/scope/transform validation still always runs.
_RESOURCE_CACHE=DecodedAssetCache()

DEFAULT_CAMERAS=[
 {'name':'entry','position':[0,7,1.65],'target':[0,-3,1.0],'fov':70},
 {'name':'overview','position':[16,17,16],'target':[0,-2,0],'fov':70,'cutaway':True},
 {'name':'west-zone','position':[-1.5,-1.3,1.65],'target':[-7,-4,1.0],'fov':75},
 {'name':'east-zone','position':[1.5,-1.3,1.65],'target':[7,-4,1.0],'fov':75},
]


def quaternion_matrix(q):
    if len(q)!=4 or not np.isfinite(q).all() or abs(sum(v*v for v in q)-1)>1e-5:raise ValueError('Expected finite normalized xyzw quaternion')
    x,y,z,w=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
        [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def apply_patch(layout,patch,source_hash,max_translation_m=2):
    if set(patch)!={'base_layout_sha256','changes'} or patch['base_layout_sha256']!=source_hash:raise ValueError('Patch must bind exact input layout hash')
    if not isinstance(patch['changes'],list) or not 1<=len(patch['changes'])<=10:raise ValueError('Patch must change1..10 instances')
    result=deepcopy(layout);seen=set();scale=result['interiorScale']
    for change in patch['changes']:
        if not set(change)<={'instance_id','delta_translation_m','yaw_delta_degrees'} or 'instance_id' not in change:raise ValueError('Only existing instance transform deltas can be patched')
        label=change['instance_id']
        if label in seen or not isinstance(label,str) or not label.startswith('furniture-'):raise ValueError('Duplicate/invalid instance ID')
        seen.add(label)
        try:index=int(label.removeprefix('furniture-'))-1
        except ValueError:raise ValueError('Invalid instance number')
        if label!=f'furniture-{index+1:04d}' or not 0<=index<len(result['interiorFurniture']):raise ValueError('Unknown instance')
        t=result['interiorFurniture'][index]['transform']
        delta=change.get('delta_translation_m',[0,0,0])
        if not isinstance(delta,list) or len(delta)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in delta) or math.sqrt(sum(v*v for v in delta))>max_translation_m:raise ValueError('Translation exceeds finite per-iteration guard')
        angle=change.get('yaw_delta_degrees',0)
        if isinstance(angle,bool) or not isinstance(angle,(int,float)) or not math.isfinite(angle) or abs(angle)>180:raise ValueError('Invalid yaw delta')
        t['location']=[old+d*scale for old,d in zip(t['location'],delta)]
        x,y,z,w=t['rotation'];s=math.sin(math.radians(angle)/2);c=math.cos(math.radians(angle)/2)
        t['rotation']=[c*x-s*y,c*y+s*x,c*z+s*w,c*w-s*z]
        quaternion_matrix(t['rotation'])
    validate_layout_budget(result)
    return result


SECTION_Z=3.0


def _hex2rgb(hx):
    return (int(hx[1:3], 16) / 255, int(hx[3:5], 16) / 255, int(hx[5:7], 16) / 255)


def _mesh_flat(mat, hex_fallback):
    """Colour to draw an untextured mesh with: the material's own flat colour if the decoder recorded one, else the
    item's measured/estimated colour from item_colors, else None (renderer falls back to neutral grey)."""
    if mat is not None and mat.get('texture') is not None: return None
    if mat is not None and mat.get('flat_color') is not None: return tuple(mat['flat_color'])
    return _hex2rgb(hex_fallback) if hex_fallback else None


def run_pipeline(layout_path,output_dir,*,basement_context=False,db_path=None,cameras=None,size=(960,640),patch=None,room_context=False,approximate_tint=False,rough_room_finish=False,three_view=False,mirror_view=True,dye_mode='default',display_gamma=0.7,view_names=None,lighting=None,upper_context=False,labels=False,debug_buffers=False,artifacts=False,image_prefix=None,overwrite=False,scope='interior'):
    """Render PNGs only by default. Metadata is returned; diagnostic JSONs are opt-in.

    layout_path may also be an in-memory layout dict. image_prefix namespaces files
    in a shared directory; overwrite is reserved for regenerating named cache images.
    """
    auto_overview=cameras is None;start=time.perf_counter();out=Path(output_dir)
    if image_prefix is not None and (not isinstance(image_prefix,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',image_prefix)):
        raise ValueError('image_prefix must contain only ASCII letters, numbers, underscores or hyphens')
    prefix=(image_prefix+'-') if image_prefix is not None else ''
    snapshot=out/(prefix+'layout.json');manifest_path=out/(prefix+'manifest.json');request_path=out/(prefix+'review-request.json')
    if isinstance(layout_path,dict):
        data=json.dumps(layout_path,ensure_ascii=False,sort_keys=True).encode('utf-8');layout=deepcopy(layout_path);layout_path=None
    else:
        layout_path=Path(layout_path)
        if artifacts and layout_path.resolve()==snapshot.resolve():raise ValueError('Output snapshot would overwrite input layout')
        data=layout_path.read_bytes();layout=json.loads(data)
    if artifacts and not overwrite and any(p.exists() for p in (snapshot,manifest_path,request_path)):
        raise ValueError('Diagnostic output already exists; choose a different image_prefix')
    source_hash=hashlib.sha256(data).hexdigest()
    if scope not in ('interior','exterior'):raise ValueError('scope must be interior or exterior')
    if scope=='exterior':
        if patch is not None or three_view or approximate_tint:raise ValueError('Exterior patches/three_view/legacy tint need an explicit policy; use native cameras and session edits')
        from .exterior import render_exterior
        return render_exterior(layout,out,data=data,input_path=layout_path,source_hash=source_hash,db_path=db_path,cameras=cameras,size=size,mirror_view=mirror_view,dye_mode=dye_mode,display_gamma=display_gamma,lighting=lighting,labels=labels,debug_buffers=debug_buffers,artifacts=artifacts,image_prefix=image_prefix,overwrite=overwrite,view_names=view_names)
    if patch is not None:layout=apply_patch(layout,patch,source_hash)
    budget=validate_layout_budget(layout);scale=layout['interiorScale']
    if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or scale<=0:raise ValueError('Invalid layout scale')
    house_size=layout.get('houseSize');profile=HOUSE_PROFILES.get(house_size)
    if profile is None:raise ValueError(f'No measured room profile for houseSize {house_size!r}')
    items=layout.get('interiorFurniture',[])
    if not items and not room_context:raise ValueError('Empty interior scene without room context')
    meshes=[];objects={};warnings=[]
    catalog=Path(db_path or catalog_path()).resolve()
    with closing(sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        ids=sorted({i['itemId'] for i in items})
        records=[json.loads(r[0]) for r in db.execute('SELECT evidence FROM asset_geometry WHERE item_id IN (%s)'%','.join('?'*len(ids)),ids)]
        for r in records:r['item_id']=int(r['item_id'])
        dyes={}
        if dye_mode=='default' and approximate_tint is False:
            import csv
            with open(source_path('stains_csv'),encoding='utf-8') as stain_file:
                stain={r['Name']:((int(r['Color'])>>16)&255,(int(r['Color'])>>8)&255,int(r['Color'])&255) for r in csv.DictReader(stain_file) if r['Color']!='0'}
            try:dyes={iid:stain[name] for iid,name in db.execute('SELECT item_id,dye_name FROM item_default_dye') if name in stain}
            except sqlite3.OperationalError:warnings.append('item_default_dye table missing: no default dyes applied (run scripts/fill_default_dye.py)')
        fallback={}
        try:
            for iid,hx in db.execute("SELECT item_id,c1_hex FROM item_colors WHERE c1_hex IS NOT NULL"): fallback[iid]=hx   # measured where available, estimated (est_from) for untextured meshes; never a neutral grey
        except sqlite3.OperationalError:pass
        assets=Assets(records,ROOT/'outputs/render-pipeline/cache',dyes=dyes,fallback_colours=fallback,mi_tint=(dye_mode=='mi'),resource_cache=_RESOURCE_CACHE)
        for index,item in enumerate(items,1):
            if item.get('attachments'):raise ValueError('Nonempty attachments require an explicit transform policy; not silently omitted')
            furniture=db.execute('SELECT id,name,scope FROM furniture WHERE id=?',(item['itemId'],)).fetchone()
            if not furniture or furniture['scope']!='interior' or furniture['name']!=item['name']:raise ValueError('Unmapped identity, conflicting name or non-interior item')
            _c=(item.get('properties') or {}).get('color');_rgb=tuple(int(_c[i:i+2],16) for i in (0,2,4)) if isinstance(_c,str) and len(_c)>=6 else None
            mesh=assets.load(item['itemId'],_rgb if dye_mode=='mi' else None);t=item['transform'];rotation=quaternion_matrix(t['rotation']);position=np.asarray(t['location'],float)/scale
            if position.shape!=(3,) or not np.isfinite(position).all():raise ValueError('Invalid location')
            if t.get('scale',[1,1,1])!=[1,1,1]:raise ValueError('Non-unit furnishing scale is unsupported by plugin export; not silently rendered differently')
            rotated=mesh['vertices']@rotation.T
            world=rotated+position
            object_id=index;label=f'furniture-{index:04d}'
            objects[str(object_id)]={'instance_id':label,'item_id':item['itemId'],'name':item['name'],'position_m':position.tolist(),'rotation':t['rotation']}
            for group in mesh['groups']:
                mat=mesh['materials'][group['material_index']] if group['material_index']>=0 else None
                a=group['first_triangle'];n=group['triangle_count']
                meshes.append({'id':object_id,'vertices':world,'triangles':mesh['triangles'][a:a+n],'uv':mesh['uv'],'material':mat,'role':'furniture','projection_vertices':rotated,'projection_offset':position[:2],**({'flat_color':_mesh_flat(mat, fallback.get(item['itemId']))} if _mesh_flat(mat, fallback.get(item['itemId'])) else {})})
    district=next((r['name'] for r in layout.get('interiorFixture',[]) if r['type']=='District'),None)
    if district: district=district.replace(' ','')   # app display names ('Dark Minimalist') -> compact geometry tokens
    from ..interiors import InteriorProfile, geometry as interior_geometry, transform_points, validate_style
    validate_style(district)
    interior=InteriorProfile(district) if house_size=='Medium' else None
    apt=None
    if house_size=='Apartment':
        from ..interiors import ApartmentProfile
        apt=ApartmentProfile(district)
    elif house_size=='Small':
        from ..interiors import SmallProfile
        apt=SmallProfile(district)
    elif interior is None and district!='Shirogane':raise ValueError('Non-Medium interior styles are not calibrated yet')
    def find(suffix):
        return structure_record(ROOT,suffix)
    floor_record=interior.record('floor') if interior else (interior_geometry(str(source_path('interiors')/'HouseAssets/InteriorStyles/Shirogane/Small/GroundFloor.uexp')) if house_size=='Small' else (find(profile['floor']) if 'floor' in profile else None))
    room_records=[('floor',floor_record)] if floor_record else []
    if room_context:
        for name in ('room-frame','ceiling','walls','pillars'):
            room_records.append((name,interior.record(name) if interior else (interior_geometry(str(apt.mesh(name))) if apt and name in ('room-frame','pillars') else find(profile[name]))))
        warnings.append('Enclosure meshes assume native-local identity plus level offset; not verified app actor placement.')
    if room_context and basement_context and house_size=='Small' and apt is not None:
        _sc=source_path('interiors')/'HouseAssets/InteriorStyles/SizeCommon/Small'
        _st=source_path('interiors')/'HouseAssets/InteriorStyles'/(district or 'Shirogane')/'Small'
        def _mesh(name):
            # district-provided walls render the SELECTED interior style; shared meshes are the neutral fallback
            for base in (_st,_sc):
                p=base/(name+'.uexp')
                if p.exists():
                    try:
                        rec=interior_geometry(str(p))
                        if rec: return rec
                    except Exception: pass
            return interior_geometry(str(_sc/(name+'.uexp')))
        for _n,_p in (('floor',_sc/'BasementFloor.uexp'),('room-frame',apt.mesh('bs-room-frame')),('ceiling',_sc/'BasementCeiling.uexp'),('pillars',apt.mesh('bs-pillars'))):
            room_records.append(('bs-'+_n,interior_geometry(str(_p))))
        for _n in ('BasementDistrictWall','BasementFloorWall'):
            rec=_mesh(_n)
            if rec: room_records.append(('bs-'+_n,rec))
        warnings.append('Basement context: Small basement meshes translated -7 m (stair actor z); walls use the selected district where available; not app-verified.')
    if room_context and upper_context and interior:
        for name in ('floor','room-frame','ceiling','walls','pillars'):
            room_records.append(('up-'+name,interior.record(name,'upper')))
        warnings.append('Upper context uses the selected style upper meshes translated +7m; enclosure placement is approximate.')
    if floor_record is None:
        warnings.append('Apartment floor footprint uses the measured SimpleFrame bounds')
    finish={};textures={}
    if rough_room_finish:
        from .house_materials import average_color,fixture_texture
        from . import native
        fx=layout.get('interiorFixture',[])
        floor_c,floor_p=average_color('Floor',fixtures=fx);wall_c,wall_p=average_color('Wall',fixtures=fx)
        finish={'floor':(floor_c,floor_p),'wall':(wall_c,wall_p)}
        try:
            textures={'floor':fixture_texture('Floor',fx),'walls':fixture_texture('Wall',fx)}
            if interior:
                try: textures['ceiling']=interior.ceiling_texture()
                except (ValueError,FileNotFoundError) as error: warnings.append(str(error)+'; no other style ceiling substituted')
            else:
                ceiling_path=source_path('houses')/'HouseAssets/InteriorStyles/Shirogane/Material/e1i0_i_com0000_0d_d.uasset'
                cimg,cmeta=native.decode_texture(ceiling_path);textures['ceiling']={'texture':np.asarray(cimg.convert('RGBA')),'provenance':{'texture':ceiling_path.name,'source_sha256':cmeta['source_sha256']}}
            if basement_context:
                for key,kind in (('bs_floor','Floor'),('bs_walls','Wall')):
                    try:textures[key]=fixture_texture(kind,fx,level='Basement')
                    except (ValueError,FileNotFoundError):textures[key]=textures['floor' if kind=='Floor' else 'walls']
                if 'ceiling' in textures: textures['bs_ceiling']=textures['ceiling']
            if upper_context:
                for key,kind in (('upper_floor','Floor'),('upper_walls','Wall')):
                    try:textures[key]=fixture_texture(kind,fx,level='Upper Floor')
                    except (ValueError,FileNotFoundError):textures[key]=textures['floor' if kind=='Floor' else 'walls']
                if 'ceiling' in textures: textures['upper_ceiling']=textures['ceiling']
            warnings.append('Room finish: floor/wall meshes use the chosen Ground Floor flooring/wallpaper albedo tiled by the native UVs; ceiling uses native MI_Ceiling; frame/pillars/stairs use their own native Base textures (no normal/specular/lighting, no tint). Wall/ceiling fixture-to-mesh mapping is inferred, not verified in the app.')
        except (ValueError,FileNotFoundError,KeyError,OSError) as error:
            textures={};warnings.append(f'Textures unavailable ({error}); room meshes fall back to flat average colours.')
    structure_assets=Assets([],ROOT/'outputs/render-pipeline/cache',resource_cache=_RESOURCE_CACHE)
    fixture_asset_loaders=[]
    def structure_parts(record,key,override=None):
        """Native sections/materials of a structure mesh (frame, pillars, stairs...); override replaces the placeholder material texture."""
        structure_assets.records[key]={**record,'item_id':key};mesh=structure_assets.load(key);out=[]
        for g in mesh['groups']:
            mat=mesh['materials'][g['material_index']] if g['material_index']>=0 else None
            if override is not None:mat={'texture':override['texture'],'tint':None}
            out.append((g,mat))
        return mesh,out
    next_render_id=len(items)+1
    def allocate_render_id():
        nonlocal next_render_id
        render_id=next_render_id;next_render_id+=1
        return render_id
    for label,record in room_records:
        i=allocate_render_id()
        is_up=label.startswith('up-');is_bs=label.startswith('bs-');base=label[3:] if (is_up or is_bs) else label
        role=('upper_floor' if base=='floor' else 'upper_enclosure') if is_up else ('floor' if base=='floor' else 'enclosure')
        tkey={'floor':'floor','walls':'walls','ceiling':'ceiling'}.get(base,'')
        override=textures.get(('upper_'+tkey) if is_up and tkey else (('bs_'+tkey) if is_bs and tkey else tkey))
        zoff=np.array([0,0,7.0]) if is_up else (np.array([0,0,-7.0]) if is_bs else np.zeros(3))
        if textures:
            mesh,parts=structure_parts(record,-i,override)
            for g,mat in parts:
                meshes.append({'id':i,'vertices':mesh['vertices']+zoff,'triangles':mesh['triangles'][g['first_triangle']:g['first_triangle']+g['triangle_count']],'uv':mesh['uv'],'material':mat,'role':role})
        else:
            vertices,triangles=read_static_mesh_triangles(record)
            meshes.append({'id':i,'vertices':np.asarray(vertices)+zoff,'triangles':np.asarray(triangles),'role':role,
                **({'flat_color':(finish['floor'] if base=='floor' else finish['wall'])[0]} if finish else {})})
        objects[str(i)]={'instance_id':label,'source':record['source'],'source_sha256':record['source_sha256'],'native_local_transform_assumed_identity':True,
                         **({'texture':override['provenance']} if override else {})}
    selected_door_drawn=False
    if room_context and house_size=='Small' and apt is not None:
        from ..interiors import SmallProfile
        assert isinstance(apt,SmallProfile)
        _ext={f['type']:f for f in layout.get('exteriorFixture',[])}
        for _kind,_cat,_places in (('Window','Window',apt.WINDOWS),('Door','MainDoor',(apt.DOOR,))):
            _f=_ext.get(_kind)
            if not _f:continue
            try:
                from ..geometry import read_static_mesh_bounds
                _folder=source_path('materials')/'HouseAssets'/_cat/''.join(_f['name'].replace('(','0x28').replace(')','0x29').split())
                _rec=read_static_mesh_bounds(_folder/(_folder.name+'.uexp'));_rec['item_id']=-88
                _as=Assets([_rec],ROOT/'outputs/render-pipeline/cache',resource_cache=_RESOURCE_CACHE);fixture_asset_loaders.append(_as);_m=_as.load(-88)
                for _x,_y,_z,_yaw in _places:
                    _wid=allocate_render_id()
                    _w=transform_points(_m['vertices'],dict(translation_m=[_x,_y,_z],yaw_degrees=_yaw,scale=[1,1,1]))
                    for g in _m['groups']:
                        mat=_m['materials'][g['material_index']] if g['material_index']>=0 else None
                        meshes.append({'id':_wid,'vertices':_w,'triangles':_m['triangles'][g['first_triangle']:g['first_triangle']+g['triangle_count']],'uv':_m['uv'],'material':mat,'role':'door' if _kind=='Door' else 'fixture',**({} if mat is not None and mat.get('texture') is not None else {'flat_color':[0.45,0.33,0.22]})})
                    objects[str(_wid)]={'instance_id':'native-'+_kind.lower(),'name':_f['name'],'position_m':[_x,_y,_z],'note':'native exterior fixture at the decoded umap transform'}
                    if _kind=='Door':
                        objects[str(_wid)].update(render_id=_wid,mesh_source=_rec['source'],app_verified=False,
                            world_bounds_m=[[round(float(_w[:,k].min()),3) for k in range(3)],[round(float(_w[:,k].max()),3) for k in range(3)]])
                        objects['main-door']=objects[str(_wid)]
                        selected_door_drawn=True
                        warnings.append(f"Main entrance door drawn from selected fixture {_f['name']}; placement follows Small profile, not app-verified")
            except Exception as error:warnings.append(f'Native {_kind} not drawn ({type(error).__name__}: {error})')
    if room_context and 'main-door' in profile and not selected_door_drawn:
        # Native main entrance door (user-reported gap: renderer drew an empty entry wall).
        # Mesh identity and world placement evidence live in HOUSE_PROFILES['main-door'];
        # placement follows the documented north-wall centre convention, never claimed app-verified.
        _door=profile['main-door']
        _dp=next((source_path(k)/'HouseAssets'/_door['mesh'] for k in ('materials','houses') if (source_path(k)/'HouseAssets'/_door['mesh']).is_file()),None)
        _drec=interior_geometry(str(_dp)) if _dp else None
        if _drec is None:
            warnings.append(f"Main entrance door mesh missing ({_door['mesh']}); entry wall stays empty")
        else:
            try:
                _key='main-door-'+_door['mesh'];structure_assets.records[_key]={**_drec,'item_id':_key}
                _dmesh=structure_assets.load(_key)
                _a=math.radians(_door.get('yaw_degrees',0));_c,_s=math.cos(_a),math.sin(_a)
                _dv=_dmesh['vertices'].copy();_dv[:,:2]=_dv[:,:2]@[[ _c,-_s],[ _s, _c]]
                _dv+=np.asarray(_door['translation_m'],float)
                if not np.isfinite(_dv).all():raise ValueError('non-finite door vertices')
                _did=allocate_render_id()
                for _g in _dmesh['groups']:
                    _mat=_dmesh['materials'][_g['material_index']] if _g['material_index']>=0 else None
                    meshes.append({'id':_did,'vertices':_dv,'triangles':_dmesh['triangles'][_g['first_triangle']:_g['first_triangle']+_g['triangle_count']],'uv':_dmesh['uv'],'material':_mat,'role':'door',  # 'door' (not 'enclosure'): cutaway plan views must still show the entrance
                                   **({} if _mat is not None and _mat.get('texture') is not None else {'flat_color':[0.35,0.22,0.12]})})
                objects[str(_did)]=objects['main-door']={'instance_id':'main-door','render_id':_did,'source':_drec['source'],'source_sha256':_drec['source_sha256'],'mesh_source':_drec['source'],
                    'world_bounds_m':[[round(float(_dv[:,k].min()),3) for k in range(3)],[round(float(_dv[:,k].max()),3) for k in range(3)]],
                    'placement_evidence':_door['evidence'],'app_verified':False}
                warnings.append(f"Main entrance door drawn from native mesh {Path(_drec['source']).name}; placement is a documented north-wall centre convention, not decoded from actor properties and not app-verified ({_door['evidence']})")
            except Exception as _e:
                warnings.append(f'Main entrance door not drawn ({type(_e).__name__}: {_e})')
    if room_context and basement_context and house_size=='Small' and apt is not None:
        try:
            # Plan cutaways remove the walls, so floor this style walls off (Mist: stair underside + under the ground landing) would read as usable.
            # Mark it with a dark flat overlay drawn only in cutaway views (role 'void'); the region is the style's own basement outline.
            from shapely.geometry import box as _box
            from shapely.ops import triangulate as _tri
            _void = _box(-6.0, -6.0, 10.0, 14.0).difference(apt.polygon('basement').buffer(0.01))
            _parts = [g for g in getattr(_void, 'geoms', [_void]) if g.area > 0.5]
            if _parts:
                _vid = allocate_render_id(); _vs = []; _ts = []
                for _g in _parts:
                    for _t in _tri(_g):
                        if not _g.buffer(1e-6).contains(_t.representative_point()): continue
                        _c = list(_t.exterior.coords)[:3]; _ts.append([len(_vs), len(_vs) + 1, len(_vs) + 2]); _vs += [[x, y, -6.97] for x, y in _c]
                if _ts:
                    meshes.append({'id': _vid, 'vertices': np.asarray(_vs, float), 'triangles': np.asarray(_ts), 'uv': None, 'material': None, 'role': 'void', 'flat_color': [0.06, 0.05, 0.05]})
                    objects[str(_vid)] = {'instance_id': 'basement-walled-off', 'area_m2': round(sum(g.area for g in _parts), 2), 'style': apt.style,
                                          'note': 'floor outside the style basement outline (sliced native walls); drawn dark in cutaway plans only'}
        except Exception as _e:
            warnings.append(f'Basement walled-off overlay not drawn ({type(_e).__name__}: {_e})')
    if room_context and floor_record is None and 'footprint' in profile:
        # Apartment has no floor mesh: synthesize the footprint rectangle (UV 0.175/m, the scale measured on the Medium floor) with the chosen flooring albedo.
        _rec=find(profile['footprint']);(x0,y0,_),(x1,y1,_)=_rec['local_min_m'],_rec['local_max_m']
        _v=np.array([[x0,y0,0],[x1,y0,0],[x1,y1,0],[x0,y1,0]],float);_uv=_v[:,:2]*0.175;_fid=allocate_render_id()
        _tex=textures.get('floor');_mat={'texture':_tex['texture'],'tint':None} if _tex else None
        meshes.append({'id':_fid,'vertices':_v,'triangles':np.array([[0,1,2],[0,2,3]]),'uv':_uv,'material':_mat,'role':'floor',**({} if _mat else {'flat_color':finish['floor'][0] if finish else [0.4,0.35,0.3]})})
        objects[str(_fid)]={'instance_id':'floor-synthetic','source':_rec['source'],'note':'synthetic Apartment floor from the SimpleFrame footprint'}
    stairs=(interior.actors if interior else getattr(apt,'actors',{})) if room_context else {}
    if stairs:
        for k,(sname,a) in enumerate(sorted(stairs.items())):
            stair_id=allocate_render_id()
            srec=interior_geometry(a['mesh'])
            mesh,parts=structure_parts(srec,-(1000+k))
            world=transform_points(mesh['vertices'],a)
            for g,mat in parts:
                meshes.append({'id':stair_id,'vertices':world,'triangles':mesh['triangles'][g['first_triangle']:g['first_triangle']+g['triangle_count']],'uv':mesh['uv'],'material':mat,'role':'enclosure' if 'Ceiling' in sname else 'stair',   # stairwell ceiling is part of the shell: cutaway plan views must remove it
                               **({} if mat is not None and mat.get('texture') is not None else {'flat_color':[0.59,0.46,0.35]})})
            label={'Stairs':'stair-up','Stairs2_9':'stair-down','Railing':'railing-upper','Railing2_2':'railing-ground'}.get(sname,sname.lower())
            objects[str(stair_id)]={'instance_id':label,'source_actor':sname,'decoded_actor_transform':a,'mesh':srec['source'],'mesh_sha256':srec['source_sha256'],'material_slots_textured':sum(1 for _,m in parts if m and m.get('texture') is not None),'material_slots':len(parts)}
        warnings.append('Stairs/railings use shared native component defaults or named style overrides, including full negative scale; no screenshot overrides. App navigation not verified.')
    # ---- ceiling light fixture mesh (hangs from the ceiling at the room centre: position inferred, not verified in the app) + lighting model
    fx_light=next((f for f in layout.get('interiorFixture',[]) if f.get('type')=='Light' and f.get('level')=='Ground Floor'),None)
    light_sources=[]
    for _lvl,_cz in (('Ground Floor',6.5),('Upper Floor',13.5),('Basement',-0.55)):
        if _lvl=='Upper Floor' and not upper_context:continue
        if _lvl=='Basement' and not basement_context:continue
        _fx=next((f for f in layout.get('interiorFixture',[]) if f.get('type')=='Light' and f.get('level')==_lvl),None)
        if room_context and _fx is not None:
            try:
                from ..geometry import read_static_mesh_bounds
                folder=source_path('materials')/'HouseAssets/CeilingLight'/''.join(_fx['name'].split())
                lrec=read_static_mesh_bounds(folder/(folder.name+'.uexp'));lrec['item_id']=-77
                lassets=Assets([lrec],ROOT/'outputs/render-pipeline/cache',resource_cache=_RESOURCE_CACHE);fixture_asset_loaders.append(lassets);lmesh=lassets.load(-77);lid=allocate_render_id()
                lv=lmesh['vertices']+np.array([0.0,0.0,_cz])
                for g in lmesh['groups']:
                    mat=lmesh['materials'][g['material_index']] if g['material_index']>=0 else None
                    meshes.append({'id':lid,'vertices':lv,'triangles':lmesh['triangles'][g['first_triangle']:g['first_triangle']+g['triangle_count']],'uv':lmesh['uv'],'material':mat,'role':'fixture','emissive':(0.5,0.4,0.25) if lighting else (0,0,0),**({} if mat is not None and mat.get('texture') is not None else {'flat_color':[0.8,0.7,0.5]})})
                objects[str(lid)]={'instance_id':'ceiling-light-'+_lvl.split()[0].lower(),'name':_fx['name'],'item_id':_fx.get('itemId'),'position_note':f'hangs from ceiling z={_cz} at (0,0); position inferred'}
                light_sources.append(_cz)
            except Exception as error:warnings.append(f'Ceiling light mesh ({_lvl}) not drawn ({type(error).__name__}: {error})')
    lighting_cfg=None
    if lighting:
        MOODS={'day':dict(lo=(.45,.44,.42),hi=(.75,.78,.85),exposure=1.3,scale=.5),'dusk':dict(lo=(.10,.09,.10),hi=(.22,.22,.28),exposure=1.25,scale=1.0),'night':dict(lo=(.04,.04,.07),hi=(.08,.09,.15),exposure=1.4,scale=1.2)}
        mood=MOODS['dusk' if lighting in (True,'warm') else lighting] if isinstance(lighting,(str,bool)) else lighting
        EMIT=re.compile(r'lamp|lantern|chandelier|candle|brazier|fire|torch|sconce|pendant|hearth|stove|bonfire|flame|illuminat|glow|lighting|neon|\blight\b',re.I)
        boxes={}
        for m in meshes:
            if m['role']=='furniture' and EMIT.search(objects[str(m['id'])]['name']):
                v=np.asarray(m['vertices']);b=boxes.setdefault(m['id'],[v.min(0),v.max(0)]);b[0]=np.minimum(b[0],v.min(0));b[1]=np.maximum(b[1],v.max(0))
        lights=[];emit={}
        for oid,(lo,hi) in boxes.items():
            nm=objects[str(oid)]['name'].lower();c=(lo+hi)/2;pos=[float(c[0]),float(c[1]),float(lo[2]+.7*(hi[2]-lo[2]))]
            if re.search(r'fire|brazier|hearth|bonfire|stove|flame',nm):col,inten,rad=(1.0,.55,.25),2.2,1.9
            elif re.search(r'chandelier|pendant',nm):col,inten,rad=(1.0,.82,.55),2.2,3.2
            elif 'candle' in nm:col,inten,rad=(1.0,.7,.4),.7,1.0
            elif 'wall' in nm or 'sconce' in nm:col,inten,rad=(1.0,.75,.45),1.4,1.7
            else:col,inten,rad=(1.0,.78,.5),1.3,1.5
            lights.append({'pos':pos,'color':list(col),'intensity':inten*mood['scale'],'radius':rad});emit[oid]=tuple(.8*x for x in col)
        for m in meshes:
            if m['id'] in emit:m['emissive']=emit[m['id']]
        for _cz in light_sources:lights.append({'pos':[0.0,0.0,_cz-1.2],'color':[1.0,.85,.6],'intensity':1.5*mood['scale'],'radius':4.5})
        lights.sort(key=lambda l:-l['intensity']*l['radius']);lighting_cfg={'ambient_lo':list(mood['lo']),'ambient_hi':list(mood['hi']),'exposure':mood['exposure'],'lights':lights[:64]}
        warnings.append(f'Lighting: {len(lights)} point lights (lamps/lanterns/fires from furniture names + ceiling fixture), hemisphere ambient, wrap diffuse, NO shadows, no specular/normal maps, no GI, not the game shader. Approximate mood only.')
    # Exact triangle projection membership, not furniture AABB corners; this is not navigation.
    from shapely.geometry import box
    from shapely.affinity import translate
    from .projection import projected_footprint
    from shapely.ops import unary_union
    if floor_record is not None:
        fv,ft=read_static_mesh_triangles(floor_record)
        floor=projected_footprint(fv,ft).buffer(.002)
    else:
        fp=find(profile['footprint']);floor=box(fp['local_min_m'][0],fp['local_min_m'][1],fp['local_max_m'][0],fp['local_max_m'][1]).buffer(.002)
    outside=set();corridor=set();height_errors=set();stair_hit=set()
    from shapely.ops import unary_union as _union
    _keeps=interior.stair_footprints('ground') if interior else room_keepouts(ROOT,house_size,'ground');stair_keep=_union(_keeps) if _keeps else None
    for m in meshes:
        if m['role']!='furniture':continue
        is_upper=np.asarray(m['vertices'])[:,2].min()>=6.4
        if np.asarray(m['vertices'])[:,2].min()<=-3:continue   # basement furniture: checked by the MCP, not here
        floor_check=interior.polygon('upper') if is_upper and interior else floor
        if is_upper and not interior:continue
        # Footprint is the union of actual nondegenerate projected triangles, including concavities.
        local_projection=projected_footprint(m['projection_vertices'],m['triangles'])
        if not local_projection.is_empty:
            silhouette=translate(local_projection,*m['projection_offset'])
            if silhouette.difference(floor_check).area>.001:outside.add(objects[str(m['id'])]['instance_id'])
            if not is_upper and stair_keep is not None and silhouette.intersection(stair_keep).area>.05:stair_hit.add(objects[str(m['id'])]['instance_id'])
            _mrr=list(silhouette.minimum_rotated_rectangle.exterior.coords);_depth=min(math.dist(_mrr[0],_mrr[1]),math.dist(_mrr[1],_mrr[2]))
            thin_on_wall=silhouette.distance(floor.boundary)<.05 and _depth<.4
            if not is_upper and profile.get('corridor') and not thin_on_wall and silhouette.intersection(box(*profile['corridor'])).area>.01:corridor.add(objects[str(m['id'])]['instance_id'])
        level_z=7.0 if is_upper else 0.0
        if m['vertices'][:,2].min()<level_z-.05 or m['vertices'][:,2].max()>level_z+6.52:height_errors.add(objects[str(m['id'])]['instance_id'])
    if patch is not None and (corridor or height_errors or stair_hit):raise ValueError('Patch violates reserved design corridor or measured floor/height guard')
    if stair_hit:warnings.append('Geometry intersects the stair keepout (stair hull + 1 m approach): '+','.join(sorted(stair_hit)))
    if corridor:warnings.append('Geometry intersects reserved design central corridor: '+','.join(sorted(corridor)))
    if height_errors:warnings.append('Geometry crosses measured floor/height guard: '+','.join(sorted(height_errors)))
    if outside:
        if patch is not None:raise ValueError('Patched geometry leaves measured floor projection: '+','.join(sorted(outside)))
        warnings.append('Objects partly outside measured floor projection: '+','.join(sorted(outside)))
    encoding='utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8'
    snapshot_data=(json.dumps(layout,ensure_ascii=False,indent=2)+'\n').encode(encoding)
    views=[]
    if three_view:
        lo=np.asarray(floor.bounds[:2]);hi=np.asarray(floor.bounds[2:]);c=(lo+hi)/2;half=float(max(hi[0]-lo[0],hi[1]-lo[1]))/2*1.08+.5;d=max(80.,half*6)
        fov=math.degrees(2*math.atan(half/d));zc=3.25
        cameras=[{'name':'top','position':[c[0],c[1],d],'target':[c[0],c[1],0],'fov':fov,'cutaway':True},
                 {'name':'front','position':[c[0],c[1]+d,zc],'target':[c[0],c[1],zc],'fov':fov,'cutaway':True},
                 {'name':'side','position':[c[0]+d,c[1],zc],'target':[c[0],c[1],zc],'fov':fov,'cutaway':True}]
        warnings.append('three-view: distant narrow-FOV perspective (~orthographic, not exact); enclosure hidden; world axes uncalibrated vs app')
    elif cameras is None and house_size!='Medium':
        # DEFAULT_CAMERAS were placed for the Medium footprint only; frame other sizes from the measured floor bounds.
        lo=np.asarray(floor.bounds[:2]);hi=np.asarray(floor.bounds[2:]);c=(lo+hi)/2;w,dp=hi-lo;r=max(w,dp)
        cameras=[{'name':'overview','position':[c[0]+.9*r,c[1]+.9*r,.9*r],'target':[c[0],c[1],0],'fov':70,'cutaway':True},
                 {'name':'entry','position':[c[0],hi[1]+.5,1.65],'target':[c[0],c[1],1.0],'fov':80},
                 {'name':'west','position':[c[0]+.1*w,c[1],1.65],'target':[lo[0],c[1]-.2*dp,1.0],'fov':80},
                 {'name':'east','position':[c[0]-.1*w,c[1],1.65],'target':[hi[0],c[1]-.2*dp,1.0],'fov':80}]
        warnings.append(f'{house_size}: cameras auto-framed from measured floor bounds, not the Medium design cameras')
    else:cameras=DEFAULT_CAMERAS if cameras is None else cameras
    # Cutaway views are sectioned: stairs (up to 8.5 m tall) would hide most of the room, so parts above SECTION_Z are not drawn there.
    if view_names:cameras=[c for c in cameras if c.get('name') in view_names]   # render only the views asked for (every view costs minutes on a full room)
    cameras=[{**c,'cut_stairs_z':SECTION_Z} if c.get('cutaway') and 'cut_stairs_z' not in c else c for c in cameras]
    if auto_overview and not three_view and any(c.get('name')=='overview' for c in cameras):
        # pick the corner view (elevated, looking at the floor centre) that shows the most furniture pixels; scores come from small test renders
        import tempfile
        lo=np.asarray(floor.bounds[:2]);hi=np.asarray(floor.bounds[2:]);cc=(lo+hi)/2;rr=float(max(hi[0]-lo[0],hi[1]-lo[1]))
        cands=[]
        for nm,(sx,sy) in {'NE':(1,1),'NW':(-1,1),'SE':(1,-1),'SW':(-1,-1)}.items():
            cands.append({'name':'overview','position':[float(cc[0]+sx*.85*rr),float(cc[1]+sy*.75*rr),float(.8*rr)],'target':[float(cc[0]),float(cc[1]),0.0],'fov':62,'cutaway':True,'cut_stairs_z':SECTION_Z})
        furn={m['id'] for m in meshes if m['role']=='furniture'};best=None;trial=[]
        with tempfile.TemporaryDirectory() as tmpd:
            for k,cam in enumerate(cands):
                v=render(meshes,cam,Path(tmpd)/f'c{k}.png',size=(240,160));vis=v.get('visible_object_pixels',{});fp=sum(n for i,n in vis.items() if int(i) in furn);trial.append((fp,['NE','NW','SE','SW'][k]))
                if best is None or fp>best[0]:best=(fp,cam)
        cameras=[best[1] if c.get('name')=='overview' else c for c in cameras]
        warnings.append('overview camera auto-picked from 4 corners by visible furniture pixels (%s); stairs sectioned above %.1f m in cutaway views'%(', '.join(f'{n}:{p}' for p,n in trial),SECTION_Z))
    if not isinstance(cameras,list) or not 1<=len(cameras)<=8:raise ValueError('Need1..8 bounded cameras')
    if dye_mode=='default' and not approximate_tint:warnings.append('Colours: Base x the furniture default dye (ItemData Dye -> Stain.csv colour) on dyeable slots only, masked by Base alpha; display curve gamma %s fitted to app screenshot samples (approximate, no lighting model).'%display_gamma)
    if mirror_view:
        cameras=[{**c,'mirror_x':True} for c in cameras]
        warnings.append('Views are horizontally mirrored (view-only, per user observation that app left/right is opposite); layout and world coordinates are unchanged. Pass mirror_view=False / --no-mirror for the raw projection.')
    if lighting_cfg:cameras=[{**c,'lighting':lighting_cfg} for c in cameras]
    image_stem=image_prefix if image_prefix is not None else 'view'
    image_paths=[out/f'{image_stem}-{i+1:02d}.png' for i in range(len(cameras))]
    if not overwrite:
        for path in image_paths:
            targets=[path.with_name(path.stem+'-labeled.png') if labels else path]
            if debug_buffers:targets.extend((path.with_name(path.stem+'-ids.png'),path.with_name(path.stem+'-depth.npy')))
            if any(p.exists() for p in targets):raise ValueError('Render image already exists; choose a different image_prefix')
    out.mkdir(parents=True,exist_ok=True)
    if artifacts:snapshot.write_bytes(snapshot_data)
    for i,camera in enumerate(cameras):
        view=render(meshes,camera,image_paths[i],size=size,approximate_tint=approximate_tint,display_gamma=1.0 if lighting_cfg else display_gamma,labels=labels,debug_buffers=debug_buffers);views.append(view)
    textured=sum(x['textured_slots'] for x in assets.coverage);slots=sum(x['material_slots'] for x in assets.coverage)
    native_material_diagnostics:dict[str,object]={
        'scope':'native decode only; decoded entries, not placement counts or a full-library scan; room texture overrides are not effective-material coverage',
        'room_material_mode':'texture-overrides' if textures else 'geometry-only',
    }
    for category,rows in (('furniture',assets.coverage),('structure',structure_assets.coverage),
                          ('fixtures',[row for loader in fixture_asset_loaders for row in loader.coverage])):
        material_count=sum(row['material_slots'] for row in rows)
        textured_count=sum(row['textured_slots'] for row in rows)
        native_material_diagnostics[category]={'decoded_entries':len(rows),'material_slots':material_count,
            'textured_slots':textured_count,'untextured_slots':material_count-textured_count,'coverage':rows}
    manifest={'input_layout':str(layout_path.resolve()) if layout_path else None,'input_layout_sha256':source_hash,'rendered_layout':str(snapshot.resolve()) if artifacts else None,
        'rendered_layout_sha256':hashlib.sha256(snapshot_data).hexdigest(),'patch':patch,'budget':budget,'views':views,'objects':objects,
        'geometry_assets':len(assets.coverage),'material_slots':slots,'textured_slots':textured,'untextured_slots':slots-textured,
        'asset_coverage':assets.coverage,'native_material_diagnostics':native_material_diagnostics,'warnings':warnings,'mirror_view':mirror_view,'dye_mode':dye_mode if not approximate_tint else 'mi-tint','display_gamma':display_gamma,'outside_floor_projection':sorted(outside),'stair_keepout_hits':sorted(stair_hit),'elapsed_seconds':time.perf_counter()-start,
        'interior_profile':interior.summary() if interior else None,
        'room_context':room_context,'fixture_selections':layout.get('interiorFixture',[]),'fixture_materials_applied':bool(finish),'rough_room_finish':{k:v[1] for k,v in finish.items()},
        'app_equivalence_verified':False,'physical_lighting_verified':False,'parent_material_graphs_reconstructed':False,
        'approximate_tint_enabled':approximate_tint,'normal_specular_emission_applied':False,'walkability_verified':False,'model_calls':0}
    if not artifacts:return manifest
    manifest['artifacts']={'layout':str(snapshot.resolve()),'manifest':str(manifest_path.resolve()),'review_request':str(request_path.resolve())}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    request={'task':'Review these native-mesh preview cameras and propose a bounded per-instance transform patch. Do not infer true materials or lighting from unsupported/grey slots. Preserve intended overlaps; keep used floor access, source scope and budgets. No new objects or layout-wide rewrite.',
        'layout_sha256':manifest['rendered_layout_sha256'],'views':[v['image'] for v in views],'objects':objects,'warnings':warnings,
        'patch_schema':{'base_layout_sha256':manifest['rendered_layout_sha256'],'changes':[{'instance_id':'furniture-0001','delta_translation_m':[0,0,0],'yaw_delta_degrees':0}]},
        'limits':{'max_changed_instances':10,'max_translation_m':2,'max_abs_yaw_delta_degrees':180},
        'limitations':['App coordinates/camera orientation not calibrated','Room actors not calibrated','Lighting is approximate','No geometric navigation proof']}
    request_path.write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest
