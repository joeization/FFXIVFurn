"""Furniture placement on the REAL floor outline with true rotated footprints. The MODEL directs intent; this module only executes it.

Per plan item the model may give `placement` = {arrangement, wall, facing, spacing_m, allow_overlap}; zones may give a compass `region`.
Hard constraints (physics only): inside the floor, outside the stair bodies, wall items on a wall, props on a real flat surface.
Everything else is soft: walkway clearance, the Medium entrance corridor and overlaps are avoided first and relaxed rather than dropping furniture
(FFXIV allows furniture to overlap, so an item is only left unplaced when even the relaxed passes find no spot at all).

Data-driven (see `placement_info`, measured by scripts/fill_placement_info.py): every item has its own measured FRONT direction (`front_deg`, CCW from model-local +X),
yaw = wanted_facing - front_deg so ANY angle works; placement type decides the branch (floor / wall / ceiling / rug).
Conventions that remain assumptions (not calibrated in the app): yaw is CCW about Z in the renderer's space; pillars, doors and the entrance are not modelled.
"""
from __future__ import annotations
import math
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.prepared import prep

GAP = 0.04
WALL_GAP = 0.03
WALL_CONTACT = 0.12
ART_CENTER_Z = 1.55
STEP = 0.1
WALKWAY = 1.0          # soft clearance around stairs (avoided first, then relaxed)
ORDER = ('rug', 'table', 'seating', 'architecture', 'storage', 'lighting', 'wall-art', 'decor')
WALLS = {'W': 0, 'E': 180, 'S': 90, 'N': 270}  # wall -> direction an item against it faces (inward)
COMPASS = {'E': 0.0, 'N': 90.0, 'W': 180.0, 'S': 270.0}   # world directions: +x east, +y north
DEFAULT_ARRANGEMENT = {}   # no role is forced into a pattern; the model chooses an arrangement


# ---------------------------------------------------------------- geometry
def rot(x, y, yaw_deg):
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    return c * x - s * y, s * x + c * y


def corners(it):
    lo, hi = it['lo'], it['hi']
    return [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])]


def poly_at(it, yaw, pivot):
    return Polygon([(rot(x, y, yaw)[0] + pivot[0], rot(x, y, yaw)[1] + pivot[1]) for x, y in corners(it)])


def pivot_for_center(it, yaw, center):
    cx, cy = (it['lo'][0] + it['hi'][0]) / 2, (it['lo'][1] + it['hi'][1]) / 2; rx, ry = rot(cx, cy, yaw)
    return (center[0] - rx, center[1] - ry)


def face_yaw(it, facing_deg):
    return (facing_deg - it['front_deg']) % 360


def wrap(a): return (a + 180) % 360 - 180


def angle_to(a, b): return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360


def wall_segments(scene):
    if not hasattr(scene, '_segs'):
        rings = [scene.polygon.exterior] + list(scene.polygon.interiors) if scene.polygon.geom_type == 'Polygon' else [r for g in scene.polygon.geoms for r in [g.exterior, *g.interiors]]
        scene._segs = [(a, b) for ring in rings for a, b in zip(list(ring.coords)[:-1], list(ring.coords)[1:]) if math.dist(a, b) > 1e-6]
    return scene._segs


def wall_normal_at(scene, geom, ref=None):
    """Direction (deg) of the wall normal pointing into the room, for the wall segment nearest to `geom` (a point or polygon)."""
    seg = min(wall_segments(scene), key=lambda s: LineString(s).distance(geom)); (ax, ay), (bx, by) = seg
    L = math.hypot(bx - ax, by - ay); dx, dy = (bx - ax) / L, (by - ay) / L; nx, ny = -dy, dx; c = geom.centroid if ref is None else Point(ref)
    if (c.x - ax) * nx + (c.y - ay) * ny < 0: nx, ny = -nx, -ny
    return math.degrees(math.atan2(ny, nx)) % 360


