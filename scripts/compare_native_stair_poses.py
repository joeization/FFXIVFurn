"""Comparison only: native style overrides versus default component pose candidates."""
from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
from PIL import Image,ImageDraw
OUT=ROOT/'outputs/interior-direction-audit';BASE=OUT/'legacy/MakePlace/Content/HouseAssets/InteriorStyles'
def main():
    audit=json.loads((OUT/'audit.json').read_text())
    objdir=OUT/'stair-obj';objdir.mkdir(exist_ok=True)
    for r in audit['stairs']:
        v,t=read_static_mesh_triangles(r['geometry']);(objdir/(r['style']+'-'+r['mesh']+'.obj')).write_text('# metres; model-local; no materials\n'+''.join('v %.8f %.8f %.8f\n'%p for p in v)+''.join('f %d %d %d\n'%tuple(i+1 for i in tri) for tri in t),encoding='ascii')
    im=Image.new('RGB',(1500,620),'#182029');d=ImageDraw.Draw(im);results=[]
    for col,style in enumerate(('Shirogane','Minimalist','DarkMinimalist')):
        ox=col*500+30;oy=60;sc=18
        def xy(p):return (ox+(p[0]+13)*sc,oy+(9-p[1])*sc)
        d.text((ox,15),style+' / native pose evidence',fill='white')
        d.rectangle([xy((-12,8)),xy((12,-8))],outline='#8b9aa5')
        # Native local upper floor shape, translated +7 m only for the landing diagnostic.
        fp=BASE/style/'Medium/UpperFloor.uexp'
        if not fp.exists():fp=BASE/'SizeCommon/Medium/UpperFloor.uexp'
        fv,ft=read_static_mesh_triangles(read_static_mesh_bounds(fp))
        floor=unary_union([p for tri in ft if (p:=Polygon([(fv[i][0],fv[i][1]) for i in tri])).area>1e-8])
        for tri in ft:d.polygon([xy(fv[i]) for i in tri],fill='#26343c')
        stairrec=next(r for r in audit['stairs'] if r['style']==style and r['mesh']=='Stair1')
        v,t=read_static_mesh_triangles(stairrec['geometry'])
        for actor in ('Stairs','Stairs2_9'):
            a=next(x for x in audit['medium_style_transforms'] if x['actor']==actor)
            if style=='Shirogane':
                comp=next(x for x in audit['medium_components'] if x['export']['outer']==a['export']['index'])
                loc=comp['translation_candidate_m'];scale=comp['scale_candidate'];yaw=0
                qualification='component translation/scale; default yaw=0 assumption'
            else:
                entry=next(x for x in a['style_entries'] if x['style']==style)
                loc=entry['translation_m'];scale=entry['scale'];yaw=entry['yaw_deg'];qualification='native named style FTransform, full scale applied'
            c=math.cos(math.radians(yaw));s=math.sin(math.radians(yaw))
            w=[(c*x*scale[0]-s*y*scale[1]+loc[0],s*x*scale[0]+c*y*scale[1]+loc[1],z*scale[2]+loc[2]) for x,y,z in v]
            for tri in sorted(t,key=lambda tri:sum(w[i][2] for i in tri)):
                p=[w[i] for i in tri]
                if max(x[2] for x in p)-min(x[2] for x in p)>.01:continue
                area=Polygon([(x[0],x[1]) for x in p]).area
                if area<.005:continue
                z=sum(x[2] for x in p)/3
                k=max(0,min(1,(z-loc[2])/7))
                d.polygon([xy(x) for x in p],fill=(int(50+k*190),int(100+k*130),int(160+k*70)))
            # The z=7 tread band measures adjacency to upper floor, not exact navigation.
            band=[p for tri in t if all(abs(w[i][2]-(loc[2]+7))<.18 for i in tri) and (p:=Polygon([(w[i][0],w[i][1]) for i in tri])).area>.01]
            landing=unary_union(band)
            overlap=landing.intersection(floor.buffer(.08)).area/landing.area if landing.area else None
            results.append(dict(style=style,actor=actor,translation_m=loc,scale=scale,yaw_deg=yaw,evidence=qualification,bounds_xy=[min(p[0] for p in w),min(p[1] for p in w),max(p[0] for p in w),max(p[1] for p in w)],landing_band_area=landing.area,upper_floor_xy_overlap_fraction=overlap,landing_xy_distance_to_upper_floor_m=landing.distance(floor) if landing.area else None))
        d.text((ox,410),'WORLD +X right / +Y up; NOT screen-mirrored',fill='#becbd5')
        d.text((ox,430),'Dark=low; bright=high. Grey=upper floor XY.',fill='#becbd5')
        d.text((ox,455),'Shirogane yaw0 candidate; others native overrides.',fill='#edc879')
    im.save(OUT/'medium-native-pose-comparison.png')
    (OUT/'pose-comparison.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(dict(exported_obj=len(list(objdir.glob('*.obj'))),poses=results),indent=2))
if __name__=='__main__':main()
