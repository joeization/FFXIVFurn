"""Validated LOD sections, material-slot mapping and provenance-keyed optional textures."""
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from . import native
from ..config import load_sources, source_path
from ..geometry_mesh import read_static_mesh_triangles
from .resources import DecodedAssetCache, dependency_snapshot


def mesh_materials(path):
    table=native.tables.map_tables(path);imports={r['index']:r for r in table['imports']}
    export=next(r for r in table['exports'] if r['class'].endswith('.StaticMesh'))
    reader=native.Reader(path.with_suffix('.uexp').read_bytes()[export['serial_offset_in_uexp']:],native.names(path))
    fields,zero=reader.header()
    if not fields or fields[0]!=2 or 2 in zero:raise ValueError('Missing first StaticMaterials property')
    count=reader.read('<i')
    if not 1<=count<=64:raise ValueError('Invalid StaticMaterials count')
    result=[]
    for i in range(count):
        fields,zero=reader.header()
        if set(fields)-{0,1,2,3} or 0 not in fields or 0 in zero:raise ValueError('Unsupported StaticMaterial struct')
        ref=reader.read('<i');material=imports.get(ref)
        if not material or material['class'] not in ('Material','MaterialInstanceConstant'):raise ValueError('Bad material reference')
        for field in (1,2):
            if field in fields and field not in zero:reader.fname()
        if 3 in fields and 3 not in zero:
            uvfields,uvzero=reader.header()
            if set(uvfields)-set(range(6)):raise ValueError('Unknown UV density fields')
            for field in uvfields:
                if field not in uvzero:reader.read('<B' if field<2 else '<f')
        result.append(material)
    return result


def sections(record,triangles,material_count):
    data=Path(record['source']).read_bytes();hits=[]
    for count in range(1,65):
        start=record['vertex_buffer_offset']-14-40*count
        if start<4 or struct.unpack_from('<I',data,start-4)[0]!=count:continue
        cursor=0;output=[]
        for i in range(count):
            mat,first,num,lo,hi,*flags=struct.unpack_from('<10i',data,start+40*i)
            if first!=cursor*3 or num<=0 or cursor+num>len(triangles) or not 0<=mat<material_count or any(f not in (0,1) for f in flags):break
            indices=np.asarray(triangles[cursor:cursor+num]).ravel()
            if int(indices.min())!=lo or int(indices.max())!=hi:break
            output.append({'material_index':mat,'first_triangle':cursor,'triangle_count':num});cursor+=num
        else:
            if cursor==len(triangles):hits.append(output)
    if len(hits)!=1:raise ValueError('No unique cross-validated section layout')
    return hits[0]


def uvs(record):
    data=Path(record['source']).read_bytes();count=record['vertex_count'];end=record['vertex_buffer_offset']+16+count*12
    channels,n,full,high,tan_size,tan_count=struct.unpack_from('<6I',data,end+2);offset=end+26+tan_size*tan_count
    size,total=struct.unpack_from('<2I',data,offset)
    if size!=(8 if full else 4) or total<count*channels or n!=count:raise ValueError('UV count mismatch')
    uv=np.frombuffer(data,dtype='<f4' if full else '<f2',count=count*channels*2,offset=offset+8).reshape(count,channels,2)[:,0].astype(float)
    if not np.isfinite(uv).all():raise ValueError('Nonfinite UV')
    return uv


ROOT_DIR=Path(__file__).resolve().parents[2]
EXTRA_CONTENT_ROOTS=[source_path(k) for k in ('interiors','houses','materials')]+[Path(p) for p in load_sources()['furniture_roots']]


def find_asset(content,package,dependencies=None):
    """Resolve /Game/... against the mesh's own Content root first, then the other extracted roots."""
    rel=package.split('.')[0].removeprefix('/Game/')
    for root in [content,*EXTRA_CONTENT_ROOTS]:
        path=(root/rel).with_suffix('.uasset')
        if dependencies is not None:
            dependencies.update(path.with_suffix(s) for s in ('.uasset','.uexp','.ubulk'))
        if path.exists():return path
    return (content/rel).with_suffix('.uasset')


