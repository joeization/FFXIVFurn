"""Read-only native house-size/stair survey. No guessed world transforms."""
from pathlib import Path
import hashlib
import json
import struct
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles


def map_tables(path):
    """Bounded retoc legacy UE5.3 name/import/export table reader; NOT property decoder."""
    b=path.read_bytes();data=path.with_suffix('.uexp').read_bytes()
    if b[:4]!=bytes.fromhex('c1832a9e') or struct.unpack_from('<i',b,4)[0]!=-8:raise ValueError('Unsupported package header')
    length=struct.unpack_from('<i',b,32)[0]
    if not 0<length<1024:raise ValueError('Unexpected package name')
    fields=struct.unpack_from('<11i',b,36+length+4)
    nc,no=fields[:2];ec,eo,ic,io,dep=fields[6:11]
    if not 0<nc<10000 or (dep-eo)!=ec*96 or eo-io!=ic*32:raise ValueError('Unexpected table strides')
    names=[];pos=no
    for _ in range(nc):
        size=struct.unpack_from('<i',b,pos)[0];pos+=4
        if not 0<abs(size)<10000:raise ValueError('Unexpected name length')
        end=pos+(size if size>0 else -size*2)
        names.append(b[pos:end].decode('utf-8' if size>0 else 'utf-16-le').rstrip(chr(0)));pos=end+4
    if pos>io:raise ValueError('Name table overlaps imports')
    def name(index,number):
        if not 0<=index<len(names):raise ValueError('Bad FName')
        return names[index]+('_'+str(number-1) if number else '')
    imports=[]
    for i in range(ic):
        a,an,c,cn,outer,n,nn,package=struct.unpack_from('<8i',b,io+32*i)
        if not -ic<=outer<=ec:raise ValueError('Bad import outer')
        imports.append({'index':-(i+1),'name':name(n,nn),'class':name(c,cn),'outer':outer})
    def resolve(index,visited=()):
        if not index:return ''
        if index>0:return 'export:'+str(index)
        if index in visited:raise ValueError('Cyclic import')
        row=imports[-index-1];outer=resolve(row['outer'],visited+(index,))
        return (outer+'.' if outer else '')+row['name']
    exports=[]
    for i in range(ec):
        off=eo+96*i;cl,sup,tmp,outer,ni,num,flags=struct.unpack_from('<6iI',b,off)
        size,at=struct.unpack_from('<qq',b,off+28)
        if not -ic<=cl<=ec or not 0<=outer<=ec or size<0 or not len(b)<=at<=len(b)+len(data) or at+size>len(b)+len(data):raise ValueError('Invalid export region')
        exports.append({'index':i+1,'name':name(ni,num),'class':resolve(cl),'outer':outer,
                        'serial_offset_in_uexp':at-len(b),'serial_size':size})
    return {'path':str(path.resolve()),'sha256':hashlib.sha256(b+data).hexdigest(),
            'imports':[{**r,'resolved':resolve(r['index'])} for r in imports], 'exports':exports,
            'property_transforms_decoded':False}