# ---------------------------------------------------------------- scene
class Scene:
    def __init__(self, room):
        self.polygon = room['polygon']; self.ceiling = room['ceiling_z']
        self.usable = prep(self.polygon.buffer(-WALL_GAP)); self.wall_cover = prep(self.polygon.buffer(0.002)); self.boundary = self.polygon.boundary
        keeps = list(room.get('keepouts') or [])
        self.keepout_union = unary_union(keeps) if keeps else None
        self.keep = prep(self.keepout_union) if keeps else None        # HARD: the stair bodies
        soft = ([box(*room['corridor'])] if room.get('corridor') else []) + [k.buffer(WALKWAY, join_style=2) for k in keeps]
        self.soft = prep(unary_union(soft)) if soft else None          # SOFT: walkway around stairs + the Medium entrance corridor
        self.free = self.polygon.difference(self.keepout_union) if keeps else self.polygon
        self.solid = []; self.art = []; self.hung = []; self.placements = []; self.unplaced = []; self.tables = []; self.tabletop = []
        self.strict = True; self.overlap = False; self.counters = {}; self.anchors = {}

    def blocked(self, poly):
        return self.keep is not None and self.keep.intersects(poly)

    def soft_blocked(self, poly):
        return self.soft is not None and self.soft.intersects(poly)

    def wall_contact(self, poly):
        return poly.distance(self.boundary) < WALL_CONTACT

    def fits(self, poly, layer):
        if layer == 'rug':
            return self.wall_cover.covers(poly) and not self.blocked(poly)
        if layer == 'wall':
            if not (self.wall_cover.covers(poly) and not self.blocked(poly) and poly.distance(self.boundary) < 0.05): return False
            if self.overlap: return True
            return not any(poly.distance(a) < 0.05 for a in self.art) and not any(poly.intersects(s[0]) and s[1] > 1.0 for s in self.solid)
        if not (self.usable.covers(poly) and not self.blocked(poly)): return False
        if self.strict and self.soft_blocked(poly): return False
        if self.overlap: return True
        return not any(poly.distance(s[0]) < GAP for s in self.solid)


def make_item(entry, geo, idx):
    lo, hi = geo['lo'], geo['hi']; role = entry['role']; cat = geo['category']
    ptype = geo.get('ptype') or ('wall' if (role == 'wall-art' and (cat.startswith('Item/Printed') or cat == 'Furniture/Wall-Mounted')) else
                                 'rug' if role == 'rug' or cat == 'Furniture/Rug' else 'floor')
    return {'item_id': entry['item_id'], 'name': geo['name'], 'role': role, 'zone': entry['zone'], 'lo': lo, 'hi': hi, 'height': hi[2] - lo[2], 'category': cat, 'ptype': ptype,
            'front_deg': float(geo.get('front_deg', 90.0)), 'supports_top': bool(geo.get('supports_top', False)), 'top_z': geo.get('top_z_local'),
            'mount_bottom_z': geo.get('mount_bottom_z'), 'small': bool(geo.get('small', (hi[2] - lo[2]) < 0.6 and max(hi[0] - lo[0], hi[1] - lo[1]) < 0.7)),
            'round_top': bool(geo.get('round_top', False)), 'surfaces': geo.get('surfaces'), 'idx': idx, 'spec': dict(entry.get('placement') or {}), 'key': entry.get('entry_key')}


def commit(scene, it, yaw, pivot, layer, z=None, note=''):
    poly = poly_at(it, yaw, pivot)
    if z is None: z = -it['lo'][2]
    if scene.overlap and layer in ('solid', 'seat') and any(poly.intersects(s[0]) and poly.intersection(s[0]).area > 1e-4 for s in scene.solid): note = (note + ' [overlaps another item]').strip()
    scene.placements.append({'item_id': it['item_id'], 'name': it['name'], 'zone': it['zone'], 'role': it['role'], 'ptype': it['ptype'], 'location_m': [round(pivot[0], 4), round(pivot[1], 4), round(z, 4)],
                             'yaw_degrees': round(yaw % 360, 3), 'front_deg': it['front_deg'], 'footprint_m': [round(v, 3) for v in poly.bounds],
                             'footprint_poly': [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords][:-1], 'layer': layer, 'note': note, 'z_top_m': round(z + it['hi'][2], 3), 'intent': it['spec']})
    if layer in ('solid', 'seat'):
        scene.solid.append((poly, z + it['hi'][2], it, z))
        if it['role'] == 'table' and layer == 'solid': scene.tables.append((poly, it))
    elif layer == 'wall': scene.art.append(poly)
    return poly


def try_at(scene, it, center, facing, layer, z=None, note=''):
    yaw = face_yaw(it, facing); pivot = pivot_for_center(it, yaw, center); poly = poly_at(it, yaw, pivot)
    return commit(scene, it, yaw, pivot, layer, z, note) if scene.fits(poly, 'solid' if layer == 'seat' else layer) else None


def spiral(center, bounds, step=0.25, limit=300):
    yield center
    for k in range(1, limit):
        r = k * step
        for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r), (r, r), (-r, r), (r, -r), (-r, -r)):
            p = (center[0] + dx, center[1] + dy)
            if bounds[0] - 1 <= p[0] <= bounds[2] + 1 and bounds[1] - 1 <= p[1] <= bounds[3] + 1: yield p


def bbox_wh(it, yaw):
    b = poly_at(it, yaw, (0, 0)).bounds; return b[2] - b[0], b[3] - b[1]


