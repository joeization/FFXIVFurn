"""Populate only support_surfaces from every geometry-backed furniture mesh.

Run with the project's Python. Backs up the database before any writes, prints
batch progress, isolates item failures, then reads back persisted statistics.
"""
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from ffxiv_furniture.design.surfaces import measure_support_surfaces

COLUMNS = ('z_local', 'min_x', 'min_y', 'max_x', 'max_y', 'area_m2',
           'clearance_above_m', 'is_top')
SCHEMA = '''CREATE TABLE IF NOT EXISTS support_surfaces(
    item_id INTEGER, surface_idx INTEGER, z_local REAL,
    min_x REAL, min_y REAL, max_x REAL, max_y REAL, area_m2 REAL,
    clearance_above_m REAL, is_top INTEGER,
    PRIMARY KEY(item_id, surface_idx))'''


def measure_item(row):
    item_id, name, evidence = row
    try:
        vertices, faces = read_static_mesh_triangles(json.loads(evidence))
        return item_id, name, measure_support_surfaces(vertices, faces), None
    except Exception as exc:
        return item_id, name, [], f'{type(exc).__name__}: {exc}'


def fingerprint_other_tables(connection):
    result = {}
    for name, sql in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name!='support_surfaces' ORDER BY name").fetchall():
        # vec0 is backed by ordinary shadow tables, fingerprinted below. Its
        # virtual SELECT requires the optional extension and is not needed to
        # verify persistence (the exact virtual schema is still fingerprinted).
        if sql and 'CREATE VIRTUAL TABLE' in sql.upper():
            result[name] = ('virtual_schema', hashlib.sha256(sql.encode()).hexdigest())
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        digest = hashlib.sha256(str(sql).encode())
        count = 0
        for row in connection.execute(f'SELECT * FROM {quoted}'):
            digest.update(repr(row).encode('utf-8'))
            digest.update(b'\n')
            count += 1
        result[name] = (count, digest.hexdigest())
    return result


def validate(db, backup, expected_items, failures):
    with closing(sqlite3.connect(db)) as c, closing(sqlite3.connect(backup)) as b:
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert fingerprint_other_tables(c) == fingerprint_other_tables(b), 'An unrelated table changed'
        rows = c.execute('SELECT item_id,COUNT(*) FROM support_surfaces GROUP BY item_id').fetchall()
        report = dict(items_processed=expected_items, items_with_surfaces=len(rows),
                      items_with_multiple_surfaces=sum(n >= 2 for _, n in rows),
                      total_surfaces=sum(n for _, n in rows), failures=failures,
                      backup=str(backup), other_tables_unchanged=True, integrity_check='ok')
        print('COUNTS', json.dumps(report), flush=True)
        for term in ('Bookshelf', 'Bookcase', 'Shelf', 'Table'):
            items = c.execute('SELECT DISTINCT f.id,f.name FROM furniture f JOIN asset_geometry g ON g.item_id=f.id WHERE f.name LIKE ? ORDER BY f.name,f.id LIMIT 5', ('%' + term + '%',)).fetchall()
            for item_id, name in items:
                surfaces = c.execute('SELECT surface_idx,' + ','.join(COLUMNS) + ' FROM support_surfaces WHERE item_id=? ORDER BY surface_idx', (item_id,)).fetchall()
                print('SPOT', json.dumps(dict(term=term, item_id=item_id, name=name,
                      surfaces=[dict(zip(('surface_idx',) + COLUMNS, s)) for s in surfaces])), flush=True)
        # Explicitly show the strongest stacked-bookshelf evidence, not only alphabetical samples.
        example = c.execute("SELECT f.id,f.name,COUNT(*) n FROM support_surfaces s JOIN furniture f ON f.id=s.item_id WHERE f.name LIKE '%bookshelf%' OR f.name LIKE '%bookcase%' GROUP BY f.id ORDER BY n DESC,f.id LIMIT 1").fetchone()
        if example:
            print('STACKED_BOOKSHELF', json.dumps(dict(item_id=example[0], name=example[1],
                  count=example[2], planes=c.execute('SELECT z_local,area_m2,clearance_above_m FROM support_surfaces WHERE item_id=? ORDER BY surface_idx', (example[0],)).fetchall())), flush=True)
        assert not c.execute('SELECT 1 FROM support_surfaces WHERE area_m2<0.019999999 OR clearance_above_m<0.119999999 LIMIT 1').fetchone()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data/furniture.sqlite3')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--batch-size', type=int, default=50)
    args = parser.parse_args()
    if args.workers < 1 or args.batch_size < 1:
        parser.error('workers and batch-size must be positive')
    db = args.db.resolve()
    wal = Path(str(db) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError('Nonempty SQLite WAL: close database writers before copying backup')
    backup = db.parent / 'backups' / ('pre-support-surfaces-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db, backup)
    print('BACKUP', backup, flush=True)
    with closing(sqlite3.connect('file:' + db.as_posix() + '?mode=ro', uri=True)) as c:
        rows = c.execute('''SELECT f.id,f.name,g.evidence FROM furniture f
            JOIN asset_geometry g ON g.item_id=f.id
            WHERE EXISTS(SELECT 1 FROM candidate_assets a WHERE a.item_id=f.id)
            ORDER BY f.id,g.asset_key''').fetchall()
        # A catalog item has one selected geometry record; never silently choose
        # one asset if a later database introduces multiple records per item.
        if len({r[0] for r in rows}) != len(rows):
            raise ValueError('Multiple geometry assets per item require explicit mesh aggregation')
        geometry_count = c.execute('SELECT COUNT(DISTINCT item_id) FROM asset_geometry WHERE item_id IN (SELECT id FROM furniture)').fetchone()[0]
        assert geometry_count == len(rows), 'Geometry items missing candidate_assets'
    out, failures = [], []
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(rows), args.batch_size):
            batch = rows[offset:offset + args.batch_size]
            for item_id, name, surfaces, error in pool.map(measure_item, batch):
                if error:
                    failures.append(dict(item_id=item_id, name=name, error=error))
                for idx, surface in enumerate(surfaces):
                    out.append((item_id, idx, *(surface[k] for k in COLUMNS)))
            print(f'PROGRESS {offset + len(batch)}/{len(rows)} items; {len(out)} surfaces; '
                  f'{len(failures)} failures; {time.monotonic() - start:.1f}s', flush=True)
    with closing(sqlite3.connect(db)) as c:
        with c:
            c.execute(SCHEMA)
            c.execute('DELETE FROM support_surfaces')
            c.executemany('INSERT INTO support_surfaces VALUES(?,?,?,?,?,?,?,?,?,?)', out)
    validate(db, backup, len(rows), failures)


if __name__ == '__main__':
    main()