def main():
    out=ROOT/'outputs/house-layouts';out.mkdir(parents=True,exist_ok=True)
    legacy=ROOT/'data/house-legacy/MakePlace/Content'
    verified=[];unsupported=[]
    for sub in ('HouseAssets/InteriorStyles','HouseAssets/MainDoor'):
        for p in sorted((legacy/sub).rglob('*.uexp')):
            try:verified.append(read_static_mesh_bounds(p))
            except ValueError as e:unsupported.append({'source':str(p),'error':str(e)})
    write=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
    write(out/'native-bounds.json',{'records':verified,'unsupported_assets':unsupported})
    maps={size:map_tables(legacy/'Maps'/('XIV'+size+'House.umap' if size!='Apartment' else 'XIVApartment.umap')) for size in ['Small','Medium','Large','Apartment']}
    write(out/'native-map-tables.json',maps)
    notes={
        'Small':{'floors':['ground','basement'],'connections':[{'from':'ground','to':'basement','native_mesh':'Stair5','mapping':'map imports corroborate one staircase family; additional ceiling actor is not a second staircase'}]},
        'Medium':{'floors':['ground','upper','basement'],'connections':[{'from':'ground','to':'upper','native_mesh':'Stair1'},{'from':'ground','to':'basement','native_mesh':'Stair1'}], 'user_observation':'Previous plan: upper-left goes up, upper-right goes down. Display left/right remain view-dependent.'},
        'Large':{'floors':['ground','upper','basement'],'connections':[{'from':'ground','to':'upper','native_mesh':'Stair4','native_actor':'MainStairs'},{'from':'ground','to':'basement','native_mesh':'Stair3','native_actor':'BasementStairs'}]},
        'Apartment':{'floors':['ground'],'connections':[]}}
    for size,n in notes.items():
        m=maps[size]
        n['native_map']=m['path'];n['map_sha256']=m['sha256']
        n['map_stair_imports']=[r for r in m['imports'] if '/Stair/' in r['resolved']]
        n['map_stair_exports']=[r for r in m['exports'] if 'Stair' in r['name']]
        n['stair_asset_world_transforms']=None
        n['stair_keepout_polygons']=None
        n['safe_for_exact_automatic_placement']=False
        n['evidence_limit']='Native map references and local mesh geometry verified; unversioned actor/component properties not decoded. Never place local meshes at origin and treat as house layout.'
    # Machine-readable source geometries, with each tread's local XY projection and height.
    treads=[]
    for r in verified:
        source=Path(r['source'])
        if source.parent.name!='Stair' or 'Ceiling' in source.stem:continue
        try:
            vertices,triangles=read_static_mesh_triangles(r)
            horizontal=[]
            for tri in triangles:
                pts=[vertices[i] for i in tri]
                if max(v[2] for v in pts)-min(v[2] for v in pts)<.005:
                    area=abs((pts[1][0]-pts[0][0])*(pts[2][1]-pts[0][1])-(pts[2][0]-pts[0][0])*(pts[1][1]-pts[0][1]))/2
                    if area>.005:horizontal.append({'xy_m':[[v[0],v[1]] for v in pts],'z_m':sum(v[2] for v in pts)/3})
            treads.append({'mesh':source.stem,'source':r['source'],'source_sha256':r['source_sha256'],
                'local_min_m':r['local_min_m'],'local_max_m':r['local_max_m'],'horizontal_triangles':horizontal,'world_transform':None})
        except ValueError as e:unsupported.append({'source':str(source),'error':str(e)})
    write(out/'stair-local-triangles.json',treads)
    write(out/'house-layouts.json',{'sizes':notes,'units':'metres','coordinate_space':'model-local; not calibrated screen left/right',
        'verified_native_mesh_count':len(verified),'stair_mesh_count':len(treads),
        'limitations':['Static mesh local bounds are not scene actor transforms.','District variants need separate checks.','Island is an outdoor map, not a multistorey estate size.']})
    # Reference sheets, separate local mesh views; no fabricated overlay of unknown transforms.
    from PIL import Image,ImageDraw
    sheet=Image.new('RGB',(1200,900),'#182029');d=ImageDraw.Draw(sheet)
    for i,suffix in enumerate(['Stair5','Stair1','Stair4','Stair3']):
        r=next(r for r in treads if r['mesh']==suffix and '/Shirogane/' in r['source'].replace(chr(92),'/'))
        ox=30+(i%2)*600;oy=30+(i//2)*440
        d.text((ox,oy),{'Stair5':'Small: down to basement','Stair1':'Medium: reused up/down','Stair4':'Large: main staircase','Stair3':'Large: basement staircase'}[suffix]+' / '+suffix,fill='white')
        mn=r['local_min_m'];mx=r['local_max_m'];scale=min(500/(mx[0]-mn[0]),330/(mx[1]-mn[1]))
        for tri in r['horizontal_triangles']:
            z=(tri['z_m']-mn[2])/max(.01,mx[2]-mn[2]);color=(round(70+170*z),round(130+80*z),round(170-70*z))
            d.polygon([(round(ox+30+(x-mn[0])*scale),round(oy+45+(mx[1]-y)*scale)) for x,y in tri['xy_m']],fill=color)
        d.text((ox,oy+395),'LOCAL geometry only; brighter = higher. No world transform.',fill='#b9c9d0')
    sheet.save(out/'stair-families-local.png')
    print(json.dumps({'sizes':list(notes),'verified_meshes':len(verified),'stair_meshes':len(treads),
                     'world_transforms_verified':False,'output':str(out)},ensure_ascii=False))


if __name__=='__main__':main()
