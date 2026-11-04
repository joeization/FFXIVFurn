"""Compare design-time footprints (place.py) with the renderer's real rotated geometry for the same layout."""
from pathlib import Path
import json, sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture.rendering.pipeline import quaternion_matrix

d = Path(sys.argv[1])
rep = json.loads((d / 'design-report.json').read_text(encoding='utf-8'))
b = (d / 'layout.json').read_bytes(); lay = json.loads(b.decode('utf-16' if b[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8'))
import sqlite3
c = sqlite3.connect('file:' + str(ROOT / 'data/furniture.sqlite3') + '?mode=ro', uri=True)
bad = 0
for i, (p, it) in enumerate(zip(rep['placements'], lay['interiorFurniture']), 1):
    lo_hi = c.execute('SELECT min_x,min_y,min_z,max_x,max_y,max_z FROM asset_geometry WHERE item_id=?', (it['itemId'],)).fetchone()
    lo, hi = np.array(lo_hi[:3]), np.array(lo_hi[3:])
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    R = quaternion_matrix(it['transform']['rotation']); pos = np.array(it['transform']['location']) / lay['interiorScale']
    w = corners @ R.T + pos
    real = (w[:, 0].min(), w[:, 1].min(), w[:, 0].max(), w[:, 1].max())
    mine = p['footprint_m']
    err = max(abs(a - b2) for a, b2 in zip(real, mine))
    if err > 0.02 or p['layer'] in ('wall',):
        bad += err > 0.02
        print(i, p['name'][:28].ljust(28), p['role'].ljust(9), 'yaw', p['yaw_degrees'], 'err_m', round(err, 2), 'real', [round(v, 2) for v in real], 'mine', mine, 'z', p['location_m'][2])
print('footprint mismatches >2cm:', bad, 'of', len(rep['placements']))
