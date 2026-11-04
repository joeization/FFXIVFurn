"""Render/export Opus's design without changing its selections or XY layout."""
import importlib.util
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from ffxiv_furniture.housing import validate_layout_budget
from ffxiv_furniture.layout import build_layout
spec=importlib.util.spec_from_file_location('ground',ROOT/'scripts/arrange_ground_floor.py');ground=importlib.util.module_from_spec(spec);spec.loader.exec_module(ground)


def main():
    out=ROOT/'outputs/opus-one-floor';design=json.loads((out/'design.json').read_text(encoding='utf-8'))
    source_records=json.loads((ROOT/'outputs/geometry/fill-result.json').read_text(encoding='utf-8'))['records']
    source_by_id={r['item_id']:r for r in source_records};mesh_cache={};by_label={};instances=[];warnings=[]
    with FurnitureDB(ROOT/'data/furniture-test.sqlite3') as db:
        for row in design['placements']:
            if row['label'] in by_label:raise ValueError('Duplicate placement label')
            item=db.get_furniture(row['item_id'])
            if not item or item['scope']!='interior':raise ValueError('Non-DB or non-interior item')
            g=dict(db.connection.execute('SELECT * FROM furniture_bounds WHERE id=?',(row['item_id'],)).fetchone())
            x,y,yaw=row['x'],row['y'],row['yaw_degrees'];angle=math.radians(yaw);co,si=math.cos(angle),math.sin(angle)
            px=x-(co*g['center_x']-si*g['center_y']);py=y-(si*g['center_x']+co*g['center_y']);base=row['base_m']
            if row['support']:
                parent=by_label[row['support']];iid=parent['item_id']
                if iid not in mesh_cache:mesh_cache[iid]=read_static_mesh_triangles(source_by_id[iid])
                a=math.radians(parent['yaw_degrees']);dx=x-parent['pivot_m'][0];dy=y-parent['pivot_m'][1]
                lx=math.cos(a)*dx+math.sin(a)*dy;ly=-math.sin(a)*dx+math.cos(a)*dy
                try:base=ground.projected_surface(*mesh_cache[iid],lx,ly)+parent['pivot_m'][2]
                except ValueError:
                    warnings.append({'label':row['label'],'issue':'No real support triangle at Opus XY; retained explicit Opus base_m instead; placement requires inspection'})
            pivot=[px,py,base-g['min_z']]
            inst={**row,'name':item['name'],'pivot_m':pivot,'bounds':ground.rotated_bounds(g,pivot,yaw)}
            instances.append(inst);by_label[row['label']]=inst
        seed_path=Path('D:/Downloads/ReMakeplace-V7-57-1/MakePlace/Save/Save.json');seed_bytes=seed_path.read_bytes();seed=json.loads(seed_bytes)
        scale=seed['interiorScale']
        layout=build_layout(db,seed,[{'item_id':i['item_id'],'location':[v*scale for v in i['pivot_m']],'yaw_degrees':i['yaw_degrees']} for i in instances])
    floor_record=json.loads((ROOT/'outputs/geometry/house-bounds.json').read_text(encoding='utf-8'))[0]
    floor_points,floor_triangles=read_static_mesh_triangles(floor_record)
    for i in instances:
        b=i['bounds']
        points=[(x,y) for x in (b['min'][0],(b['min'][0]+b['max'][0])/2,b['max'][0]) for y in (b['min'][1],(b['min'][1]+b['max'][1])/2,b['max'][1])]
        if any(not any(ground.barycentric_xy(p,*(floor_points[v] for v in t)) for t in floor_triangles) for p in points):warnings.append({'label':i['label'],'issue':'Footprint extends outside measured floor projection'})
        if b['max'][2]>6.5001:warnings.append({'label':i['label'],'issue':'Above 6.5m measured frame height'})
        if b['min'][0]<1.2 and b['max'][0]>-1.2:warnings.append({'label':i['label'],'issue':'Intersects reserved central passage'})
    overlap=[]
    for n,a in enumerate(instances):
        for b in instances[n+1:]:
            depth=[min(a['bounds']['max'][i],b['bounds']['max'][i])-max(a['bounds']['min'][i],b['bounds']['min'][i]) for i in range(3)]
            if min(depth)>.001:
                intentional=bool(a['support']==b['label'] or b['support']==a['label'] or (a['intentional_overlap_group'] and a['intentional_overlap_group']==b['intentional_overlap_group']))
                overlap.append({'left':a['label'],'right':b['label'],'declared_intentional_or_support':intentional,'aabb_intersection_m':depth})
    encoding='utf-16' if seed_bytes.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8'
    target=out/'Opus_GroundFloor.json';target.write_bytes((json.dumps(layout,ensure_ascii=False,indent=2)+'\n').encode(encoding))
    assert json.loads(target.read_bytes())==layout
    report={'title':design['title'],'instances':instances,'warnings':warnings,'aabb_overlaps':overlap,'budget':validate_layout_budget(layout),
        'opus_xy_or_item_choices_modified':False,'support_height_computed_from_real_mesh':True,'app_import_verified':False,
        'world_actor_transforms_verified':False,'original_save_modified':False}
    (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    # Screen X is mirrored per the user's observed app/old-plan orientation mismatch.
    from PIL import Image,ImageDraw,ImageFont
    im=Image.new('RGB',(1500,1050),'#1c242a');d=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',18);small=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',14);large=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',27)
    xy=lambda x,y:(round(90+(12-x)*42),round(100+(8-y)*42))
    for t in floor_triangles:d.polygon([xy(floor_points[v][0],floor_points[v][1]) for v in t],fill='#d7cdb7')
    d.rectangle([xy(1.2,8),xy(-1.2,-8)],fill='#adbea4')
    palette=['#438e95','#8a5a48','#9b759f','#bd8848','#557f65'];zones={z['name']:palette[k%len(palette)] for k,z in enumerate(design['zones'])}
    for k,i in enumerate(instances,1):
        b=i['bounds'];color=zones[i['zone']]
        d.rectangle([xy(b['max'][0],b['max'][1]),xy(b['min'][0],b['min'][1])],outline=color,width=3)
        if not i['support']:d.text(xy(i['x'],i['y']),str(k),fill='#172126',font=small)
    d.text((35,25),design['title'],font=large,fill='white')
    d.text((35,65),'Opus 配置 / 模型占地圖（非 app 渲染）・圖像 X 反轉，JSON 座標不變',font=small,fill='#c2cdd0')
    y=115
    for zone in design['zones']:
        d.rectangle((1140,y,1158,y+18),fill=zones[zone['name']]);d.text((1170,y),zone['name'].replace('_','\n'),font=small,fill='white');y+=115
    d.text((40,820),'保留中央通道；上方兩側樓梯區未配置。編號對應 placements。',font=font,fill='white')
    d.text((40,855),f'{len(instances)} 件 / Medium 全屋室內 450 件上限；有意重疊合法。',font=font,fill='white')
    d.text((40,890),f'幾何檢查警告 {len(warnings)} 件次；尚未實際載入 ReMakePlace。',font=font,fill='#e8bb8c')
    im.save(out/'Opus_Footprint_Preview.png')
    print(json.dumps({'layout':str(target),'instances':len(instances),'unique_items':len({i['item_id'] for i in instances}),'warnings':warnings,
        'unassigned_bbox_overlap_pairs':sum(not o['declared_intentional_or_support'] for o in overlap)},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
