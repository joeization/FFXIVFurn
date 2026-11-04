"""Back up and fill model-local geometry in the isolated test catalog only."""
import argparse
from contextlib import closing
import datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.geometry import read_static_mesh_bounds


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=str(ROOT/'data/furniture-test.sqlite3'))
    p.add_argument('--legacy-dir',default=str(ROOT/'data/geometry-legacy'))
    p.add_argument('--report',default=str(ROOT/'outputs/geometry/fill-result.json'))
    a=p.parse_args();target=Path(a.db).resolve()
    if not target.exists():raise ValueError('Existing test DB required')
    if target== (ROOT/'data/furniture.sqlite3').resolve():raise ValueError('Refuse production DB')
    records=[];failures=[]
    with closing(sqlite3.connect(target)) as c:
        rows=c.execute('SELECT item_id,asset_key FROM candidate_assets WHERE item_id IS NOT NULL').fetchall()
    for iid,key in rows:
        path=Path(a.legacy_dir)/(key+'/'+key.rsplit('/',1)[1]+'.uexp')
        try:
            record=read_static_mesh_bounds(path);record.update(item_id=iid,asset_key=key);records.append(record)
        except (ValueError,OSError) as exc:failures.append({'item_id':iid,'asset_key':key,'error':str(exc)})
    if not records:raise ValueError('No independently verified bounds; nothing to fill')
    backup=target.parent/'backups'/('test-pre-geometry-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
    backup.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(target)) as src,closing(sqlite3.connect(backup)) as dst:src.backup(dst)
    with FurnitureDB(target) as db:
        c=db.connection
        with c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('''CREATE TABLE IF NOT EXISTS asset_geometry(
                asset_key TEXT PRIMARY KEY REFERENCES candidate_assets(asset_key),
                item_id INTEGER REFERENCES furniture(id),
                min_x REAL NOT NULL,min_y REAL NOT NULL,min_z REAL NOT NULL,
                max_x REAL NOT NULL,max_y REAL NOT NULL,max_z REAL NOT NULL,
                center_x REAL NOT NULL,center_y REAL NOT NULL,center_z REAL NOT NULL,
                source TEXT NOT NULL,source_sha256 TEXT NOT NULL,method TEXT NOT NULL,evidence TEXT NOT NULL)''')
            columns={r['name'] for r in c.execute('PRAGMA table_info(candidate_assets)')}
            for name in ('length','width','height'):
                if name not in columns:c.execute(f'ALTER TABLE candidate_assets ADD COLUMN {name} REAL')
            for r in records:
                if hashlib.sha256(Path(r['source']).read_bytes()).hexdigest()!=r['source_sha256']:
                    raise ValueError('Source changed during fill')
                dimensions=[r[k] for k in ('length_m','width_m','height_m')]
                if not all(math.isfinite(v) and v>0 for v in dimensions):raise ValueError('Invalid dimensions')
                c.execute('UPDATE furniture SET length=?,width=?,height=? WHERE id=?',(*dimensions,r['item_id']))
                c.execute('UPDATE candidate_assets SET length=?,width=?,height=? WHERE asset_key=?',(*dimensions,r['asset_key']))
                values=(r['asset_key'],r['item_id'],*r['local_min_m'],*r['local_max_m'],
                        *(v/100 for v in r['origin_cm']),r['source'],r['source_sha256'],r['method'],json.dumps(r))
                c.execute('INSERT OR REPLACE INTO asset_geometry VALUES('+','.join('?' for _ in values)+')',values)
            c.execute('''CREATE VIEW IF NOT EXISTS furniture_bounds AS
                SELECT f.*,g.min_x,g.min_y,g.min_z,g.max_x,g.max_y,g.max_z,
                g.center_x,g.center_y,g.center_z,f.length*f.width*f.height AS bounding_box_volume_m3
                FROM furniture f JOIN asset_geometry g ON g.item_id=f.id''')
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        for r in records:
            row=db.get_furniture(r['item_id'])
            assert [row[k] for k in ('length','width','height')]==[r[k] for k in ('length_m','width_m','height_m')]
    result={'database':str(target),'backup':str(backup),'filled_count':len(records),'failed':failures,
            'records':records,'overlap_policy':'intentional intersections allowed; no global rejection',
            'scope':'model-local mesh geometry, not runtime actor transforms or exact collision',
            'axes':'length=X,width=Y,height=Z; metres; preserved origin-relative min/max'}
    Path(a.report).parent.mkdir(parents=True,exist_ok=True)
    Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
