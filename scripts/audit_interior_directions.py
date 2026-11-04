"""Read-only interior mesh inventory and bounded Medium style-transform audit.
Does not change renderer, saves, or existing calibration outputs.
"""
from pathlib import Path
import sys,json,struct,math,hashlib
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.inspect_house_stairs import map_tables
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from PIL import Image,ImageDraw
OUT=ROOT/'outputs/interior-direction-audit'
BASE=OUT/'legacy/MakePlace/Content/HouseAssets/InteriorStyles'

def main():
    records=[]; failures=[]; meshes={}
    for p in sorted(BASE.rglob('*.uexp')):
        if p.parent.name!='Stair' or 'Collision' in p.stem or 'Ceiling' in p.stem: continue
        try:
            r=read_static_mesh_bounds(p);v,t=read_static_mesh_triangles(r)
            style=p.relative_to(BASE).parts[0]
            records.append(dict(style=style,mesh=p.stem,vertices=len(v),triangles=len(t),geometry=r))
            meshes[style,p.stem]=(v,t)
        except ValueError as e: failures.append(dict(source=str(p),error=str(e)))
    inventory={s:dict(packages=len(list((BASE/s).rglob('*.uasset'))),stairs=[r['mesh'] for r in records if r['style']==s]) for s in sorted(p.name for p in BASE.iterdir() if p.is_dir())}
    p=ROOT/'data/house-legacy/MakePlace/Content/Maps/XIVMediumHouse.umap'
    tab=map_tables(p);data=p.with_suffix('.uexp').read_bytes()
    transforms=[]
    for e in tab['exports']:
        if not e['class'].endswith('.DistrictFixture'):continue
        b=data[e['serial_offset_in_uexp']:e['serial_offset_in_uexp']+e['serial_size']]
        # Exact observed map layout: uint32 count followed by two FString/transform entries.
        assert struct.unpack_from('<I',b,14)[0]==2
        pos=18;entries=[]
        for expected in ('Minimalist','DarkMinimalist'):
            n=struct.unpack_from('<i',b,pos)[0];pos+=4
            assert 1<n<100
            key=b[pos:pos+n].decode('ascii').rstrip('\0');pos+=n
            assert key==expected
            marker=b[pos:pos+2].hex();assert marker=='0007';pos+=2
            vals=struct.unpack_from('<10d',b,pos);pos+=80
            q=vals[:4];assert abs(sum(x*x for x in q)-1)<1e-6  # DarkMinimalist railing rounded to 6 decimals
            entries.append(dict(style=key,marker=marker,offset_in_export=pos-80,quaternion_xyzw=q,translation_m=[x/100 for x in vals[4:7]],scale=vals[7:],yaw_deg=math.degrees(2*math.atan2(q[2],q[3]))))
        # Count, keys, boundaries checked; following bytes are deliberately not decoded.
        transforms.append(dict(actor=e['name'],export=e,style_entries=entries,entries_end=pos,tail_hex=b[pos:].hex()))
    # Persist map/component evidence, not a guessed generic UE property schema.
    components=[]
    actor_ids={x['export']['index'] for x in transforms}
    for e in tab['exports']:
        if e['outer'] not in actor_ids:continue
        b=data[e['serial_offset_in_uexp']:e['serial_offset_in_uexp']+e['serial_size']]
        refs=[]
        for off in range(len(b)-3):
            index=struct.unpack_from('<i',b,off)[0]
            if -len(tab['imports'])<=index<0:
                imp=tab['imports'][-index-1]
                if imp['class']=='StaticMesh':refs.append(dict(byte_offset=off,reference=imp['resolved']))
        # Known fixed trailer (13 bytes); preceding 24/48 bytes are component location/scale.
        assert b[-13:]==b'\x02'+bytes(12)
        mirrored=len(b)==110
        loc_off=len(b)-13-(48 if mirrored else 24)
        loc=struct.unpack_from('<3d',b,loc_off)
        scale=struct.unpack_from('<3d',b,loc_off+24) if mirrored else (1.,1.,1.)
        components.append(dict(export=e,raw_hex=b.hex(),mesh_references=refs,translation_candidate_m=[x/100 for x in loc],scale_candidate=scale,location_byte_offset=loc_off,qualification='bounded trailer decode; full unversioned property schema/rotation not decoded'))
    result=dict(inventory=inventory,stairs=records,failures=failures,medium_style_transforms=transforms,medium_components=components,map_sha256=tab['sha256'],limitations=['Style-entry FTransform is not the default component transform.','Default component locations/scales have bounded trailer evidence; omitted rotation still needs schema/runtime confirmation.','No renderer or existing calibration modified.'])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    # Local geometry only, same XY scale within every cell; bright = high.
    styles=[s for s in inventory if s!='SizeCommon'];cellw,cellh=360,320
    im=Image.new('RGB',(cellw*len(styles),cellh*2),'#182029');d=ImageDraw.Draw(im)
    for col,s in enumerate(styles):
        for row,n in enumerate(('Stair1','Stair2')):
            if (s,n) not in meshes:continue
            v,t=meshes[s,n];xs=[a[0] for a in v];ys=[a[1] for a in v];zs=[a[2] for a in v]
            scale=min(300/(max(xs)-min(xs)),240/(max(ys)-min(ys)));ox=col*cellw+24;oy=row*cellh+40
            for tri in sorted(t,key=lambda t:sum(v[i][2] for i in t)):
                pts=[v[i] for i in tri]
                if max(a[2] for a in pts)-min(a[2] for a in pts)>.01:continue
                z=(sum(a[2] for a in pts)/3-min(zs))/(max(zs)-min(zs))
                d.polygon([(ox+(a[0]-min(xs))*scale,oy+(max(ys)-a[1])*scale) for a in pts],fill=(int(60+190*z),int(90+140*z),int(140+80*z)))
            d.text((ox,row*cellh+12),f'{s} {n}',fill='white')
            d.text((ox,row*cellh+292),'LOCAL +X right / +Y up; bright=high',fill='#becbd5')
    im.save(OUT/'stairs-local-comparison.png')
    print(json.dumps(dict(inventory=inventory,verified_stair_meshes=len(records),failures=failures,medium_actor_style_entries=sum(len(a['style_entries']) for a in transforms),components=components),indent=2))
if __name__=='__main__':main()
