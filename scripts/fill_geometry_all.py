"""Fill model-local geometry for every candidate asset in the REAL DB from extracted GameAssets (read-only source).

Reuses the verified read_static_mesh_bounds. Failures keep NULL and are recorded with the reason. Existing geometry rows are kept.
"""
from pathlib import Path
from contextlib import closing
import collections, datetime, hashlib, json, math, sqlite3, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture.geometry import read_static_mesh_bounds
DB = ROOT / 'data/furniture.sqlite3'
LEGACY = ROOT / 'data/gameassets-legacy'


def main():
    with closing(sqlite3.connect(DB)) as c:
        rows = c.execute('SELECT asset_key,item_id FROM candidate_assets WHERE asset_key NOT IN (SELECT asset_key FROM asset_geometry)').fetchall()
    ok = []; fail = collections.Counter(); failures = []
    for key, iid in rows:
        folder = LEGACY / key; main_name = key.rsplit('/', 1)[1]
        cand = folder / f'{main_name}.uexp'
        try:
            if not cand.exists():
                raise FileNotFoundError('main mesh uexp not found: ' + cand.name)
            r = read_static_mesh_bounds(cand); r.update(item_id=iid, asset_key=key); ok.append(r)
        except Exception as e:
            msg = type(e).__name__ + ': ' + str(e)[:90]; fail[msg] += 1; failures.append({'asset_key': key, 'item_id': iid, 'error': msg})
    print('ok', len(ok), 'failed', len(failures)); print(fail.most_common(8))
    for r in ok:
        dims = [r[k] for k in ('length_m', 'width_m', 'height_m')]
        assert all(math.isfinite(v) and v > 0 for v in dims), r['asset_key']
        assert hashlib.sha256(Path(r['source']).read_bytes()).hexdigest() == r['source_sha256']
    backup = ROOT / 'data/backups' / ('pre-geometry-all-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
    with closing(sqlite3.connect(DB)) as s, closing(sqlite3.connect(backup)) as d: s.backup(d)
    with closing(sqlite3.connect(DB)) as c:
        c.execute('PRAGMA foreign_keys=ON')
        with c:
            for r in ok:
                dims = [r[k] for k in ('length_m', 'width_m', 'height_m')]
                c.execute('UPDATE furniture SET length=?,width=?,height=? WHERE id=?', (*dims, r['item_id']))
                c.execute('UPDATE candidate_assets SET length=?,width=?,height=? WHERE asset_key=?', (*dims, r['asset_key']))
                v = (r['asset_key'], r['item_id'], *r['local_min_m'], *r['local_max_m'], *(x / 100 for x in r['origin_cm']), r['source'], r['source_sha256'], r['method'], json.dumps(r))
                c.execute('INSERT INTO asset_geometry VALUES(' + ','.join('?' * len(v)) + ')', v)
        assert not c.execute('PRAGMA foreign_key_check').fetchall() and c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        print('asset_geometry rows', c.execute('SELECT COUNT(*) FROM asset_geometry').fetchone()[0], 'furniture with dims', c.execute('SELECT COUNT(length) FROM furniture').fetchone()[0])
    out = ROOT / 'outputs/geometry/fill-all-result.json'
    out.write_text(json.dumps({'filled': len(ok), 'failed': failures, 'backup': str(backup), 'units': 'metres, model-local; runtime actor scale not measured'}, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__': main()
