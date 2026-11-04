"""Measure placement metadata for every geometry-backed furniture item and store it in `placement_info` (real DB, backed up first).

All values come from the extracted meshes + the source category; nothing is guessed silently:
- placement_type: wall | ceiling | rug | floor  (rules documented below; 'small' flag separate)
- front_deg: local direction (degrees CCW from +X) the item faces. Seating: measured from the backrest side of the mesh (confidence = offset in m);
  everything else: the +Y prior supported by 64/73 chairs and thin-axis posters (front_source says which).
- supports_top / top_z_local / top_area_fraction: flat usable top surface measured from the highest vertex plane.
- mount_bottom_z: where the underside of a wall item sits (wall art centred at 1.55 m, wall cabinets/shelves from 1.3 m, never below 0.05 m).
"""
from pathlib import Path
from contextlib import closing
import collections, datetime, json, math, sqlite3, sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from shapely.geometry import MultiPoint

DB = ROOT / 'data/furniture.sqlite3'
from ffxiv_furniture.placement import measure


def main():
    with closing(sqlite3.connect('file:' + str(DB) + '?mode=ro', uri=True)) as c:
        rows = c.execute('''SELECT f.id,f.name,a.source_category,g.evidence,f.length,f.width,f.height,g.min_z FROM furniture f
                            JOIN asset_geometry g ON g.item_id=f.id JOIN candidate_assets a ON a.item_id=f.id ORDER BY f.id''').fetchall()
    out = []; fails = []
    for r in rows:
        try: out.append(measure(r))
        except Exception as e: fails.append((r[0], r[1], repr(e)[:100]))
    backup = ROOT / 'data/backups' / ('pre-placement-info-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
    with closing(sqlite3.connect(DB)) as s, closing(sqlite3.connect(backup)) as d: s.backup(d)
    with closing(sqlite3.connect(DB)) as c:
        with c:
            c.execute('DROP TABLE IF EXISTS placement_info')
            c.execute('''CREATE TABLE placement_info(item_id INTEGER PRIMARY KEY REFERENCES furniture(id),placement_type TEXT NOT NULL CHECK(placement_type IN ('floor','wall','ceiling','rug')),
                small INTEGER NOT NULL,front_deg REAL NOT NULL,front_source TEXT NOT NULL,front_confidence REAL NOT NULL,supports_top INTEGER NOT NULL,
                top_z_local REAL NOT NULL,top_area_fraction REAL NOT NULL,mount_bottom_z REAL)''')
            c.executemany('INSERT INTO placement_info VALUES(?,?,?,?,?,?,?,?,?,?)', out)
            c.execute('INSERT OR REPLACE INTO build_metadata VALUES(?,?)', ('placement_info', 'measured from extracted meshes by scripts/fill_placement_info.py; front is a prior (+Y) except seating (measured)'))
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        print('rows', len(out), 'failures', len(fails), fails[:5])
        print(c.execute('SELECT placement_type,COUNT(*),SUM(small),SUM(supports_top) FROM placement_info GROUP BY 1').fetchall())
        print('front measured', c.execute("SELECT front_deg,COUNT(*) FROM placement_info WHERE front_source LIKE 'measured%' GROUP BY 1").fetchall())
        print('wall items without mount', c.execute("SELECT COUNT(*) FROM placement_info WHERE placement_type='wall' AND mount_bottom_z IS NULL").fetchone())
    print('backup', backup.name)


if __name__ == '__main__': main()