def _lin(v): return np.where(v <= .04045, v / 12.92, ((v + .055) / 1.055) ** 2.4)
def _srgb(v): return np.where(v <= .0031308, v * 12.92, 1.055 * np.maximum(v, 0) ** (1 / 2.4) - .055)


def apply_default_dye(rgba, dye_rgb):
    """Bake an item's default dye (sRGB 0..255) into a dyeable slot's Base: rgb = base * lerp(1, dye, mask), mask = Base alpha
    (white = dyeable body, black = trim that keeps its own colour; verified on the Scholasticate Bookshelf atlas). Multiplication in linear light."""
    a = rgba[..., 3:4].astype(float) / 255; base = _lin(rgba[..., :3].astype(float) / 255); dye = _lin(np.asarray(dye_rgb, float) / 255)
    out = _srgb(base * (1 - a + a * dye)); res = rgba.copy(); res[..., :3] = np.clip(out * 255 + .5, 0, 255).astype(np.uint8)
    res[..., 3] = 255
    return res


def door_hinge_sockets(path):
    """Decode the native static-mesh DoorHinge transforms; never guess a leaf pivot.

    The inspected UE5.3 socket schema is FName, FVector3d (cm), FRotator3d
    (pitch/yaw/roll), followed by the zero object-guid marker. Unknown layouts
    fail explicitly rather than attaching a door at an invented origin.
    """
    path=Path(path).with_suffix('.uasset')
    table=native.tables.map_tables(path);data=path.with_suffix('.uexp').read_bytes()
    sockets=[]
    for export in table['exports']:
        if not export['class'].endswith('.StaticMeshSocket'):continue
        start=export['serial_offset_in_uexp'];end=start+export['serial_size']
        r=native.Reader(data[start:end],native.names(path))
        fields,zero=r.header()
        if fields!=[0,1,2] or zero:raise ValueError('Unsupported native door socket schema')
        name=r.fname();location=np.asarray(r.read('<3d'),float)/100
        pitch,yaw,roll=r.read('<3d')
        if r.data[r.pos:]!=b'\0'*4 or not np.isfinite([*location,pitch,yaw,roll]).all():
            raise ValueError('Invalid native door socket payload')
        if not name.startswith('DoorHinge'):continue
        if abs(pitch)>1e-8 or abs(roll)>1e-8:raise ValueError('Non-yaw native door hinge is not supported')
        if any(s['socket']==name for s in sockets):raise ValueError('Duplicate native door hinge')
        sockets.append(dict(socket=name,translation_m=location.tolist(),yaw_degrees=float(yaw)))
    return sockets


