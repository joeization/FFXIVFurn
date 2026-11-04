import sys, json, sqlite3, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffxiv_furniture.rendering import native
from ffxiv_furniture.rendering.assets import mesh_materials, find_asset
db = sqlite3.connect((ROOT/'data/furniture.sqlite3').as_uri()+'?mode=ro', uri=True)
rows = db.execute("select g.item_id,f.name,g.evidence from asset_geometry g join furniture f on f.id=g.item_id where f.scope='interior'").fetchall()
bad = collections.defaultdict(list); reasons = collections.Counter(); tot = slots = 0; parents = collections.Counter()
for iid, name, ev in rows:
    try:
        src = Path(json.loads(ev)['source']); mats = mesh_materials(src.with_suffix('.uasset')); content = next(q for q in src.parents if q.name == 'Content')
    except Exception as e:
        bad[iid].append(('mesh', type(e).__name__ + str(e)[:50])); reasons['mesh:' + type(e).__name__] += 1; continue
    tot += 1
    for k, m in enumerate(mats):
        slots += 1
        try:
            mi = native.material_instance(find_asset(content, m['resolved'].split('.')[0])); parents[mi['parent'].split('.')[-1]] += 1
            b = mi['parameters'].get('Base')
            if not b or b['kind'] != 'texture': raise ValueError('no Base texture param')
            native.decode_texture(find_asset(content, b['value'].split('.')[0]))
        except Exception as e:
            r = type(e).__name__ + ': ' + str(e)[:60]; reasons[r] += 1; bad[iid].append((k, r))
print('items', tot, 'slots', slots, 'items with a failing slot', len(bad), 'failing slots', sum(len(v) for v in bad.values()))
for r, n in reasons.most_common(12): print(n, r)
names = {i: n for i, n, _ in rows}
output=ROOT/'outputs/render-pipeline/missing-textures.json'
output.parent.mkdir(parents=True,exist_ok=True)
with output.open('w',encoding='utf-8') as stream:
    json.dump({str(i): dict(name=names.get(i), fails=v) for i, v in bad.items()}, stream, ensure_ascii=False, indent=1)
db.close()
for i, v in list(bad.items())[:15]: print(i, names.get(i), v[:2])
