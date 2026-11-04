"""Decode the Medium house stair/railing actor transforms from XIVMediumHouse.uexp and derive footprints.

Format (verified on all four DistrictFixture exports, 253-254 bytes): an FTransform of 10 little-endian doubles starting at byte 35:
quaternion x,y,z,w @35,43,51,59 · translation x,y,z (cm) @67,75,83 · Scale3D x,y,z @91,99,107, repeated once more at +101
(a second identical copy). Cross-checks: unit quaternions; basement stair z = -700 cm = one 7 m storey; Stair1 is 8.6 m tall;
the basement stair footprint lands in the ground floor's missing notch; Scale3D.x = -1 (mirrored stairs).
Only Medium is decoded; other sizes have different export sizes and are NOT verified.
"""
from pathlib import Path
import json, math, struct, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
MAP = ROOT / 'data/house-legacy/MakePlace/Content/Maps/XIVMediumHouse.uexp'
TABLES = ROOT / 'outputs/house-layouts/native-map-tables.json'
OUT = ROOT / 'outputs/house-layouts/medium-stair-transforms.json'
ACTORS = {'Stairs': 'up (ground -> upper)', 'Stairs2_9': 'down (ground -> basement)', 'Railing': 'upper-floor railing at the stair arrival', 'Railing2_2': 'ground-floor railing around the basement opening'}
SLOTS = ['qx', 'qy', 'qz', 'qw', 'tx', 'ty', 'tz', 'sx', 'sy', 'sz']


def read_transform(b, base=35):
    v = dict(zip(SLOTS, struct.unpack_from('<10d', b, base)))
    dup = dict(zip(SLOTS, struct.unpack_from('<10d', b, base + 101)))
    return v, dup


