"""Independent check of the decoded stair transforms against the ground-floor mesh (not used in decoding)."""
from pathlib import Path
import json, math, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from shapely.geometry import Point
from ffxiv_furniture.house_profiles import room_polygon
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles

t = json.loads((ROOT / 'outputs/house-layouts/medium-stair-transforms.json').read_text(encoding='utf-8'))
floor = room_polygon(ROOT, 'Medium')
rec = next(r for r in json.loads((ROOT / 'outputs/house-layouts/native-bounds.json').read_text(encoding='utf-8'))['records'] if r['source'].replace(chr(92), '/').endswith('Shirogane/Stair/Stair1.uexp'))
verts, _ = read_static_mesh_triangles(rec)
for name in ('Stairs', 'Stairs2_9'):
    a = t['actors'][name]; sx = a['scale'][0]; c, s = math.cos(math.radians(a['yaw_degrees'])), math.sin(math.radians(a['yaw_degrees'])); tx, ty, tz = a['translation_m']
    W = [(c * x * sx - s * y + tx, s * x * sx + c * y + ty, z + tz) for x, y, z in verts]
    at_floor = [(x, y) for x, y, z in W if abs(z) < 0.15]
    inside = sum(floor.buffer(0.05).contains(Point(p)) for p in at_floor)
    print(f'{name}: vertices at ground level z~0: {len(at_floor)}, of which on the ground-floor mesh: {inside}')
    if at_floor:
        xs = [p[0] for p in at_floor]; ys = [p[1] for p in at_floor]; print('   ground-level ring bbox x', round(min(xs), 2), round(max(xs), 2), 'y', round(min(ys), 2), round(max(ys), 2))
print('notch (floor missing) is x -12..-4, y 2..8')
