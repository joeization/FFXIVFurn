"""Render smoke test: new (non-57) DB furniture + DB fixtures in every house size. Test artifacts only; not app-verified for Small/Apartment seeds."""
from pathlib import Path
from contextlib import closing
import json, sqlite3, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.layout import build_layout, apply_fixtures
from ffxiv_furniture.rendering.pipeline import run_pipeline

OUT = ROOT / 'outputs/render-pipeline/multi-size'; OUT.mkdir(parents=True, exist_ok=True)
SEEDS = {'Medium': ROOT.parent.parent.parent / 'Downloads' / 'x'}  # placeholder replaced below
SEED_MEDIUM = Path('D:/Downloads/ReMakeplace-V7-57-1/MakePlace/Save/Save.json')
SEED_LARGE = Path('D:/Downloads/ReMakePlace-agent-inspection/schema-reference/example0.json')


def load(p):
    b = p.read_bytes(); return json.loads(b.decode('utf-16' if b[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')), b[:2] in (b'\xff\xfe', b'\xfe\xff')


def main():
    with FurnitureDB(ROOT / 'data/furniture.sqlite3') as db:
        c = db.connection
        old = {r[0] for r in sqlite3.connect('file:' + str(ROOT / 'data/furniture-test.sqlite3') + '?mode=ro', uri=True).execute('SELECT id FROM furniture')}
        pick = []
        for like in ('%Table', '%Sofa', '%Bookshelf', '%Lantern', '%Rug', '%Chair', '%Cupboard', '%Plant', '%Desk', '%Bed'):
            r = c.execute("SELECT f.id,f.name,f.length,f.width FROM furniture f JOIN asset_geometry g ON g.item_id=f.id WHERE f.scope='interior' AND f.name LIKE ? AND f.length BETWEEN 0.3 AND 4 AND f.width BETWEEN 0.3 AND 4 ORDER BY f.id", (like,)).fetchall()
            r = [x for x in r if x[0] not in old]
            if r: pick.append(r[len(r) // 2])
        print('picked', [(x[1], round(x[2], 1), round(x[3], 1)) for x in pick])
        mats = {cat: c.execute("SELECT item_id,name FROM house_materials WHERE category=? AND item_id IS NOT NULL ORDER BY item_id LIMIT 1 OFFSET 7", (cat,)).fetchone() for cat in ('Flooring', 'Wallpaper', 'CeilingLight')}
        print('fixtures', mats)
        res = {}
        for size, seedp in (('Medium', SEED_MEDIUM), ('Large', SEED_LARGE), ('Small', SEED_MEDIUM), ('Apartment', SEED_MEDIUM)):
            seed, u16 = load(seedp); seed['houseSize'] = size
            seed['interiorFurniture'] = []; seed['exteriorFurniture'] = []
            half = {'Medium': (9, 5), 'Large': (16, 8), 'Small': (3, 3), 'Apartment': (4, 6)}[size]
            pl = [{'item_id': it[0], 'location': [(-half[0] + i * (2 * half[0] / max(len(pick) - 1, 1))) * 100, ((-1) ** i) * half[1] * 100 * 0.6, 0], 'yaw_degrees': 90 * (i % 4)} for i, it in enumerate(pick)]
            if size == 'Small': pl = [dict(p, location=[(p['location'][0] / 100 / 9 * 4 + 2) * 100, p['location'][1] / 100 / 5 * 3 * 100, 0]) for p in pl]
            lay = build_layout(db, seed, pl)
            lay, w = apply_fixtures(db, lay, [{'item_id': mats['Flooring'][0], 'level': 'Ground Floor'}, {'item_id': mats['Wallpaper'][0], 'level': 'Ground Floor'}, {'item_id': mats['CeilingLight'][0], 'level': 'Ground Floor'}])
            lp = OUT / f'{size}.json'
            lp.write_bytes((json.dumps(lay, ensure_ascii=False, indent='\t') + '\n').encode('utf-16' if u16 else 'utf-8'))
            try:
                rd = OUT / f'render-{size}'
                if rd.exists(): res[size] = 'exists'; continue
                m = run_pipeline(lp, rd, db_path=ROOT / 'data/furniture.sqlite3', room_context=True, rough_room_finish=True, approximate_tint=True, size=(800, 560))
                res[size] = {'objects': len(m['objects']), 'views': len(m['views']), 'untextured_slots': m['untextured_slots'], 'material_slots': m['material_slots'], 'warnings': m['warnings'][:4], 'outside': m['outside_floor_projection'], 'secs': round(m['elapsed_seconds'], 1)}
            except Exception as e:
                res[size] = 'ERROR ' + repr(e)[:300]
        print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__': main()
