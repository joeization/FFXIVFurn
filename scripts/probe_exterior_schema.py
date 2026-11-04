from pathlib import Path
import sys,struct,collections,sqlite3
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture.rendering.native import tables,Reader,names
for size in ('Small','Medium','Large'):
 p=ROOT/'data/house-legacy/MakePlace/Content/Maps'/('XIV'+size+'Exterior.umap');t=tables.map_tables(p);data=p.with_suffix('.uexp').read_bytes();nm=names(p)
 print('\nSIZE',size)
 byidx={r['index']:r for r in t['exports']};imports={r['index']:r for r in t['imports']}
 for e in t['exports']:
  if not e['class'].endswith(('.HouseFixture','.StaticMeshComponent','.StaticMeshActor')):continue
  b=data[e['serial_offset_in_uexp']:e['serial_offset_in_uexp']+e['serial_size']];r=Reader(b,nm);f,z=r.header()
  print(e['index'],e['name'],e['class'].split('.')[-1],'outer',byidx.get(e['outer'],{}).get('name'),'len',len(b),'fields',f,'zero',z,'headerend',r.pos,'hex',b[r.pos:].hex())
 if size=='Small':
  print('IMPORTS',[(r['index'],r['resolved']) for r in t['imports'] if r['class'] in ('StaticMesh','MaterialInstanceConstant')])
db=sqlite3.connect('file:'+str(ROOT/'data/furniture.sqlite3')+'?mode=ro',uri=True)
print('FIXTURE_SLOTS',db.execute('select category,slot,count(*) from house_materials group by category,slot').fetchall())
print('FENCE_NAMES',db.execute("select name,asset_key,slot from house_materials where category='Fence'").fetchall())
