"""Estimate the model-local FRONT axis from seating geometry (backrest = the high-mass side) over the whole chair category."""
from pathlib import Path
from contextlib import closing
import collections, json, sqlite3, sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles

with closing(sqlite3.connect('file:' + str(ROOT / 'data/furniture.sqlite3') + '?mode=ro', uri=True)) as c:
    rows = c.execute("SELECT g.item_id,f.name,g.evidence,f.length,f.width,f.height FROM asset_geometry g JOIN furniture f ON f.id=g.item_id JOIN candidate_assets a ON a.item_id=f.id "
                     "WHERE a.source_category='Furniture/Chair' AND a.scope='interior' AND f.height>0.5").fetchall()
votes = collections.Counter(); per = {}
for iid, name, ev, L, W, H in rows:
    try:
        v, _ = read_static_mesh_triangles(json.loads(ev)); v = np.asarray(v)
    except Exception:
        continue
    z = v[:, 2]; zmax = z.max(); high = v[z > 0.65 * zmax]; low = v[(z > 0.1 * zmax) & (z < 0.5 * zmax)]
    if len(high) < 20 or len(low) < 20: continue
    # back is where the high mass sits relative to the low (seat) mass, per axis
    dy = high[:, 1].mean() - low[:, 1].mean(); dx = high[:, 0].mean() - low[:, 0].mean()
    if abs(dy) < 0.08 and abs(dx) < 0.08: continue
    ax = 'y' if abs(dy) >= abs(dx) else 'x'; d = dy if ax == 'y' else dx
    votes[(ax, '+' if d > 0 else '-')] += 1; per[name] = (ax, round(float(d), 2))
print('chairs measured', sum(votes.values()), 'of', len(rows)); print('BACKREST side (axis, sign):', dict(votes))
print(list(per.items())[:12])
