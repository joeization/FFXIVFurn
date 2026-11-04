"""Audit current MCP tools over stdio in disposable audit-prefixed sessions.
No modification of application saves, existing sessions, renderer or database.
"""
import asyncio,datetime,hashlib,json,os,sys,traceback
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('MCP_AUDIT_OUTPUT', str(ROOT/'outputs/mcp-interior-support-audit')))
STYLES=['Shirogane','Minimalist','DarkMinimalist','Mist','LavBed','Goblet','Empyreum']

def unpack(res):
    texts=[];images=[]
    for c in res.content:
        if c.type=='text':
            try:texts.append(json.loads(c.text))
            except ValueError:texts.append(c.text)
        elif c.type=='image':images.append(dict(mime=c.mimeType,base64_chars=len(c.data)))
    obj=res.structuredContent or next((v for v in texts if isinstance(v,dict)),None)
    if isinstance(obj,dict) and set(obj)=={'result'}:obj=obj['result']
    return obj,dict(is_error=bool(res.isError),texts=texts,images=images)

async def audit_style(style,stamp):
    name=f'audit-interior-{stamp}-{style.lower()}'
    env=dict(os.environ,DECO_SESSION=name,DECO_STYLE=style,DECO_FROM_LAYOUT='0')
    params=StdioServerParameters(command=sys.executable,args=['-m','ffxiv_furniture.deco.server'],cwd=str(ROOT),env=env)
    record=dict(style=style,session=name,calls=[])
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as s:
            await s.initialize();tools=await s.list_tools();record['registered_tools']=[t.name for t in tools.tools]
            async def call(tool,args=None):
                try:
                    res=await s.call_tool(tool,args or {});obj,raw=unpack(res)
                    record['calls'].append(dict(tool=tool,args=args or {},**raw));return obj
                except Exception as e:
                    record['calls'].append(dict(tool=tool,args=args or {},is_error=True,exception=str(e)));return None
            await call('status')
            await call('list_interiors')
            await call('set_interior',dict(style=style))
            await call('search_furniture',dict(query='tea set',mode='text',limit=3))
            await call('search_furniture',dict(query='small wooden chair',mode='semantic',limit=3))
            for kind in ('wall','floor','light'):await call('search_materials',dict(query='',kind=kind,limit=3))
            geo=await call('inspect',dict(include_geometry=True))
            await call('place',dict(name='Hingan Sitting Table',position=[0,-5,0],yaw_deg=0,anchor='bottom_center'))
            items=await call('inspect',dict(include_geometry=False))
            iid=items['instances'][0]['instance_id']
            await call('move',dict(instance_id=iid,position=[0,-4.5,0],anchor='bottom_center'))
            await call('rotate',dict(instance_id=iid,yaw_deg=37,anchor='bottom_center'))
            wall=next(w for w in geo['walls'] if w['length']>8)
            await call('batch',dict(operations=[
                dict(op='place',instance_id='audit_chair',name='Hingan Chair',position=[0,-2,0],yaw_deg=0),
                dict(op='face',instance_id='audit_chair',target_id=iid),
                dict(op='place_on',instance_id='audit_tea',name='Oriental Tea Set',target_id=iid,offset_xy=[0,0],gap_m=0,yaw_deg=0),
                dict(op='place_along_wall',instance_id='audit_cabinet',name='Hingan Sideboard',wall_id=wall['wall_id'],along_m=wall['length']/2,gap_m=0,facing='inward',z=0)
            ],strict=False,label='interior audit helpers'))
            snap=await call('snapshot',dict(label='audit baseline'))
            await call('remove',dict(instance_id='audit_chair'))
            await call('undo');await call('redo');await call('restore',dict(snapshot_id=snap['snapshot_id']))
            for level in ('ground','upper'):
                await call('set_fixtures',dict(wall='Pure White Interior Wall',floor='Light Wood Flooring',light='Flat Ceiling Lamp',level=level))
            await call('render',dict(view='overview',width=320,height=240,labels=True,lighting='off'))
            await call('render',dict(view='up_overview',width=320,height=240,labels=False,lighting='day',diagnostics=True))
            ex=await call('export_json',dict(name='audit-export'))
            if ex and ex.get('layout'):
                p=Path(ex['layout']['path']);raw=p.read_bytes();d=json.loads(raw)
                assert hashlib.sha256(raw).hexdigest()==ex['layout']['sha256']
                district=next(x['name'] for x in d['interiorFixture'] if x['type']=='District')
                assert district==style
                assert len(d['interiorFurniture'])==4
                record['export_readback']=dict(path=str(p),district=district,items=len(d['interiorFurniture']),bom_utf16le=raw.startswith(b'\xff\xfe'),sha256=ex['layout']['sha256'])
            final=await call('inspect',dict(instance_ids=[iid,'audit_chair','audit_tea','audit_cabinet'],include_geometry=True))
            assert len(final['instances'])==4
            record['final_readback']=dict(count=len(final['instances']),floor_polygon=final['floor_polygon'],walls=final['walls'],stair_footprints=final['stair_footprints'])
    (OUT/f'{style}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(style,[(c['tool'],c['is_error']) for c in record['calls'] if c['is_error']],flush=True)
    return record

async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    for style in STYLES:
        try:await audit_style(style,stamp)
        except Exception:
            (OUT/f'{style}-fatal.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
    # Aggregate saved files, never rely on mental counts.
    rows=[json.loads((OUT/f'{s}.json').read_text(encoding='utf-8')) for s in STYLES]
    assert len(rows)==7
    summary=[]
    for r in rows:
        called={c['tool'] for c in r['calls']};assert set(r['registered_tools'])<=called
        summary.append(dict(style=r['style'],session=r['session'],registered_tool_count=len(r['registered_tools']),call_count=len(r['calls']),errors=[dict(tool=c['tool'],texts=c.get('texts'),exception=c.get('exception')) for c in r['calls'] if c['is_error']],export=r.get('export_readback')))
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':asyncio.run(main())
