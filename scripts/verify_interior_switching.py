"""End-to-end native MCP switching, persistence and staircase preview proof."""
import asyncio,datetime,hashlib,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.audit_mcp_interiors import unpack
from ffxiv_furniture.interiors import STYLES,InteriorProfile
from shapely.geometry import Polygon
OUT=ROOT/'outputs/mcp-interior-implementation'

async def connect(name,work):
    env=dict(os.environ,DECO_SESSION=name,DECO_STYLE='Shirogane',DECO_FROM_LAYOUT='0')
    params=StdioServerParameters(command=sys.executable,args=['-m','ffxiv_furniture.deco.server'],cwd=str(ROOT),env=env)
    async with stdio_client(params) as (r,w):
        async with ClientSession(r,w) as s:
            await s.initialize();return await work(s)

async def main():
    OUT.mkdir(parents=True,exist_ok=True);name='verify-interiors-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    log=[];views=[];evidence=[]
    async def work(s):
        async def call(tool,args=None):
            res=await s.call_tool(tool,args or {});obj,raw=unpack(res);log.append(dict(tool=tool,args=args or {},**raw))
            assert not res.isError,(tool,raw);return obj
        choices=await call('list_interiors');assert {c['style'] for c in choices['interiors']}==set(STYLES)
        await call('render',dict(view='overview',width=320,height=240,lighting='off')) # empty houses must work
        await call('place',dict(name='Hingan Chair',position=[0,-5,0],yaw_deg=37))
        before=(await call('inspect'))['instances'];snap=await call('snapshot',dict(label='original Shirogane'))
        for style in STYLES:
            await call('set_interior',dict(style=style))
            status=await call('status');assert status['style']==style
            ground=await call('inspect',dict(include_geometry=True,level='ground'));upper=await call('inspect',dict(include_geometry=True,level='upper'))
            assert ground['instances']==before;assert upper['style']==style
            cam=dict(position=[16,-13,20],target=[0,3,2],fov=65,cutaway=True,cut_stairs_z=20,hide_above_z=20)
            top=await call('render',dict(view=cam,width=640,height=400,lighting='off',diagnostics=True))
            close=await call('render',dict(view=dict(position=[0,-4,6],target=[8,4,3],fov=70,cutaway=True,cut_stairs_z=20,hide_above_z=20),width=640,height=400,lighting='off'))
            assert top['profile']['style']==style;assert close['profile']['style']==style
            entry=await call('render',dict(view='north_wall',width=640,height=400,lighting='off'))
            views.append(dict(style=style,overview=top['image'],stairs=close['image'],entry=entry['image']))
            ex=await call('export_json',dict(name='preview-'+style));raw=Path(ex['layout']['path']).read_bytes();lay=json.loads(raw)
            assert hashlib.sha256(raw).hexdigest()==ex['layout']['sha256'];assert next(x['name'] for x in lay['interiorFixture'] if x['type']=='District')==style
            # Read actual rendered source and transform, not just tool metadata.
            m=json.loads(Path(top['artifacts']['manifest']).read_text());objs={v['instance_id']:v for v in m['objects'].values()};p=InteriorProfile(style)
            assert Path(objs['floor']['source'])==p.paths['ground']['floor']
            assert objs['stair-up']['decoded_actor_transform']==p.actors['Stairs']
            # Ground and upper MCP polygons are rounded to mm, so allow tiny boundary rounding only.
            differences={level:Polygon(info['floor_polygon']).symmetric_difference(p.polygon(level)).area for level,info in [('ground',ground),('upper',upper)]}
            assert all(a<.05 for a in differences.values()),differences
            evidence.append(dict(style=style,export=ex['layout'],polygon_rounding_difference_m2=differences,stair_up=p.actors['Stairs'],stair_down=p.actors['Stairs2_9']))
        # Current style=DarkMinimalist; undo should recover Minimalist.
        assert (await call('undo'))['style']=='Minimalist'
        assert (await call('redo'))['style']=='DarkMinimalist'
        assert (await call('restore',dict(snapshot_id=snap['snapshot_id'])))['style']=='Shirogane'
        assert (await call('inspect'))['instances']==before
        await call('set_interior',dict(style='DarkMinimalist'))
        return before
    before=await connect(name,work)
    async def restarted(s):
        for tool in ('status','inspect'):
            res=await s.call_tool(tool,{});obj,raw=unpack(res);log.append(dict(tool=tool,restarted=True,**raw));assert not res.isError
            assert obj['style']=='DarkMinimalist',obj
            if tool=='inspect':assert obj['instances']==before
    await connect(name,restarted)
    # Contact sheet from actual MCP PNG outputs, not synthesized geometry.
    sheet=Image.new('RGB',(1280,430*len(views)),'#182029');d=ImageDraw.Draw(sheet)
    for i,row in enumerate(views):
        d.text((12,i*430+8),row['style']+' | full native stairs (not sectioned at 3m)',fill='white')
        for j,key in enumerate(('overview','stairs')):
            with Image.open(row[key]) as im:sheet.paste(im.convert('RGB'),(j*640,i*430+30))
    sheet.save(OUT/'interior-stair-contact.png')
    room_sheet=Image.new('RGB',(1280,430*4),'#182029');rd=ImageDraw.Draw(room_sheet)
    for i,row in enumerate(views):
        x,y=(i%2)*640,(i//2)*430
        rd.text((x+12,y+8),row['style']+' | enclosed north wall / stairs',fill='white')
        with Image.open(row['entry']) as im:room_sheet.paste(im.convert('RGB'),(x,y+30))
    room_sheet.save(OUT/'interior-room-contact.png')
    comparison=Image.new('RGB',(1280,860),'#182029');cd=ImageDraw.Draw(comparison)
    for i,row in enumerate([r for r in views if r['style'] in ('Shirogane','Minimalist')]):
        cd.text((12,i*430+8),row['style']+' | full stairs / detail',fill='white')
        for j,key in enumerate(('overview','stairs')):
            with Image.open(row[key]) as im:comparison.paste(im.convert('RGB'),(j*640,i*430+30))
    comparison.save(OUT/'shirogane-minimalist-stairs.png')
    report=dict(session=name,call_count=len(log),styles=len(views),views=views,evidence=evidence,persistence_restart=True,undo_redo_snapshot_verified=True,furniture_preserved=True,app_verified=False,calls=log)
    (OUT/'switch-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(session=name,call_count=len(log),styles=len(views),contact=str(OUT/'interior-stair-contact.png'),restart=True),indent=2))
if __name__=='__main__':asyncio.run(main())
