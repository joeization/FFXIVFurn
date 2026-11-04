"""Independent orientation check of the decoded stair transforms using the UPPER FLOOR and BASEMENT floor meshes (not used when decoding).

The stair's top landing (z ~ +7) must meet solid upper floor; its bottom must stand on the ground floor. The basement stair's bottom (z ~ -7) must
meet the basement floor. Alternatives (other composition orders / mirrors) are scored the same way so a wrong transform shows up.
"""
from pathlib import Path
import json, math, sys, itertools
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles

recs = json.loads((ROOT / 'outputs/house-layouts/native-bounds.json').read_text(encoding='utf-8'))['records']
def rec(suffix): return next(r for r in recs if r['source'].replace(chr(92), '/').endswith('InteriorStyles/' + suffix))
def poly_of(suffix):
    v, t = read_static_mesh_triangles(rec(suffix)); return unary_union([p for tri in t if (p := Polygon([(v[i][0], v[i][1]) for i in tri])).area > 1e-8]).buffer(0.002).buffer(-0.002)

for name in ('SizeCommon/Medium/UpperFloor.uexp', 'SizeCommon/Medium/GroundFloor.uexp'):
    p = poly_of(name); print(name.split('/')[-1], 'bounds', [round(x, 2) for x in p.bounds], 'area', round(p.area, 1), 'bbox area', round((p.bounds[2]-p.bounds[0])*(p.bounds[3]-p.bounds[1]), 1))
print('basement candidates:', [r['source'].replace(chr(92), '/').split('InteriorStyles/')[-1] for r in recs if 'Basement' in r['source'] and 'Medium' in r['source']])
upper = poly_of('SizeCommon/Medium/UpperFloor.uexp'); ground = poly_of('SizeCommon/Medium/GroundFloor.uexp')
box = Polygon([(-12, -8), (12, -8), (12, 8), (-12, 8)])
print('upper floor MISSING region bounds', [round(x, 2) for x in box.difference(upper).bounds] if not box.difference(upper).is_empty else 'none', 'area', round(box.difference(upper).area, 1))
print('ground floor MISSING region bounds', [round(x, 2) for x in box.difference(ground).bounds], 'area', round(box.difference(ground).area, 1))

t = json.loads((ROOT / 'outputs/house-layouts/medium-stair-transforms.json').read_text(encoding='utf-8'))
v, tri = read_static_mesh_triangles(rec('Shirogane/Stair/Stair1.uexp')); v = np.asarray(v)
lo = v[v[:, 2] < 0.5]; hi = v[v[:, 2] > 7.5]
print('stair local: bottom centroid', lo[:, :2].mean(0).round(2), 'top centroid', hi[:, :2].mean(0).round(2), 'ascent dir (local)', (hi[:, :2].mean(0) - lo[:, :2].mean(0)).round(2))

def world(a, v, order, flip):
    sx, sy, sz = a['scale']; yaw = math.radians(a['yaw_degrees']); c, s = math.cos(yaw), math.sin(yaw); tx, ty, tz = a['translation_m']
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    if order == 'scale-rot-trans':     # UE FTransform
        x, y = x * sx, y * sy; X, Y = c * x - s * y, s * x + c * y
    else:                              # rotate first, then scale (WRONG for UE; tested as an alternative)
        X, Y = c * x - s * y, s * x + c * y; X, Y = X * sx, Y * sy
    if flip == 'mirror-x': X = -X
    if flip == 'mirror-y': Y = -Y
    if flip == 'mirror-x+tx': X = -X; tx = -tx
    return np.stack([X + tx, Y + ty, z + tz], 1)

def frac_on(poly, pts):
    return float(np.mean([poly.buffer(0.35).contains(Point(p[0], p[1])) for p in pts]))

up = t['actors']['Stairs']; dn = t['actors']['Stairs2_9']
print('\n   transform variant            | up-stair TOP on upper floor | up-stair BOTTOM on ground floor | down-stair TOP at ground level on ground floor')
for order, flip in itertools.product(('scale-rot-trans', 'rot-scale-trans'), ('none', 'mirror-x', 'mirror-y', 'mirror-x+tx')):
    w = world(up, v, order, flip); top = w[w[:, 2] > 6.8]; bot = w[w[:, 2] < 0.4]
    wd = world(dn, v, order, flip); dtop = wd[(wd[:, 2] > -0.4) & (wd[:, 2] < 0.4)]
    print(f'   {order:16} {flip:12} |        {frac_on(upper, top):5.2f}            |          {frac_on(ground, bot):5.2f}            |        {frac_on(ground, dtop) if len(dtop) else float("nan"):5.2f}')
w = world(up, v, 'scale-rot-trans', 'none'); print('\nup stair (decoded) ascent world dir:', (w[w[:, 2] > 7.5][:, :2].mean(0) - w[w[:, 2] < 0.5][:, :2].mean(0)).round(2), 'bottom at', w[w[:, 2] < 0.5][:, :2].mean(0).round(2), 'top at', w[w[:, 2] > 7.5][:, :2].mean(0).round(2))
wd = world(dn, v, 'scale-rot-trans', 'none'); print('down stair (decoded) descent world dir:', (wd[wd[:, 2] < -6.5][:, :2].mean(0) - wd[(wd[:, 2] > -0.4) & (wd[:, 2] < 0.4)][:, :2].mean(0)).round(2))