def main():
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
    d = MAP.read_bytes()
    ex = {e['name']: e for e in json.loads(TABLES.read_text(encoding='utf-8'))['Medium']['exports']}
    actors = {}
    for name, role in ACTORS.items():
        e = ex[name]; b = d[e['serial_offset_in_uexp']:e['serial_offset_in_uexp'] + e['serial_size']]
        v, dup = read_transform(b)
        assert all(abs(v[k] - dup[k]) < 1e-5 for k in SLOTS), f'{name}: transform copies differ beyond rounding'
        norm = math.sqrt(sum(v[k] ** 2 for k in ('qx', 'qy', 'qz', 'qw'))); assert abs(norm - 1) < 1e-9, (name, norm)
        assert v['qx'] == 0 and v['qy'] == 0, 'rotation is not a pure yaw'
        yaw = math.degrees(2 * math.atan2(v['qz'], v['qw'])) % 360
        # Stored Scale3D.x is -1, but applying it (scale->rotate->translate) pushes both stairs through the walls and detaches the landings
        # (scripts/search_stair_matrix.py: best fit over the 8 rotation/reflection matrices is the PURE yaw rotation). Most likely the map references a
        # mirrored sibling of Stair1, so the -1 cancels the mirroring of the asset instead of mirroring the stair. We therefore render Stair1 with yaw only.
        is_stair = name.startswith('Stairs')
        actors[name] = {'role': role, 'translation_m': [v['tx'] / 100, v['ty'] / 100, v['tz'] / 100], 'yaw_degrees': round(yaw, 6), 'scale': [1.0, 1.0, 1.0] if is_stair else [v['sx'], v['sy'], v['sz']],
                        'scale_stored': [v['sx'], v['sy'], v['sz']], 'scale_applied': not is_stair,
                        'scale_note': 'stored Scale3D.x=-1 NOT applied for Stair1: applying it breaks wall/landing/railing constraints (see scripts/search_stair_matrix.py)' if is_stair else '',
                        'quaternion': [v['qx'], v['qy'], v['qz'], v['qw']], 'export_index': e['index'], 'uexp_offset': e['serial_offset_in_uexp'], 'raw_transform_doubles': v}
    # USER-OBSERVATION OVERRIDE (app screenshot + sketch): the decoded Stairs2_9 transform (-8,3,-7 yaw180) put the down flights along x. In the app the
    # down stair is the mirror counterpart of the up stair: flush in the back-right corner (+y wall, -x wall), flights running along y like the up stair.
    # Pure yaw 90 at (-9,4,-7) reproduces that (same orientation as Stairs, x -12.0..-4.9, y -0.9..8.0). This is chosen from images, not decoded from the map.
    a = actors['Stairs2_9']; a['decoded_translation_m'] = list(a['translation_m']); a['decoded_yaw_degrees'] = a['yaw_degrees']
    a['translation_m'] = [-9.0, 4.0, -7.0]; a['yaw_degrees'] = 90.0
    a['override_note'] = 'user app screenshot/sketch: down stair mirrors the up stair in the back corner; not decoded from the map'
    # footprints from the stair mesh (Stair1) under the decoded transforms
    rec = next(r for r in json.loads((ROOT / 'outputs/house-layouts/native-bounds.json').read_text(encoding='utf-8'))['records']
               if r['source'].replace(chr(92), '/').endswith('InteriorStyles/Shirogane/Stair/Stair1.uexp'))
    verts, tris = read_static_mesh_triangles(rec)

    def world_xy(actor):
        a = actors[actor]; sx, sy, _ = a['scale']; c, s = math.cos(math.radians(a['yaw_degrees'])), math.sin(math.radians(a['yaw_degrees']))
        tx, ty, tz = a['translation_m']
        out = []
        for x, y, z in verts:
            x, y = x * sx, y * sy                 # scale, then rotate, then translate (FTransform order)
            out.append((c * x - s * y + tx, s * x + c * y + ty, z + tz))
        return out
    foot = {}
    for name in ('Stairs', 'Stairs2_9'):
        w = world_xy(name)
        poly = unary_union([p for t in tris if (p := Polygon([(w[i][0], w[i][1]) for i in t])).area > 1e-8]).buffer(0.01).buffer(-0.01)
        zs = [p[2] for p in w]
        foot[name] = {'bounds_xy_m': [round(v, 3) for v in poly.bounds], 'z_range_m': [round(min(zs), 3), round(max(zs), 3)], 'area_m2': round(poly.area, 2), 'exterior': [[round(x, 3), round(y, 3)] for x, y in poly.convex_hull.exterior.coords]}
    # Keepouts per floor (design choice, documented): stair hull + 1.0 m approach clearance. Ground: the up stair body, and the part of the
    # down stair that stands at/above ground level (z > -0.3). Upper: where the up stair arrives. Basement: where the down stair ends.
    from shapely.geometry import MultiPoint
    def hull(name, zmin=-99, zmax=99):
        w = world_xy(name); pts = [(x, y) for x, y, z in w if zmin <= z <= zmax]
        return MultiPoint(pts).convex_hull
    CLEAR = 1.0
    keep = {'ground': [hull('Stairs'), hull('Stairs2_9', zmin=-0.3)], 'upper': [hull('Stairs')], 'basement': [hull('Stairs2_9', zmax=-5.0)]}
    keepouts = {fl: {'clearance_m': CLEAR, 'polygons': [[[round(x, 3), round(y, 3)] for x, y in g.buffer(CLEAR, join_style=2).exterior.coords] for g in gs]} for fl, gs in keep.items()}
    OUT.write_text(json.dumps({'source': str(MAP), 'mesh': 'Shirogane/Stair/Stair1', 'convention': 'FTransform order: scale -> rotate (yaw CCW about Z) -> translate; metres',
                               'actors': actors, 'footprints': foot, 'keepouts': keepouts, 'verified_only_for': 'Medium'}, indent=1), encoding='utf-8')
    for n, a in actors.items(): print(n.ljust(11), 'loc', a['translation_m'], 'yaw', a['yaw_degrees'], 'scale', a['scale'])
    for n, f in foot.items(): print(n, f['bounds_xy_m'], 'z', f['z_range_m'], 'area', f['area_m2'])


if __name__ == '__main__': main()