class Assets:
    def __init__(self,records,cache_dir,dyes=None,fallback_colours=None,mi_tint=False,resource_cache=None):
        self.mi_tint=mi_tint   # use each material instance's own Tint/FixedTint (the item's real default look) instead of the DB default dye
        self.dyes=dyes or {};self.fallback_colours=fallback_colours or {}   # item_id -> '#rrggbb' measured (or honestly estimated, est_from) colour for meshes whose material carries no texture
        self.records={r['item_id']:r for r in records};self.cache=Path(cache_dir);self.cache.mkdir(parents=True,exist_ok=True)
        self.loaded={};self.coverage=[];self.resource_cache=resource_cache;self.dependencies={}
    def load(self,item_id,color=None):
        """color = (r,g,b) 0..255 housing-dye override for dyeable (Tint) slots; FixedTint slots never change."""
        key=item_id if color is None else (item_id,tuple(color))
        if key in self.loaded:return self.loaded[key]
        if item_id not in self.records:raise ValueError(f'No measured geometry for Item ID {item_id}; not replaced with a box')
        record=self.records[item_id];path=Path(record['source'])
        resource_key=(json.dumps(record,sort_keys=True),key,self.mi_tint,tuple(self.dyes.get(item_id,())),self.fallback_colours.get(item_id),str(self.cache.absolute()))
        if self.resource_cache is not None:
            cached=self.resource_cache.get(resource_key)
            if cached is not None:
                result,coverage,deps=cached;self.loaded[key]=result;self.coverage.append(coverage);self.dependencies.update(deps);return result
        dependencies={path.with_suffix(s) for s in ('.uasset','.uexp','.ubulk')}
        vertices,triangles=read_static_mesh_triangles(record)
        uv=uvs(record);notes=[]
        try:materials=mesh_materials(path.with_suffix('.uasset'));groups=sections(record,triangles,len(materials))
        except (ValueError,KeyError,struct.error,IndexError) as error:
            notes.append(str(error));materials=[];groups=[{'material_index':-1,'first_triangle':0,'triangle_count':len(triangles)}]
        decoded=[]
        for material in materials:
            entry={'native_reference':material['resolved'],'texture':None,'warning':None,'tint':None}
            try:
                package=material['resolved'].split('.')[0]
                _master=package.rsplit('/',1)[-1]
                if package.startswith('/Game/Materials/') and _master in ('M_MasterGlass','M_Rain'):
                    # Slot bound straight to a translucent master (not extracted, no parameters): draw as a pale see-through pane.
                    # M_Rain streams (rain windows, waterfall curtains) are clearly visible in game; 0.12 made them vanish.
                    entry.update(glass=True,glass_alpha=0.22 if _master=='M_MasterGlass' else 0.3,
                                 flat_color=(0.80,0.88,0.92) if _master=='M_MasterGlass' else (0.72,0.86,0.95),parent=material['resolved'],
                                 warning=f'{_master}: translucent approximation (no refraction/reflection)')
                    decoded.append(entry);continue
                if not package.startswith('/Game/Materials/') and _master.startswith('M_') and 'Water' in _master:
                    # Item-local standalone water material (e.g. Waterfall Partition M_BrightWater): no MI parameters to decode.
                    # Approximate as glowing translucent water instead of the opaque brown item-colour fallback.
                    entry.update(glass=True,glass_alpha=0.5,flat_color=(0.45,0.78,0.92),emissive=(0.25,0.55,0.7),parent=material['resolved'],
                                 warning=f'{_master}: standalone water material approximated as translucent glowing water')
                    decoded.append(entry);continue
                # Package paths, not file stems with FName numeric suffixes, identify the actual asset.
                content=next(p for p in path.parents if p.name=='Content')
                mp=find_asset(content,package,dependencies)
                guessed=None
                try:mi=native.material_instance(mp)
                except (ValueError,KeyError,struct.error,IndexError) as mi_error:
                    # Unsupported MI property layout: if the MI imports exactly one albedo (_d) texture, use it as Base instead of a flat colour.
                    imps=native.tables.map_tables(mp)['imports']
                    ds=sorted({x['resolved'] for x in imps if x['class']=='Texture2D' and x['resolved'].split('.')[-1].endswith('_d')})
                    if len(ds)!=1:raise
                    par=next((x['resolved'] for x in imps if x['class']=='Material'),None)
                    mi={'parent':par,'parameters':{'Base':{'kind':'texture','value':ds[0]}},'source_sha256':hashlib.sha256(mp.with_suffix('.uexp').read_bytes()).hexdigest()}
                    guessed=f'MI layout unsupported ({mi_error}); base guessed from its only _d texture import'
                base=mi['parameters'].get('Base')
                uv_layer=None
                if base is None and (mi['parent'] or '').split('.')[-1]=='M_bgUvScroll':
                    # Two-layer UV-scroll albedo has no Base: on the inspected Phasmascapes DiffuseB is the scene picture
                    # and DiffuseA the shared scrolling shimmer overlay. Render DiffuseB statically (no scroll/blend).
                    for _k in ('DiffuseB','DiffuseA'):
                        if mi['parameters'].get(_k,{}).get('kind')=='texture':base=mi['parameters'][_k];uv_layer=_k;break
                if not base or base['kind']!='texture':raise ValueError('No explicit Base texture parameter')
                tp=find_asset(content,base['value'],dependencies)
                image,metadata=native.decode_texture(tp)
                texture_key=hashlib.sha256(json.dumps(metadata['source_file_hashes'],sort_keys=True).encode()).hexdigest()
                target=self.cache/(texture_key+'.png')
                if not target.exists():image.save(target)
                tex=np.asarray(image.convert('RGBA'));dye=self.dyes.get(item_id);dyed=False
                parent=(mi['parent'] or '').split('/')[-1].split('.')[0];params=mi['parameters']
                if parent in ('M_MasterFoliageSpec','M_MasterFoliage','M_MasterOpacityMask','M_MasterOpacityMaskTwoSided','M_FoliageVertexColor'):entry['cutout']=True   # Base alpha is opacity here
                elif parent.startswith('M_bg') and (tex[...,3]<32).mean()>0.10 and ((tex[...,3]>=32)&(tex[...,3]<=224)).mean()<0.10:entry['cutout']=True   # housing-bg masked leaves/lattices: bimodal alpha with large holes = opacity (data-driven; alpha elsewhere is a dye mask)
                if self.mi_tint:
                    def _s(v):return [float(_srgb(np.asarray(max(0.0,min(1.0,x)))) )*255 for x in v[:3]]
                    if parent in ('M_MasterTint','M_MasterTintMask','M_bgColorChange','M_MasterEmissiveTintMask') and 'Tint' not in params and color is None and mi['parent']:
                        # MI omits Tint: use the master's own default (decoded from the extracted master material when available)
                        try:_mp=find_asset(content,mi['parent'].split('.')[0],dependencies);_dt=native.master_default_tint(_mp)
                        except (FileNotFoundError,ValueError,StopIteration):_dt=None
                        if _dt is not None:params=dict(params,Tint={'kind':'vector','value':[*_dt,1.0]});entry['mi_tint_source']='parent-default'
                    if parent in ('M_MasterTint','M_MasterTintMask','M_bgColorChange','M_MasterEmissiveTintMask') and ('Tint' in params or color is not None):   # the MI may omit Tint (default lives in the parent material); an explicit dye still applies
                        tex=apply_default_dye(tex,list(color) if color is not None else _s(params['Tint']['value']));entry['mi_tint']=params['Tint']['value'][:3] if 'Tint' in params else 'parent-default';entry['instance_dye']=list(color) if color is not None else None;dye=None
                    elif 'FixedTint' in params:
                        b=_lin(tex[...,:3].astype(float)/255)*np.asarray(params['FixedTint']['value'][:3],float);r=tex.copy();r[...,:3]=np.clip(_srgb(b)*255+.5,0,255).astype(np.uint8);tex=r;entry['mi_fixed_tint']=params['FixedTint']['value'][:3];dye=None
                if not self.mi_tint and dye is not None and ('Tint' in mi['parameters'] or 'RefractionDepthBias' in mi['parameters']):   # dye-capable master-material permutation (book slots / armchair have neither)
                    tex=apply_default_dye(tex,dye);dyed=True
                if parent.startswith('M_MasterEmissive'):
                    # Emissive masters: whole-slot emitters (bulbs, flames) glow fully; masked variants (shade/panel where a texture channel
                    # limits the glow, mask not decoded) glow at 0.6 so the slot reads lit without flooding its unlit parts.
                    _ev=next((params[k]['value'] for k in ('EmissiveTint','EmissiveColor') if params.get(k,{}).get('kind')=='vector'),(1.0,.85,.6))
                    _m=max(max(_ev[:3]),1e-6);_f=1.0 if parent in ('M_MasterEmissive','M_MasterEmissiveFixedTint','M_MasterEmissiveTint') else 0.6
                    entry['emissive']=tuple(_f*float(max(0.0,c))/_m for c in _ev[:3])
                if guessed:entry['warning']=guessed
                if uv_layer:entry['uv_scroll_layer']=uv_layer;entry['warning']=f'M_bgUvScroll: static {uv_layer} layer only (scroll/overlay blend not rendered)'
                entry.update(texture=tex,texture_cache=str(target),texture_sources=metadata['source_file_hashes'],dyed_with=list(dye) if dyed else None,
                    material_source_sha256=mi['source_sha256'],parent=mi['parent'],tint=mi['parameters'].get('Tint',{}).get('value'))
            except (ValueError,KeyError,struct.error,IndexError,OSError) as error:entry['warning']=str(error)
            if entry['texture'] is None:
                fb=self.fallback_colours.get(item_id)
                if fb: entry['flat_color']=((int(fb[1:3],16)/255, int(fb[3:5],16)/255, int(fb[5:7],16)/255))
            decoded.append(entry)
        components=[]
        if path.stem.endswith('PartitionDoor'):
            # Interactive partition frames and movable leaves are separate native
            # meshes. Attach one leaf per decoded hinge (Log has two), preserving
            # the socket pose; this does not simulate the game's open/close state.
            from ..geometry import read_static_mesh_bounds
            leaf_path=path.with_name(path.stem+'_Door.uexp')
            dependencies.update(leaf_path.with_suffix(s) for s in ('.uasset','.uexp','.ubulk'))
            sockets=door_hinge_sockets(path)
            if not sockets:raise ValueError(f'No native DoorHinge socket for {path.stem}')
            leaf_record=read_static_mesh_bounds(leaf_path);leaf_record['item_id']=item_id
            leaf_assets=Assets([leaf_record],self.cache,dyes=self.dyes,fallback_colours=self.fallback_colours,
                               mi_tint=self.mi_tint,resource_cache=self.resource_cache)
            leaf=leaf_assets.load(item_id,color)
            dependencies.update(leaf_assets.dependencies)
            notes.extend('Door leaf: '+note for note in leaf_assets.coverage[0]['notes'])
            for socket in sockets:
                a=np.radians(socket['yaw_degrees']);c,s=np.cos(a),np.sin(a)
                rotation=np.array([[c,-s,0],[s,c,0],[0,0,1]])
                attached=leaf['vertices']@rotation.T+socket['translation_m']
                vertex_offset=len(vertices);triangle_offset=len(triangles);material_offset=len(decoded)
                vertices=np.concatenate((vertices,attached));triangles=np.concatenate((triangles,leaf['triangles']+vertex_offset))
                uv=np.concatenate((uv,leaf['uv']))
                groups.extend(dict(material_index=g['material_index']+material_offset if g['material_index']>=0 else -1,
                                   first_triangle=g['first_triangle']+triangle_offset,triangle_count=g['triangle_count']) for g in leaf['groups'])
                decoded.extend(leaf['materials'])
                components.append(dict(socket,source=leaf_record['source'],source_sha256=leaf_record['source_sha256'],
                                       pose='native-socket',app_verified=False,vertex_start=vertex_offset,
                                       vertex_count=len(attached),triangles=len(leaf['triangles'])))
            notes.append('Movable partition leaves use decoded native DoorHinge socket poses; interaction/animation is not simulated')
        result={'vertices':np.asarray(vertices),'triangles':np.asarray(triangles),'uv':uv,'groups':groups,'materials':decoded,
                **({'components':components} if components else {})}
        self.loaded[key]=result
        self.coverage.append({'item_id':item_id,'source':record['source'],'source_sha256':record['source_sha256'],
            'triangles':len(triangles),'sections':len(groups),'material_slots':len(decoded),
            'textured_slots':sum(d['texture'] is not None for d in decoded),'notes':notes,
            'materials':[{k:v for k,v in d.items() if k!='texture'} for d in decoded],
            **({'components':components} if components else {})})
        self.dependencies.update(dependency_snapshot(dependencies))
        if self.resource_cache is not None:self.resource_cache.put(resource_key,result,self.coverage[-1],dependencies)
        return result