def wall_facing(f, wall, k, it):
    """World facing for an item standing against `wall` given the model's facing word (None -> back to the wall, front into the room)."""
    base = float(WALLS[wall])
    if f is None or f in ('wall', 'center'): return base
    if isinstance(f, (int, float)): return float(f) % 360
    if f in COMPASS: return COMPASS[f]
    if f == 'outward': return (base + 180) % 360
    if f == 'along_wall': return (base + (90 if k % 2 == 0 else -90)) % 360
    if f == 'alternate': return (base if k % 2 == 0 else base + 90) % 360
    if f == 'random': return (it['idx'] * 137.508) % 360
    return base


def pick_facing(scene, it, pos, anchor, k, default):
    """World facing at a free position. `anchor` = point the item looks toward for 'center'."""
    f = it['spec'].get('facing', default)
    if isinstance(f, (int, float)): return float(f) % 360
    if f in COMPASS: return COMPASS[f]
    if f == 'center': return angle_to(pos, anchor) if math.dist(pos, anchor) > 0.05 else 90.0
    if f == 'outward': return angle_to(anchor, pos) if math.dist(pos, anchor) > 0.05 else 270.0
    if f == 'alternate': return 90.0 if k % 2 == 0 else 0.0
    if f == 'random': return (it['idx'] * 137.508) % 360
    if f in ('wall', 'along_wall'):
        n = wall_normal_at(scene, Point(pos)); return n if f == 'wall' else (n + (90 if k % 2 == 0 else -90)) % 360
    return 90.0


def slide_to_wall(scene, it, region, wall, frac, layer, z=None, note='', facing=None, s_values=None):
    """Slide from a house wall inward along sample lines; accept only a fit that touches that wall (so it is not left floating mid-room)."""
    yaw = face_yaw(it, WALLS[wall] if facing is None else facing); b = region.bounds; w, d = bbox_wh(it, yaw)
    horizontal = wall in 'WE'; lo, hi = (b[1], b[3]) if horizontal else (b[0], b[2])
    if hi - lo < (d if horizontal else w): return None
    n = 24
    samples = list(s_values) if s_values is not None else sorted((lo + (hi - lo) * (k + 0.5) / n for k in range(n)), key=lambda s: abs((s - lo) / (hi - lo) - frac)); near = region.buffer(0.3)
    for s in samples:
        a = (b[0], b[2]) if horizontal else (b[1], b[3]); span = (w if horizontal else d) / 2
        pos = [a[0] + span + i * STEP for i in range(int((a[1] - a[0] - 2 * span) / STEP) + 1)]
        if wall in 'EN': pos.reverse()
        for t in pos:
            c = (t, s) if horizontal else (s, t)
            if not near.covers(Point(c)): continue
            pivot = pivot_for_center(it, yaw, c); poly = poly_at(it, yaw, pivot)
            if not scene.fits(poly, layer): continue
            if scene.wall_contact(poly): return commit(scene, it, yaw, pivot, layer, z, note)
            break
    return None


def wall_item_z(scene, it):
    """Bottom z for a wall item from measured mount height, clamped under the ceiling. None if it cannot hang at all."""
    h = it['hi'][2] - it['lo'][2]; bottom = it['mount_bottom_z'] if it['mount_bottom_z'] is not None else max(0.05, ART_CENTER_Z - h / 2)
    bottom = min(bottom, scene.ceiling - 0.3 - h)
    return None if bottom < 0 else bottom - it['lo'][2]


def ray_exit(poly, center, ang):
    far = (center[0] + 20 * math.cos(math.radians(ang)), center[1] + 20 * math.sin(math.radians(ang)))
    inter = LineString([center, far]).intersection(poly.exterior)
    pts = [inter] if inter.geom_type == 'Point' else list(getattr(inter, 'geoms', []))
    return max((Point(center).distance(p) for p in pts), default=0.5)


