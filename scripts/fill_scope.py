"""Back up catalogs, migrate scope schema, and fill only trusted candidate scope metadata."""
from contextlib import closing
import datetime
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.housing import HOUSING_LIMITS,validate_layout_budget,floor_access_policy


def main():
    reports=[]
    for filename in ['furniture.sqlite3','furniture-test.sqlite3']:
        target=ROOT/'data'/filename
        if not target.exists():continue
        backup=target.parent/'backups'/(target.stem+'-pre-scope-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
        backup.parent.mkdir(exist_ok=True)
        with closing(sqlite3.connect(target)) as c,closing(sqlite3.connect(backup)) as dst:c.backup(dst)
        with FurnitureDB(target) as db:
            c=db.connection
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            updated=0
            if 'candidate_assets' in tables:
                sources=c.execute('SELECT item_id,scope FROM candidate_assets WHERE item_id IS NOT NULL GROUP BY item_id,scope').fetchall()
                by_id={}
                for iid,scope in sources:
                    if scope not in ('interior','exterior'):raise ValueError('Invalid authoritative candidate scope')
                    if iid in by_id and by_id[iid]!=scope:raise ValueError(f'Conflicting source scopes for {iid}')
                    by_id[iid]=scope
                with c:
                    for iid,scope in by_id.items():
                        old=db.get_furniture(iid)
                        if old['scope'] not in (None,scope):raise ValueError('Existing scope disagrees with candidate metadata')
                        updated+=c.execute('UPDATE furniture SET scope=? WHERE id=?',(scope,iid)).rowcount
            if 'furniture_vectors' in tables:
                from ffxiv_furniture.semantic import load_sqlite_vec
                load_sqlite_vec(c)
            integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
            assert integrity=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
            reports.append({'database':str(target),'backup':str(backup),'filled':updated,'schema_version':c.execute('PRAGMA user_version').fetchone()[0],
                'scope_counts':dict(c.execute("SELECT COALESCE(scope,'unknown'),COUNT(*) FROM furniture GROUP BY scope").fetchall()),'integrity':integrity})
    layouts=[]
    with FurnitureDB(ROOT/'data/furniture-test.sqlite3') as db:
        for path in (ROOT/'outputs/ground-floor').glob('*.json'):
            value=json.loads(path.read_bytes())
            if not isinstance(value,dict) or 'interiorFurniture' not in value:continue
            budget=validate_layout_budget(value)
            for scope in ('interior','exterior'):
                for item in value.get(scope+'Furniture',[]):
                    furniture=db.get_furniture(item['itemId'])
                    if not furniture or furniture['scope']!=scope:raise ValueError(f'Wrong or unknown scope in {path}: {item["itemId"]}')
            layouts.append({'layout':str(path),'budget':budget})
    report={'databases':reports,'layouts_checked':layouts,'limits':HOUSING_LIMITS,
        'one_floor_example':floor_access_policy('Medium',['ground']),
        'rule':'Interior/exterior are incompatible. Unknown scope is excluded from export. Whole-house budgets include overlap, floating and concealment furniture.'}
    out=ROOT/'outputs/housing-constraints.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
