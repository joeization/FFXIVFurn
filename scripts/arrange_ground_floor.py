"""Ground-floor test arrangement using measured geometry, allowing intentional overlap."""
import argparse
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.layout import build_layout
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles


def barycentric_xy(point,a,b,c):
    x,y=point
    det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(det)<1e-10:return None
    u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/det
    v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/det
    w=1-u-v
    return (u,v,w) if min(u,v,w)>=-1e-7 else None


def projected_surface(points,triangles,x,y):
    hits=[]
    for triangle in triangles:
        a,b,c=(points[i] for i in triangle)
        weights=barycentric_xy((x,y),a,b,c)
        if weights:hits.append(sum(w*p[2] for w,p in zip(weights,(a,b,c))))
    if not hits:raise ValueError(f'No measured support triangle at {x,y}')
    return max(hits)


def rotated_bounds(g,pivot,yaw):
    angle=math.radians(yaw);co=math.cos(angle);si=math.sin(angle)
    points=[(pivot[0]+co*x-si*y,pivot[1]+si*x+co*y) for x in (g['min_x'],g['max_x']) for y in (g['min_y'],g['max_y'])]
    return {'min':[min(p[0] for p in points),min(p[1] for p in points),pivot[2]+g['min_z']],
            'max':[max(p[0] for p in points),max(p[1] for p in points),pivot[2]+g['max_z']]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=str(ROOT/'data/furniture-test.sqlite3'))
    p.add_argument('--seed',default=os.environ.get('DECO_SEED'),help='complete layout JSON (default: $DECO_SEED)')
    p.add_argument('--output-dir',default=str(ROOT/'outputs/ground-floor'))
    a=p.parse_args();out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    source_records=json.load(open(ROOT/'outputs/geometry/fill-result.json',encoding='utf-8'))['records']
    source_by_id={r['item_id']:r for r in source_records}
    floor_record=json.load(open(ROOT/'outputs/geometry/house-bounds.json',encoding='utf-8'))[0]
    floor_points,floor_triangles=read_static_mesh_triangles(floor_record)
    instances=[];by_label={};mesh_cache={}
    with FurnitureDB(a.db) as db:
        db.connection.row_factory=__import__('sqlite3').Row
        def place(label,item_id,x,y,yaw=0,base=0,group=None,support=None):
            row=db.connection.execute('SELECT * FROM furniture_bounds WHERE id=?',(item_id,)).fetchone()
            if row is None:raise ValueError(f'Measured DB bounds required for {item_id}')
            g=dict(row)
            co=math.cos(math.radians(yaw));si=math.sin(math.radians(yaw))
            px=x-(co*g['center_x']-si*g['center_y']);py=y-(si*g['center_x']+co*g['center_y'])
            support_z=base
            if support:
                parent=by_label[support];parent_id=parent['item_id']
                if parent_id not in mesh_cache:mesh_cache[parent_id]=read_static_mesh_triangles(source_by_id[parent_id])
                angle=math.radians(parent['yaw_degrees']);dx=x-parent['pivot_m'][0];dy=y-parent['pivot_m'][1]
                lx=math.cos(angle)*dx+math.sin(angle)*dy;ly=-math.sin(angle)*dx+math.cos(angle)*dy
                support_z=projected_surface(*mesh_cache[parent_id],lx,ly)+parent['pivot_m'][2]
            pivot=[px,py,support_z-g['min_z']]
            instance={'label':label,'item_id':item_id,'name':g['name'],'center_xy_m':[x,y],
                'pivot_m':pivot,'yaw_degrees':yaw,'intentional_overlap_group':group,
                'support_instance':support,'support_height_m':support_z,'bounds':rotated_bounds(g,pivot,yaw),
                'dimensions_m':[g['length'],g['width'],g['height']]}
            instances.append(instance);by_label[label]=instance
        # West/south lounge: two slightly staggered overlapping flooring mats avoid coplanar z fighting.
        place('lounge-floor-a',28134,-9,-4.8,group='lounge-floor')
        place('lounge-floor-b',28134,-6.5,-4.8,base=.002,group='lounge-floor')
        place('lounge-sofa-south',28639,-8,-6.1,base=.032,group='L-shaped-seating')
        place('lounge-sofa-west',28639,-10.1,-4.5,yaw=-90,base=.032,group='L-shaped-seating')
        place('tea-table',13075,-7.8,-4.1,base=.032)
        place('lounge-cupboard',20735,-5.1,-5.4,yaw=90,base=.032)
        place('tea-lantern',6637,-7.4,-4.1,support='tea-table')
        place('tea-mug-a',32205,-8.1,-4.15,support='tea-table')
        place('tea-mug-b',32205,-7.75,-3.75,support='tea-table')
        # East/south bar: the curved Manor Desk acts as a counter, not an ordinary small desk.
        place('bar-counter',6619,7,-5.7,group='bar-built-in')
        place('bar-bottle-shelf',33279,7,-7.2)
        place('bar-cupboard',6560,10.5,-7.1,group='bar-built-in')
        for i,x in enumerate((5.6,7,8.4),1):place(f'bar-seat-{i}',22559,x,-3.8,yaw=180)
        place('bar-tap',28145,5.9,-5.6,support='bar-counter')
        place('bar-bottles',28151,7.0,-5.6,support='bar-counter')
        place('bar-spirits',15977,8.4,-5.85,support='bar-counter')
        for i,x in enumerate((6.25,7.35,8.25),1):place(f'bar-mug-{i}',32205,x,-5.25,support='bar-counter')
        place('bar-lantern',6637,5.4,-6.0,support='bar-counter')
        for i,x in enumerate((4.8,5.87,6.94,8.01,9.08),1):place(f'bar-screen-{i}',32226,x,-7.65,group='bar-screen-wall')
        # East/north water garden: pond and waterfall deliberately interpenetrate to form one rock garden.
        place('garden-pond',33258,7.3,5,group='rock-water-garden')
        place('garden-waterfall',35561,9.5,6,group='rock-water-garden')
        for i,x in enumerate((8.6,9.67,10.74),1):place(f'garden-screen-{i}',32226,x,7.55,group='garden-screen-wall')
        # Low foyer lights on measured stool surfaces, leaving central circulation free.
        for side,x in [('west',-1.8),('east',1.8)]:
            place(f'foyer-plinth-{side}',8786,x,5.8)
            place(f'foyer-light-{side}',6637,x,5.8,support=f'foyer-plinth-{side}')
        seed_bytes=Path(a.seed).read_bytes();seed=json.loads(seed_bytes)
        scale=seed['interiorScale']
        placements=[{'item_id':r['item_id'],'location':[x*scale for x in r['pivot_m']],'yaw_degrees':r['yaw_degrees']} for r in instances]
        layout=build_layout(db,seed,placements)
    # Intersections are reported, NOT globally rejected. Explicit composites are a valid design feature.
    overlaps=[]
    for i,left in enumerate(instances):
        for right in instances[i+1:]:
            depths=[min(left['bounds']['max'][j],right['bounds']['max'][j])-max(left['bounds']['min'][j],right['bounds']['min'][j]) for j in range(3)]
            if min(depths)>1e-4:
                support_relation=left['support_instance']==right['label'] or right['support_instance']==left['label']
                intentional=bool(support_relation or (left['intentional_overlap_group'] and left['intentional_overlap_group']==right['intentional_overlap_group']))
                overlaps.append({'left':left['label'],'right':right['label'],'intentional':intentional,
                    'reason':'mesh-verified support; AABB includes raised trim' if support_relation else 'explicit composite group' if intentional else 'unassigned overlap warning',
                    'bbox_intersection_m':depths})
    outside=[];corridor=[];too_high=[]
    for instance in instances:
        b=instance['bounds']
        points=[(x,y) for x in (b['min'][0],(b['min'][0]+b['max'][0])/2,b['max'][0]) for y in (b['min'][1],(b['min'][1]+b['max'][1])/2,b['max'][1])]
        if any(not any(barycentric_xy(p,*(floor_points[i] for i in t)) for t in floor_triangles) for p in points):outside.append(instance['label'])
        if b['max'][2]>6.5001:too_high.append(instance['label'])
        # Intentional design-reserved corridors, not a claim of verified in-game doors/stairs.
        if (b['min'][0]<1.2 and b['max'][0]>-1.2) or (b['min'][1]<1 and b['max'][1]>-1):corridor.append(instance['label'])
    if outside or corridor or too_high:raise ValueError(json.dumps({'outside_floor_projection':outside,'reserved_corridor':corridor,'above_native_frame':too_high}))
    encoding='utf-16' if seed_bytes.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8'
    path=out/'GroundFloor_Woodland_Lounge.json'
    path.write_bytes((json.dumps(layout,ensure_ascii=False,indent='\t',allow_nan=False)+'\n').encode(encoding))
    assert json.loads(path.read_bytes())==layout
    report={'layout':str(path.resolve()),'theme':'warm wood lounge, curved bar, overlapping indoor rock-water garden',
         'instances':instances,'overlaps':overlaps,'outside_floor_projection':outside,'reserved_corridor_obstructions':corridor,
         'above_native_frame':too_high,'support_method':'ray intersection with measured parent mesh triangles, not guessed tabletop height',
         'frame_bounds_m':{'x':[-12,12],'y':[-8,8],'height':6.5},
         'app_import_tested':False,'runtime_house_actor_transform_verified':False,
         'exact_collision_tested':False,'intentional_overlaps_allowed':True,'original_save_modified':False}
    (out/'arrangement-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    # This is a measured footprint plan, not a rendered ReMakePlace screenshot.
    from PIL import Image,ImageDraw
    im=Image.new('RGB',(1320,940),'#182029');d=ImageDraw.Draw(im)
    project=lambda x,y:(round(80+(x+12)*42),round(80+(8-y)*42))
    for t in floor_triangles:
        pts=[floor_points[i] for i in t]
        d.polygon([project(v[0],v[1]) for v in pts],fill='#d8d0be')
    d.rectangle([project(-1.2,8),project(1.2,-8)],fill='#a5b99d')
    d.rectangle([project(-12,1),project(12,-1)],fill='#a5b99d')
    colors={'lounge':'#aa6c59','tea':'#bd8c51','bar':'#705344','garden':'#4f8579','foyer':'#b3a270'}
    for index,instance in enumerate(instances,1):
        b=instance['bounds'];group=instance['label'].split('-')[0];color=colors.get(group,'#a48468')
        d.rectangle([project(b['min'][0],b['max'][1]),project(b['max'][0],b['min'][1])],outline=color,width=2)
        if not instance['support_instance'] and 'screen' not in instance['label'] and 'floor' not in instance['label']:
            d.text(project(*instance['center_xy_m']),str(index),fill='#12202a')
    for i in range(-12,13,2):d.text((project(i,8)[0],50),str(i),fill='white')
    for i in range(-8,9,2):d.text((40,project(0,i)[1]),str(i),fill='white')
    d.text((20,20),'Measured XY footprint plan (m) - intentional overlaps allowed; not app render',fill='white')
    d.text((1120,80),'SW: Lounge\nSE: Curved bar\nNE: Water garden\nGreen: reserved\ncirculation\n\nTables use real\nmesh support rays',fill='white',spacing=6)
    im.save(out/'GroundFloor_Footprints.png')
    print(json.dumps({'layout':str(path.resolve()),'instances':len(instances),'unique_items':len(set(r['item_id'] for r in instances)),
         'intentional_overlap_pairs':sum(r['intentional'] for r in overlaps),'other_bbox_overlap_warnings':[r for r in overlaps if not r['intentional']],
         'floor_outside':outside,'corridor_obstructions':corridor,'app_import_tested':False},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
