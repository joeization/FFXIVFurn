"""Search the 8 rotation/reflection matrices (dihedral D4) for each stair, scoring only INDEPENDENT physical constraints:
  - the whole stair stays inside the house rectangle (walls at x +-12, y +-8; frame +-12.1/8.1)
  - up stair: bottom ring stands on the ground floor mesh, top ring (z>7) on the upper floor mesh
  - down stair: the part above head height under the ground floor (z in -2.2..-0.1) lies in the floor opening (notch)
  - stair footprint overlaps the railing footprint that surrounds its opening (railing transforms have scale +1, so they are unambiguous)
The decoded translation is kept; only the 2x2 xy matrix is searched. Prints a ranked table; nothing is written.
"""
from pathlib import Path
import itertools, json, math, sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from shapely.geometry import Polygon, Point, box, MultiPoint
from shapely.ops import unary_union
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles

recs = json.loads((ROOT / 'outputs/house-layouts/native-bounds.json').read_text(encoding='utf-8'))['records']
def rec(suffix): return next(r for r in recs if r['source'].replace(chr(92), '/').endswith('InteriorStyles/' + suffix))
def mesh(suffix): v, t = read_static_mesh_triangles(rec(suffix)); return np.asarray(v), t
def floor_poly(suffix):
    v, t = mesh(suffix); return unary_union([p for tri in t if (p := Polygon([(v[i][0], v[i][1]) for i in tri])).area > 1e-8]).buffer(0.002).buffer(-0.002)

ground = floor_poly('SizeCommon/Medium/GroundFloor.uexp'); upper = floor_poly('SizeCommon/Medium/UpperFloor.uexp')
house = box(-12.1, -8.1, 12.1, 8.1); notch = box(-12, 2, -4, 8)
A = json.loads((ROOT / 'outputs/house-layouts/medium-stair-transforms.json').read_text(encoding='utf-8'))['actors']
sv, _ = mesh('Shirogane/Stair/Stair1.uexp')
MATS = {}
for k in range(4):
    c, s = round(math.cos(math.radians(90 * k))), round(math.sin(math.radians(90 * k)))
    R = np.array([[c, -s], [s, c]], float); MATS[f'rot{90*k}'] = R; MATS[f'rot{90*k}+mirrorX(before)'] = R @ np.diag([-1, 1])

def world(M, a):
    xy = sv[:, :2] @ M.T; tx, ty, tz = a['translation_m']; return np.column_stack([xy[:, 0] + tx, xy[:, 1] + ty, sv[:, 2] + tz])

def frac(poly, pts, buf=0.4): return float(np.mean([poly.buffer(buf).contains(Point(p[0], p[1])) for p in pts])) if len(pts) else float('nan')

rail_mesh = {n: mesh('Shirogane/Railing/' + n + '.uexp')[0] for n in ('Railing1', 'Railing3')}
def rail_hull(name, rm):
    a = A[name]; yaw = math.radians(a['yaw_degrees']); c, s = math.cos(yaw), math.sin(yaw); tx, ty, tz = a['translation_m']; v = rail_mesh[rm]
    return MultiPoint([(c * x - s * y + tx, s * x + c * y + ty) for x, y, _ in v]).convex_hull

for stair, rname in (('Stairs', 'Railing'), ('Stairs2_9', 'Railing2_2')):
    print(f'\n== {stair}  (decoded: yaw {A[stair]["yaw_degrees"]}, scale.x {A[stair]["scale"][0]}, T {A[stair]["translation_m"]})')
    rows = []
    for name, M in MATS.items():
        w = world(M, A[stair]); inside = frac(house, w, 0.05)
        if stair == 'Stairs':
            a1 = frac(ground, w[w[:, 2] < 0.4]); a2 = frac(upper, w[w[:, 2] > 6.8]); extra = f'bottom-on-ground {a1:.2f} top-on-upper {a2:.2f}'; key = (inside, a1 + a2)
        else:
            mid = w[(w[:, 2] > -2.2) & (w[:, 2] < -0.1)]; ring = w[w[:, 2] > -0.3]
            a1 = frac(notch, mid, 0.3); a2 = frac(ground, ring); extra = f'head-room-part-in-opening {a1:.2f} ground-ring-on-floor {a2:.2f}'; key = (inside, a1 + a2)
        hull = MultiPoint([(p[0], p[1]) for p in w]).convex_hull
        rail = max(hull.intersection(rail_hull(rname, rm)).area / rail_hull(rname, rm).area for rm in rail_mesh)
        rows.append((key[0] + 0.0001 * key[1], name, inside, extra, rail, np.round(w[:, 0].min(), 2), np.round(w[:, 0].max(), 2), np.round(w[:, 1].min(), 2), np.round(w[:, 1].max(), 2)))
    for r in sorted(rows, key=lambda r: -(r[2] * 10 + float(r[3].split()[-1]) + float(r[3].split()[1] if False else 0) + r[4])):
        print(f'  {r[1]:22} inside-house {r[2]:.3f} | {r[3]:52} | railing-overlap {r[4]:.2f} | x {r[5]}..{r[6]} y {r[7]}..{r[8]}')