def seat_slots(scene, it, table_poly, n_seats, round_top):
    """Candidate (yaw, centre) around a table. Round tops: an even ring at arbitrary angles; rectangular: the four sides."""
    ctr = table_poly.centroid; ctr = (ctr.x, ctr.y); slots = []
    if round_top:
        for k in range(max(n_seats, 3) if n_seats > 1 else 1):
            ang = 270 + 360 * k / max(n_seats, 3 if n_seats > 1 else 1)
            facing = (ang + 180) % 360; yaw = face_yaw(it, facing); r = ray_exit(table_poly, ctr, ang)
            for _ in range(60):
                c = (ctr[0] + r * math.cos(math.radians(ang)), ctr[1] + r * math.sin(math.radians(ang)))
                if poly_at(it, yaw, pivot_for_center(it, yaw, c)).distance(table_poly) >= GAP * 2: break
                r += 0.03
            slots.append((yaw, c))
    else:
        x0, y0, x1, y1 = table_poly.bounds; tw, td = x1 - x0, y1 - y0
        for side, face in (('S', 90), ('N', 270), ('W', 0), ('E', 180)):
            yaw = face_yaw(it, face); w, d = bbox_wh(it, yaw); length = tw if side in 'SN' else td; unit = w if side in 'SN' else d
            n = max(1, int((length + GAP) // unit)) if unit > 0 else 1
            for k in range(min(n, 4)):
                off = ((k + 0.5) / n - 0.5) * length
                if side == 'S': c = ((x0 + x1) / 2 + off, y0 - GAP * 2 - d / 2)
                elif side == 'N': c = ((x0 + x1) / 2 + off, y1 + GAP * 2 + d / 2)
                elif side == 'W': c = (x0 - GAP * 2 - w / 2, (y0 + y1) / 2 + off)
                else: c = (x1 + GAP * 2 + w / 2, (y0 + y1) / 2 + off)
                slots.append((yaw, c))
    return slots


# ---------------------------------------------------------------- arrangements (each returns a placement poly or None for ONE item under the scene's current pass flags)
def _centre(region):
    c = region.centroid if region.contains(region.centroid) else region.representative_point(); return (c.x, c.y)


def _walls_for(it):
    w = it['spec'].get('wall'); return [w] if w in WALLS else list(WALLS)


def _least_overlap_spot(scene, it, region, g, default_facing):
    """Overlap pass: spread pieces over the zone (sunflower sample) and take the spot that overlaps existing furniture least, instead of piling everything on the centre."""
    cx, cy = _centre(region); x0, y0, x1, y1 = region.bounds; best = None; n = 90; off = (it['idx'] * 7) % n
    for j in range(n):
        t = (j + off) % n; r = math.sqrt((t + 0.5) / n); a = t * 2.399963
        p = (cx + r * (x1 - x0) / 2 * math.cos(a), cy + r * (y1 - y0) / 2 * math.sin(a))
        if not region.buffer(0.3).covers(Point(p)): continue
        yaw = face_yaw(it, pick_facing(scene, it, p, (cx, cy), g['k'], default_facing)); pivot = pivot_for_center(it, yaw, p); poly = poly_at(it, yaw, pivot)
        if not scene.fits(poly, 'solid'): continue
        cost = sum(poly.intersection(sl[0]).area for sl in scene.solid if poly.intersects(sl[0]))
        if best is None or cost < best[0] - 1e-9: best = (cost, yaw, pivot)
        if cost == 0: break
    if best is None: return None
    return commit(scene, it, best[1], best[2], 'solid', note='free spot')


def _free_spot(scene, it, region, g, default_facing):
    cx, cy = _centre(region)
    if scene.overlap: return _least_overlap_spot(scene, it, region, g, default_facing)
    for p in spiral((cx, cy), region.bounds):
        done = try_at(scene, it, p, pick_facing(scene, it, p, (cx, cy), g['k'], default_facing), 'solid', note='free spot')
        if done: return done
    return None


def _wall_first(scene, it, region, g, note='against house wall (back to wall)'):
    f = it['spec'].get('facing')
    for wl in _walls_for(it):
        used = scene.counters.get((it['zone'], wl), 0)
        done = slide_to_wall(scene, it, region, wl, (used * 0.381966 + 0.1) % 1.0, 'solid', note=note, facing=wall_facing(f, wl, g['k'], it))
        if done: scene.counters[(it['zone'], wl)] = used + 1; return done
    return None


def arr_scatter(scene, it, region, g):
    role = it['role']; cx, cy = _centre(region)
    if role == 'table' or (role == 'decor' and it['category'].startswith('Furniture/Table')):
        for p in spiral((cx, cy), region.bounds):
            done = try_at(scene, it, p, pick_facing(scene, it, p, (cx, cy), g['k'], 90.0), 'solid')
            if done: return done
        return None
    if role == 'seating' and it['ptype'] == 'floor':
        zt = [t for t in scene.tables if t[1]['zone'] == it['zone']] or sorted(scene.tables, key=lambda t: t[0].distance(Point(cx, cy)))[:1]
        if zt and 'facing' not in it['spec']:
            tpoly, tit = zt[0]; n = max(1, g['zone_seats']); slots = seat_slots(scene, it, tpoly, n, tit['round_top']); i = scene.counters.get((it['zone'], 'seat'), 0)
            order = slots[i % len(slots):] + slots[:i % len(slots)] if slots else []
            for yaw, c in order:
                poly = poly_at(it, yaw, pivot_for_center(it, yaw, c))
                if scene.fits(poly, 'solid'): scene.counters[(it['zone'], 'seat')] = i + 1; return commit(scene, it, yaw, pivot_for_center(it, yaw, c), 'seat', note='seated around table (facing it)')
    if role == 'decor' and it['height'] < 0.8 and it['ptype'] == 'floor' and not it['spec'].get('arrangement'):
        surfaces = [s for s in scene.solid if s[2]['supports_top'] and s[2]['top_z'] is not None and s[2]['zone'] == it['zone']] or [s for s in scene.solid if s[2]['supports_top'] and s[2]['top_z'] is not None]
        for tpoly, tz0, tit, tzz in sorted(surfaces, key=lambda s: s[0].distance(Point(cx, cy)))[:4]:
            tz = tzz + tit['top_z']
            inner = tpoly.buffer(-0.12)
            if inner.is_empty: continue
            for p in spiral((inner.centroid.x, inner.centroid.y), inner.bounds, step=0.12, limit=40):
                pivot = pivot_for_center(it, 0, p); poly = poly_at(it, 0, pivot)
                if inner.covers(poly) and not any(poly.distance(o) < 0.05 for o in scene.tabletop):
                    scene.tabletop.append(poly); return commit(scene, it, 0, pivot, 'top', z=tz - it['lo'][2], note='on measured flat surface')
    if role != 'architecture':
        done = _wall_first(scene, it, region, g)
        if done: return done
    return _free_spot(scene, it, region, g, 'alternate' if role == 'architecture' else 'center')   # architecture pieces default to a staggered 0/90 rhythm, not one direction


def arr_wall_row(scene, it, region, g):
    """Copies side by side along ONE wall (the model's `wall`, else the first wall with room), contiguous with `spacing_m` between them."""
    f = it['spec'].get('facing'); sp = float(it['spec'].get('spacing_m', 0.05)); k = g['k']
    if not scene.overlap: sp = max(sp, GAP + 0.01)   # non-overlapping passes need the small safety gap; overlap passes honour a smaller or negative spacing
    for wl in (_walls_for(it) if 'wall_choice' not in g else [g['wall_choice']]):
        yaw = face_yaw(it, wall_facing(f, wl, k, it)); w, d = bbox_wh(it, yaw); horizontal = wl in 'WE'; extent = w if not horizontal else d
        b = region.bounds; lo, hi = (b[1], b[3]) if horizontal else (b[0], b[2])
        if 'cursor' not in g or g.get('wall_choice') != wl:
            total = sum((bbox_wh(x, face_yaw(x, wall_facing(f, wl, i, x)))[1 if horizontal else 0]) for i, x in enumerate(g['items'])) + sp * (len(g['items']) - 1)
            g['cursor'] = max(lo, (lo + hi) / 2 - total / 2); g['wall_choice'] = wl
        cur = g['cursor']; tries = 0
        while cur + extent <= hi + 1e-6 and tries < 80:
            done = slide_to_wall(scene, it, region, wl, 0.5, 'solid', note=f'row along {wl} wall', facing=wall_facing(f, wl, k, it), s_values=[cur + extent / 2])
            if done: g['cursor'] = cur + extent + sp; return done
            cur += 0.2; tries += 1
        g.pop('wall_choice', None); g.pop('cursor', None)
    return arr_scatter(scene, it, region, g)


def arr_ring(scene, it, region, g):
    cx, cy = _centre(region); zt = [t for t in scene.tables if t[1]['zone'] == it['zone']]
    ax, ay = (zt[0][0].centroid.x, zt[0][0].centroid.y) if zt else (cx, cy); n = max(1, g['n']); k = g['k']; ang = (360.0 * k / n + 15) % 360
    r0 = 0.5 + max(it['hi'][0] - it['lo'][0], it['hi'][1] - it['lo'][1]) / 2 + (math.sqrt(zt[0][0].area) / 2 if zt else 0.0)
    for j in range(60):
        r = r0 + j * 0.15; c = (ax + r * math.cos(math.radians(ang)), ay + r * math.sin(math.radians(ang)))
        done = try_at(scene, it, c, pick_facing(scene, it, c, (ax, ay), k, 'center'), 'solid', note='ring')
        if done: return done
    return arr_scatter(scene, it, region, g)


def arr_grid(scene, it, region, g):
    cx, cy = _centre(region); n = max(1, g['n']); k = g['k']; cols = max(1, math.ceil(math.sqrt(n))); sp = float(it['spec'].get('spacing_m', 0.1))
    cell = max(it['hi'][0] - it['lo'][0], it['hi'][1] - it['lo'][1]) + sp; col, row = k % cols, k // cols; rows = math.ceil(n / cols)
    c = (cx + (col - (cols - 1) / 2) * cell, cy + (row - (rows - 1) / 2) * cell)
    for p in spiral(c, region.bounds, step=0.15, limit=120):
        done = try_at(scene, it, p, pick_facing(scene, it, p, (cx, cy), k, 90.0), 'solid', note='grid')
        if done: return done
    return None


def arr_line(scene, it, region, g):
    """A straight line through the zone (dividers, stepping pieces): along the zone's longer axis, centred, `spacing_m` apart, orientation per model (default alternating)."""
    cx, cy = _centre(region); n = max(1, g['n']); k = g['k']; b = region.bounds; sp = float(it['spec'].get('spacing_m', 0.3)); ext = max(it['hi'][0] - it['lo'][0], it['hi'][1] - it['lo'][1]) + sp
    along_x = (b[2] - b[0]) >= (b[3] - b[1]); off = (k - (n - 1) / 2) * ext; c = (cx + off, cy) if along_x else (cx, cy + off)
    for p in spiral(c, region.bounds, step=0.15, limit=120):
        done = try_at(scene, it, p, pick_facing(scene, it, p, (cx, cy), k, 'alternate'), 'solid', note='line')
        if done: return done
    return None


def arr_corner(scene, it, region, g):
    cx, cy = _centre(region); verts = [v for ring in ([scene.polygon.exterior] + list(scene.polygon.interiors)) for v in list(ring.coords)[:-1] if region.buffer(0.5).covers(Point(v))]
    verts.sort(key=lambda v: math.dist(v, (cx, cy)), reverse=True)
    if not verts: return arr_scatter(scene, it, region, g)
    ext = max(it['hi'][0] - it['lo'][0], it['hi'][1] - it['lo'][1]) / 2
    for v in verts[g['k'] % len(verts):] + verts[:g['k'] % len(verts)]:
        ux, uy = cx - v[0], cy - v[1]; L = math.hypot(ux, uy) or 1.0; ux, uy = ux / L, uy / L
        for j in range(40):
            c = (v[0] + ux * (ext * 0.9 + j * 0.08), v[1] + uy * (ext * 0.9 + j * 0.08))
            done = try_at(scene, it, c, pick_facing(scene, it, c, (cx, cy), g['k'], 'center'), 'solid', note='corner')
            if done: return done
    return arr_scatter(scene, it, region, g)


def arr_cluster(scene, it, region, g):
    ax, ay = g.get('anchor') or _centre(region)
    for p in spiral((ax, ay), region.bounds, step=0.12, limit=120):
        done = try_at(scene, it, p, pick_facing(scene, it, p, (ax, ay), g['k'], 'random'), 'solid', note='cluster')
        if done:
            g.setdefault('anchor', (p[0], p[1])); return done
    return None


ARRANGEMENTS = {'scatter': arr_scatter, 'wall_row': arr_wall_row, 'ring': arr_ring, 'grid': arr_grid, 'line': arr_line, 'corner': arr_corner, 'cluster': arr_cluster}


# ---------------------------------------------------------------- one item, under relaxing passes
def passes(allow_overlap, region, free):
    if allow_overlap: return [(True, True, region), (False, True, region), (False, True, free)]
    return [(True, False, region), (True, False, free), (False, False, region), (False, False, free), (False, True, region), (False, True, free)]


def place_other(scene, it, region, g):
    ptype = it['ptype']; cx, cy = _centre(region)
    if ptype == 'rug':
        for p in spiral((cx, cy), region.bounds):
            pivot = pivot_for_center(it, 0, p); poly = poly_at(it, 0, pivot)
            if scene.fits(poly, 'rug'): return commit(scene, it, 0, pivot, 'rug', note='rugs may overlap other items by design')
        return None
    if ptype == 'ceiling':
        for p in spiral((cx, cy), region.bounds):
            pivot = pivot_for_center(it, 0, p); poly = poly_at(it, 0, pivot)
            if scene.usable.covers(poly) and not scene.blocked(poly) and (scene.overlap or not any(poly.distance(h) < 0.2 for h in scene.hung)):
                scene.hung.append(poly); return commit(scene, it, 0, pivot, 'hang', z=scene.ceiling - 0.1 - it['hi'][2], note='hung from ceiling')
        return None
    if ptype == 'wall':
        zc = wall_item_z(scene, it)
        if zc is None: return None
        f = it['spec'].get('facing')
        for wl in _walls_for(it):
            used = scene.counters.get((it['zone'], wl + 'w'), 0)
            done = slide_to_wall(scene, it, region, wl, (used * 0.381966 + 0.2) % 1.0, 'wall', z=zc, note=f'hung on house wall at z={round(zc + it["lo"][2], 2)}', facing=wall_facing(f, wl, g['k'], it))
            if done: scene.counters[(it['zone'], wl + 'w')] = used + 1; return done
        return None
    arr = it['spec'].get('arrangement') or DEFAULT_ARRANGEMENT.get(it['role'], 'scatter')
    return ARRANGEMENTS.get(arr, arr_scatter)(scene, it, region, g)


def place_item(scene, it, region, free, g):
    saved = (scene.strict, scene.overlap)
    try:
        for strict, overlap, reg in passes(bool(it['spec'].get('allow_overlap')), region, free):
            scene.strict, scene.overlap = strict, overlap
            done = place_other(scene, it, reg, g)
            if done is not None:
                if overlap and not it['spec'].get('allow_overlap'): scene.placements[-1]['note'] = (scene.placements[-1]['note'] + ' [relaxed: overlap allowed]').strip()
                elif not strict: scene.placements[-1]['note'] = (scene.placements[-1]['note'] + ' [relaxed: walkway]').strip()
                return done
    finally:
        scene.strict, scene.overlap = saved
    return None


def _axis_half(it, yaw, ax):
    """Half extent of the item's rotated footprint along the unit vector ax."""
    pts = [(rot(x, y, yaw)[0], rot(x, y, yaw)[1]) for x, y in corners(it)]; proj = [p[0] * ax[0] + p[1] * ax[1] for p in pts]; return (max(proj) - min(proj)) / 2


def _record_anchor(scene, it):
    """Remember the pose of an anchor piece so group members can be placed relative to it."""
    g = it['spec'].get('group')
    if not g or not scene.placements: return
    pl = scene.placements[-1]
    if pl['item_id'] != it['item_id']: return
    poly = Polygon(pl['footprint_poly']); facing = (pl['front_deg'] + pl['yaw_degrees']) % 360
    scene.anchors.setdefault((it['zone'], g), {'poly': poly, 'facing': facing, 'item': it, 'z': pl['location_m'][2]})


def place_relative(scene, it, g):
    """Group member: placed beside/in front of/behind/around/on/above its anchor, mirroring the anchor's orientation. None -> caller falls back to normal placement."""
    spec = it['spec']; key = (it['zone'], spec.get('group')); an = scene.anchors.get(key); rel = spec.get('relation')
    if an is None or rel in (None, 'anchor'): return None
    c = an['poly'].centroid; cx, cy = c.x, c.y; f = an['facing']; fw = (math.cos(math.radians(f)), math.sin(math.radians(f))); lf = (-fw[1], fw[0])
    k, n = g['k'], max(1, g['n']); gap = float(spec.get('gap_m', 0.08)); an_it = an['item']
    if rel == 'on_top':
        surfaces = an_it.get('surfaces') or ([{'z': an_it['top_z'], 'min_x': an_it['lo'][0], 'min_y': an_it['lo'][1], 'max_x': an_it['hi'][0], 'max_y': an_it['hi'][1]}] if an_it.get('supports_top') and an_it.get('top_z') is not None else [])
        if not surfaces: return None
        si = k % len(surfaces); s = surfaces[si]; poly0 = an['poly']; inner = poly0.buffer(-0.1) if poly0.buffer(-0.1).area > 0.01 else poly0
        slots = scene.counters.get(('top', key, si), 0); scene.counters[('top', key, si)] = slots + 1
        ang = 137.5 * slots; rad = 0 if slots == 0 else min(inner.bounds[2] - inner.bounds[0], inner.bounds[3] - inner.bounds[1]) * 0.28
        p = (inner.centroid.x + rad * math.cos(math.radians(ang)), inner.centroid.y + rad * math.sin(math.radians(ang)))
        facing = (f + slots * 40) % 360
        yaw = face_yaw(it, facing); pivot = pivot_for_center(it, yaw, p)
        return commit(scene, it, yaw, pivot, 'top', z=an['z'] + s['z'] - it['lo'][2], note=f'group {key[1]}: on surface {si} of the anchor')
    if rel == 'above':
        wl = min(WALLS, key=lambda w: abs(wrap(WALLS[w] - f))); zc = wall_item_z(scene, it); horizontal = wl in 'WE'
        if zc is None: return None
        off = (k - (n - 1) / 2) * (max(it['hi'][0] - it['lo'][0], it['hi'][1] - it['lo'][1]) + gap)
        sv = (cy if horizontal else cx) + off
        return slide_to_wall(scene, it, an['poly'].buffer(3), wl, 0.5, 'wall', z=zc, note=f'group {key[1]}: above the anchor', s_values=[sv])
    if rel == 'around':
        ang = (360.0 * k / n + 15) % 360; r0 = max(_axis_half(an_it, face_yaw(an_it, f), (math.cos(math.radians(ang)), math.sin(math.radians(ang)))), 0.3) + 0.35
        for j in range(30):
            p = (cx + (r0 + j * 0.1) * math.cos(math.radians(ang)), cy + (r0 + j * 0.1) * math.sin(math.radians(ang)))
            done = try_at(scene, it, p, spec['facing'] if isinstance(spec.get('facing'), (int, float)) else angle_to(p, (cx, cy)), 'solid', note=f'group {key[1]}: around the anchor')
            if done: return done
        return None
    side = {'left': (lf, 1), 'right': (lf, -1), 'front': (fw, 1), 'behind': (fw, -1)}.get(rel)
    if rel == 'flank': side = (lf, 1 if k % 2 == 0 else -1)
    if side is None: return None
    axis0, sign = side; ax = (axis0[0] * sign, axis0[1] * sign); rank = k // 2 if rel == 'flank' else k
    facing = f if rel != 'front' else (f + 180) % 360
    if isinstance(spec.get('facing'), (int, float)): facing = float(spec['facing'])
    yaw = face_yaw(it, facing); half_a = _axis_half(an_it, face_yaw(an_it, f), ax); half_m = _axis_half(it, yaw, ax)
    for scale in (1.0, 1.25, 1.6):   # relax outward when the exact spot is taken
        d = (half_a + half_m + gap + rank * (2 * half_m + gap)) * scale; p = (cx + ax[0] * d, cy + ax[1] * d)
        done = try_at(scene, it, p, facing, 'solid', note=f'group {key[1]}: {rel} of the anchor')
        if done: return done
    return None


def place_zone(scene, region, items, free=None):
    free = free if free is not None else scene.free
    ordered = sorted(items, key=lambda i: (1 if (i['spec'].get('group') and i['spec'].get('relation') not in (None, 'anchor')) else 0, ORDER.index(i['role']), i['idx'])); groups = {}   # group members after their anchors
    for it in ordered: groups.setdefault(it['key'] if it['key'] is not None else ('solo', it['idx']), []).append(it)
    zone_seats = sum(1 for i in ordered if i['role'] == 'seating' and i['ptype'] == 'floor'); state = {}
    for it in ordered:
        key = it['key'] if it['key'] is not None else ('solo', it['idx']); members = groups[key]
        g = state.setdefault(key, {'k': 0, 'n': len(members), 'items': members, 'zone_seats': zone_seats}); g['k'] = members.index(it)
        if it['spec'].get('group') and it['spec'].get('relation') not in (None, 'anchor'):
            saved = (scene.strict, scene.overlap)
            try:
                scene.strict, scene.overlap = False, True; done = place_relative(scene, it, g)
            finally: scene.strict, scene.overlap = saved
            if done is not None: continue
        done = place_item(scene, it, region, free, g)
        if done is not None: _record_anchor(scene, it)
        if done is None:
            scene.unplaced.append({'name': it['name'], 'zone': it['zone'], 'role': it['role'], 'reason': 'no spot anywhere on the floor, even with walkway and overlap relaxed'})


# ---------------------------------------------------------------- regions
def split_regions(polygon, fractions):
    """Cut the real outline along its longer axis so each zone gets its share of actual floor area."""
    x0, y0, x1, y1 = polygon.bounds; long_x = (x1 - x0) >= (y1 - y0); lo, hi = (x0, x1) if long_x else (y0, y1)
    total = sum(fractions); target = [f / total * polygon.area for f in fractions]; cuts = [lo]; pos = lo; i = 0
    def slab(a, c): return box(a, y0 - 1, c, y1 + 1) if long_x else box(x0 - 1, a, x1 + 1, c)
    while i < len(fractions) - 1 and pos < hi:
        pos += 0.1
        if polygon.intersection(slab(cuts[-1], pos)).area >= target[i]: cuts.append(pos); i += 1
    cuts += [hi] * (len(fractions) + 1 - len(cuts)); cuts[-1] = hi
    return [polygon.intersection(slab(cuts[k], cuts[k + 1])) for k in range(len(fractions))]


def sector(free, name):
    """The part of the free floor a compass word points at (halves overlap a little so zones can touch). None if too small to use."""
    if not isinstance(name, str): return None
    x0, y0, x1, y1 = free.bounds; w, h = x1 - x0, y1 - y0; n = name.lower()
    xr = (x0, x0 + .55 * w) if 'west' in n else (x0 + .45 * w, x1) if 'east' in n else (x0 + .25 * w, x0 + .75 * w)
    yr = (y0, y0 + .55 * h) if 'south' in n else (y0 + .45 * h, y1) if 'north' in n else (y0 + .25 * h, y0 + .75 * h)
    r = free.intersection(box(xr[0], yr[0], xr[1], yr[1])); return r if r.area >= 3.0 else None


def place_all(room, resolved):
    scene = Scene(room); zones = sorted({r['zone_index'] for r in resolved}); fr = {}; hint = {}
    for r in resolved: fr.setdefault(r['zone_index'], r.get('area_fraction', 1.0)); hint.setdefault(r['zone_index'], r.get('region'))
    sect = {z: sector(scene.free, hint[z]) for z in zones if hint.get(z)}; plain = [z for z in zones if z not in sect]
    regions = dict(sect)
    if plain: regions.update(dict(zip(plain, split_regions(scene.free, [fr[z] for z in plain]))))
    n = 0
    for z in zones:
        items = []
        for r in resolved:
            if r['zone_index'] != z: continue
            for _ in range(r['count']):
                items.append(make_item({'item_id': r['item_id'], 'role': r['role'], 'zone': r['zone'], 'placement': r.get('placement'), 'entry_key': r.get('entry_key')}, r['geometry'], n)); n += 1
        place_zone(scene, regions[z], items, scene.free)
    return scene, {'regions': {str(k): [round(v, 2) for v in r.bounds] + [round(r.area, 1)] for k, r in regions.items()}}
