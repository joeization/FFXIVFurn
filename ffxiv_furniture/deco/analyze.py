"""Read-only layout diagnostics (facts, never pass/fail, never block an edit): reachability + front clearance, seat/table orientation, wall alignment, left/centre/right balance.
FFXIV allows overlap and tight placements, so every number is a hint for the designer (human or model)."""
from __future__ import annotations
import math
from collections import deque
import numpy as np
from shapely import affinity, prepared
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union
from .core import DecoError

SEAT = ('chair', 'stool', 'sofa', 'armchair', 'bench', 'seat', 'cushion')
STEP = 0.25
OPENING = 1.3   # fallback walkable gap assumed in the middle of door/arch partitions when the native mesh cannot be measured
STRUCT = ('partition', 'pillar', 'screen')
_OPENINGS = {}


def _mesh_openings(cat, item_id, z_band=(0.3, 2.0), min_width=0.6, step=0.05):
    """Walkable gaps through a partition measured from its native mesh, as local (lo, hi) intervals along the
    long local axis. A gap counts when NO triangle reaches into the walking band (z 0.3..2.0 m) across it;
    threshold rails below 0.3 m are stepped over. Returns (axis, [(lo, hi), ...]) or None if the mesh is unreadable.
    Cached per item: sliding-door partitions (Paper/Oriental Partition) open a ~1.8 m bay on one half, not a centred gap."""
    if item_id in _OPENINGS: return _OPENINGS[item_id]
    out = None
    try:
        import json
        from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
        row = cat.db.execute('SELECT evidence FROM asset_geometry WHERE item_id=?', (item_id,)).fetchone()
        if row is not None:
            v, t = read_static_mesh_triangles(json.loads(row[0]))[:2]
            v = np.asarray(v, float); t = np.asarray(t).reshape(-1, 3)
            if np.abs(v).max() > 50: v = v / 100.0   # centimetre buffers
            P = v[t]; span = v.max(0) - v.min(0); ax = 0 if span[0] >= span[1] else 1
            sel = (P[:, :, 2].max(1) > z_band[0]) & (P[:, :, 2].min(1) < z_band[1])
            lo_t = P[sel][:, :, ax].min(1); hi_t = P[sel][:, :, ax].max(1)
            grid = np.arange(v[:, ax].min(), v[:, ax].max(), step); cov = np.zeros(len(grid), bool)
            for a, b in zip(lo_t, hi_t): cov |= (grid >= a - 0.01) & (grid <= b + 0.01)
            gaps, s0 = [], None
            for g, c in zip(grid, cov):
                if not c and s0 is None: s0 = g
                if c and s0 is not None: gaps.append((float(s0), float(g))); s0 = None
            if s0 is not None: gaps.append((float(s0), float(grid[-1])))
            out = (ax, [g for g in gaps if g[1] - g[0] >= min_width])
    except (ValueError, KeyError, OSError, IndexError):
        out = None
    _OPENINGS[item_id] = out
    return out


PLATFORM_WORDS = ('loft', 'platform', 'deck', 'dais')


def is_platform(it):
    """A low raised floor piece people stand on (Tatami/Flagstone/Wooden Loft, decks): 0.15-1.0 m high, a top surface covering
    most of its footprint, and a platform-type name. Treated as walkable floor (a step), not an obstacle; tables are excluded
    by the name rule even though they have a similar top. Whether the game lets a character step up is an app test."""
    h = it['hi'][2] - it['lo'][2]
    if it.get('ptype') != 'floor' or not (0.15 <= h <= 1.0) or not any(w in it['name'].lower() for w in PLATFORM_WORDS):
        return False
    foot = (it['hi'][0] - it['lo'][0]) * (it['hi'][1] - it['lo'][1])
    top = max(((x['max'][0] - x['min'][0]) * (x['max'][1] - x['min'][1]) for x in it.get('surfaces', []) if x.get('is_top')), default=0.0)
    return foot > 0 and top >= 0.7 * foot


def _solid_fp(inst, fp, cat=None, it=None):
    n = inst['name'].lower()
    tall = it is not None and (it['hi'][2] - it['lo'][2]) >= 2.2
    if cat is not None and it is not None and tall and 'partition' in n:
        m = _mesh_openings(cat, inst['item_id'])
        if m is not None:
            ax, gaps = m
            if not gaps: return fp
            px, py = inst['pivot'][0], inst['pivot'][1]; holes = []
            for g0, g1 in gaps:   # local box through the full thickness, rotated by yaw about the pivot
                local = box(g0, it['lo'][1] - 1, g1, it['hi'][1] + 1) if ax == 0 else box(it['lo'][0] - 1, g0, it['hi'][0] + 1, g1)
                holes.append(affinity.translate(affinity.rotate(local, inst['yaw'], origin=(0, 0)), px, py))
            return fp.difference(unary_union(holes))
    if ('door' in n or 'arch' in n) and 'partition' in n:
        b = fp.bounds; cx, cy = fp.centroid.x, fp.centroid.y
        horizontal = (b[2] - b[0]) >= (b[3] - b[1])
        gap = box(cx - OPENING / 2, b[1] - 1, cx + OPENING / 2, b[3] + 1) if horizontal else box(b[0] - 1, cy - OPENING / 2, b[2] + 1, cy + OPENING / 2)
        return fp.difference(gap)
    return fp


def _ang(a, b): return abs((a - b + 180) % 360 - 180)


def _flood(m, seed):
    ny, nx = m.shape; sj, si = seed
    seen = np.zeros_like(m)
    if not m[sj, si]: return seen
    q = deque([seed]); seen[sj, si] = True
    while q:
        j, i = q.popleft()
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = j + dj, i + di
            if 0 <= a < ny and 0 <= b < nx and m[a, b] and not seen[a, b]: seen[a, b] = True; q.append((a, b))
    return seen


def _erode(m, r):
    out = m.copy()
    for _ in range(r):
        o = out.copy(); o[1:, :] &= out[:-1, :]; o[:-1, :] &= out[1:, :]; o[:, 1:] &= out[:, :-1]; o[:, :-1] &= out[:, 1:]; out = o
    return out


def _stair_solids(room):
    """Walking-height obstacle of the up stair from the native mesh (Room.stair_info)."""
    s = room.stair_info()['up']['solid']
    return [s] if s is not None else []



def _slit_open(ga, gb, pa, pb, others):
    """True if the slit between ga and gb stays open across its whole depth after removing every other solid."""
    import math
    dx, dy = pb.x - pa.x, pb.y - pa.y; n = math.hypot(dx, dy)
    if n < 1e-9: return False
    ux, uy = -dy / n, dx / n   # depth axis: perpendicular to the gap direction
    slit = unary_union([ga, gb]).convex_hull.difference(ga.buffer(0.005)).difference(gb.buffer(0.005))
    if slit.is_empty: return False
    def extent(g):
        xs = [ux * x + uy * y for x, y in (g.exterior.coords if hasattr(g, 'exterior') else g.coords)]
        return max(xs) - min(xs)
    full = max((extent(g) for g in getattr(slit, 'geoms', [slit]) if g.area > 1e-4), default=0.0)
    if full <= 0: return False
    rest = slit.difference(unary_union([g.buffer(0.03) for g in others])) if others else slit
    return any(g.area > 1e-4 and extent(g) >= 0.95 * full for g in getattr(rest, 'geoms', [rest]))

def analyze(sess, level='ground', start=None, path_width=0.8, front_depth=0.6):
    room = sess.room; cat = sess.cat; z0 = room.level_z.get(level, 0.0); z1 = z0 + 7.0
    if level not in room.levels: raise DecoError('BAD_INPUT', f'level must be one of {list(room.levels)} for a {room.house_size}')
    floor = room.polys[level]
    items = []
    for inst in sess.instances.values():
        it = cat.item(inst['item_id']); zb = inst['pivot'][2] + it['lo'][2]
        if not (z0 - 0.5 <= zb < z1 - 0.5): continue
        items.append((inst, it, sess.footprint(inst), zb - z0, zb - z0 + (it['hi'][2] - it['lo'][2])))   # heights are relative to this level's floor
    minx, miny, maxx, maxy = floor.bounds; nx, ny = int((maxx - minx) / STEP) + 1, int((maxy - miny) / STEP) + 1
    xs = minx + (np.arange(nx) + .5) * STEP; ys = miny + (np.arange(ny) + .5) * STEP
    pf = prepared.prep(floor); walk = np.array([[pf.contains(Point(x, y)) for x in xs] for y in ys])
    solid = [_solid_fp(inst, fp, cat, it) for inst, it, fp, zb, zt in items if it['ptype'] not in ('rug', 'wall') and zt - zb >= 0.4 and zb <= 1.4 and not is_platform(it)]
    if level == 'ground': solid += _stair_solids(room)
    if level == 'basement' and room.stair_info().get('basement', {}).get('solid') is not None: solid.append(room.stair_info()['basement']['solid'])
    solid += list(room.pillars_by_level.get(level, []))   # structural pillars block walking
    blocked = np.zeros_like(walk)
    if solid:
        pu = prepared.prep(unary_union(solid)); blocked = np.array([[bool(walk[j, i]) and pu.contains(Point(x, y)) for i, x in enumerate(xs)] for j, y in enumerate(ys)])
    free = walk & ~blocked
    def cell(x, y): return (min(max(int((y - miny) / STEP), 0), ny - 1), min(max(int((x - minx) / STEP), 0), nx - 1))
    if start is None and level == 'basement':
        _fa = room.stair_info()['basement']['foot_access']; start = (_fa.centroid.x, _fa.centroid.y)
    sx, sy = start if start else ((room.door_xy[0], room.door_xy[1] - 0.6) if level == 'ground' else ((lambda c: (c.x, c.y - 1.0))(room.stair_info()['up']['arrival_access'].centroid)))   # upper: just beyond the arrival steps
    r = max(1, int(path_width / 2 / STEP)); narrow = _erode(free, r); seed = cell(sx, sy)
    if not narrow[seed]:
        js, is_ = np.where(narrow)
        if len(js): k = int(np.argmin((js - seed[0]) ** 2 + (is_ - seed[1]) ** 2)); seed = (int(js[k]), int(is_[k]))
    reach_w = _flood(narrow, seed); s0 = cell(sx, sy); reach_any = _flood(free, s0 if free[s0] else seed)
    # a cell counts as reachable at path width if it is within r cells of a reachable narrow cell
    near = reach_w.copy()
    for _ in range(r):
        o = near.copy(); o[1:, :] |= near[:-1, :]; o[:-1, :] |= near[1:, :]; o[:, 1:] |= near[:, :-1]; o[:, :-1] |= near[:, 1:]; near = o
    pending = free & ~near; lab = np.zeros(free.shape, bool); unreachable = []
    for j in range(ny):
        for i in range(nx):
            if pending[j, i] and not lab[j, i]:
                comp = _flood(pending, (j, i)); lab |= comp; a = float(comp.sum() * STEP * STEP)
                if a >= 0.5:
                    jj, ii = np.where(comp); unreachable.append(dict(area_m2=round(a, 1), centre=[round(float(xs[ii].mean()), 1), round(float(ys[jj].mean()), 1)], reachable_at_zero_width=bool(reach_any[comp].any())))
    no_access = []
    for inst, it, fp, zb, zt in items:
        if it['ptype'] in ('rug', 'wall') or zb > 0.3 or is_platform(it) or any(k in inst['name'].lower() for k in STRUCT): continue   # things resting on tables/shelves are reached via their support
        cs = [cell(x, y) for x, y in list(fp.buffer(0.5).exterior.coords)[::3]]
        if not any(near[a, b] for a, b in cs): no_access.append(dict(instance_id=inst['id'], name=inst['name']))
    # tables first: a seat's own accompanying table never counts as blocking its front (tucked-in chairs are normal)
    tables = [(i, fp) for i, it, fp, zb, zt in items if it['supports_top'] and 0.45 < zt - zb < 1.3 and it['ptype'] == 'floor' and not any(k in i['name'].lower() for k in SEAT)]
    # front clearance of seats / tall storage
    front = []; obstacles = [(o[0]['id'], o[2]) for o in items if o[1]['ptype'] not in ('rug', 'wall') and o[4] - o[3] > 0.3 and o[3] < 1.4 and not is_platform(o[1])]
    for inst, it, fp, zb, zt in items:
        if it['ptype'] != 'floor' or zb > 1.0: continue
        is_seat = any(k in inst['name'].lower() for k in SEAT)
        if any(k in inst['name'].lower() for k in STRUCT): continue
        if not (is_seat or 1.5 < zt - zb < 4.5): continue
        v = sess.view(inst); fa = math.radians(v['facing_deg']); b = fp.bounds; w = max(0.5, min(b[2] - b[0], b[3] - b[1], 3.0)); ext = max(b[2] - b[0], b[3] - b[1]) / 2
        c = fp.centroid; cx, cy = c.x + math.cos(fa) * (ext * 0.5 + front_depth / 2 + 0.2), c.y + math.sin(fa) * (ext * 0.5 + front_depth / 2 + 0.2)
        rect = affinity.rotate(box(cx - w / 2, cy - front_depth / 2, cx + w / 2, cy + front_depth / 2), math.degrees(fa), origin=(cx, cy))
        others = [g for i, g in obstacles if i != inst['id']]
        if is_seat and tables:
            ti, tfp = min(tables, key=lambda t: t[1].distance(fp))
            if tfp.distance(fp) <= 1.6: others = [g for i, g in obstacles if i not in (ti['id'], inst['id'])]
        blk = unary_union(others).intersection(rect).area if others else 0.0; out = rect.difference(floor).area
        if min(1.0, (blk + out) / rect.area) > 0.3: front.append(dict(instance_id=inst['id'], name=inst['name'], facing_deg=v['facing_deg'], front_blocked_fraction=round(min(1.0, (blk + out) / rect.area), 2), wall_or_edge_part=round(out / rect.area, 2)))
    # seat -> nearest table facing error
    orient = []
    for inst, it, fp, zb, zt in items:
        if not tables or it['ptype'] != 'floor' or zt - zb > 1.8 or not any(k in inst['name'].lower() for k in SEAT): continue
        ti, tfp = min(tables, key=lambda t: t[1].distance(fp)); d = tfp.distance(fp)
        if d > 1.6: continue
        c, tc = fp.centroid, tfp.centroid; want = math.degrees(math.atan2(tc.y - c.y, tc.x - c.x)) % 360
        orient.append(dict(instance_id=inst['id'], name=inst['name'], table_id=ti['id'], distance_m=round(d, 2), facing_error_deg=round(_ang(want, sess.view(inst)['facing_deg']), 1)))
    orient.sort(key=lambda d: -d['facing_error_deg'])
    # wall alignment of tall pieces
    tall = []
    for inst, it, fp, zb, zt in items:
        if it['ptype'] != 'floor' or zt - zb < 1.8 or zb > 0.5 or any(k in inst['name'].lower() for k in ('partition', 'pillar')): continue
        yaw = inst['yaw'] % 90; tall.append(dict(instance_id=inst['id'], name=inst['name'], gap_to_wall_m=round(float(fp.distance(floor.boundary)), 2), off_axis_deg=round(min(yaw, 90 - yaw), 1)))
    # balance
    allfp = [fp for inst, it, fp, zb, zt in items if it['ptype'] != 'wall' and zt - zb > 0.3 and zb < 1.4]; cov = unary_union(allfp) if allfp else None; thirds = []
    for k in range(3):
        band = box(minx + (maxx - minx) * k / 3, -100, minx + (maxx - minx) * (k + 1) / 3, 100).intersection(floor)
        thirds.append(dict(region=('west', 'centre', 'east')[k], floor_m2=round(band.area, 1), covered_fraction=round(cov.intersection(band).area / band.area, 2) if cov is not None and band.area else 0.0))
    # enclosures: floor split by full-height partitions (door partitions counted as solid) + pillars; a room fully closed by them shows up as its own piece.
    walls = [sess.footprint(inst) for inst, it, fp, zb, zt in items if 'partition' in inst['name'].lower() and zt - zb >= 3.0]
    enclosures = []
    if walls:
        cut = floor.difference(unary_union(walls + list(room.pillars_by_level.get(level, []))).buffer(0.03))
        pieces = sorted([g for g in getattr(cut, 'geoms', [cut]) if g.area > 1.0], key=lambda g: -g.area)
        for g in pieces[1:]:
            doors = [inst['id'] for inst, it, fp, zb, zt in items if 'partition' in inst['name'].lower() and fp.buffer(0.1).intersects(g)
                     and ('door' in inst['name'].lower() or not _solid_fp(inst, fp, cat, it).equals(fp))]   # named doors or a measured walkable opening
            enclosures.append(dict(area_m2=round(g.area, 1), bounds=[round(v, 2) for v in g.bounds], door_partitions=doors, note='closed by partitions/pillars/walls' + ('' if doors else '; NO door partition touches it')))
    # raised items with nothing under them (floating is legal in FFXIV; this only lists it so it is a choice, not an accident)
    unsupported = []
    for inst, it, fp, zb, zt in items:
        if it['ptype'] in ('wall', 'ceiling') or zb < 0.05 or floor.exterior.distance(fp) < 0.3: continue   # wall-hung pieces are carried by the wall
        ok = False; c = fp.centroid
        for o, oit, ofp, ozb, ozt in items:
            if o is inst or not ofp.contains(c): continue
            if not oit['surfaces'] and abs(zb - ozt) <= 0.12: ok = True; break   # unmeasured furniture: its top
            for s in oit['surfaces']:
                if abs(zb - (o['pivot'][2] - z0 + s['z'])) > 0.06: continue
                from shapely.geometry import Polygon as _Poly
                from .core import _rot
                pts = [(o['pivot'][0] + _rot(x, y, o['yaw'])[0], o['pivot'][1] + _rot(x, y, o['yaw'])[1]) for x, y in ((s['min'][0], s['min'][1]), (s['max'][0], s['min'][1]), (s['max'][0], s['max'][1]), (s['min'][0], s['max'][1]))]
                if _Poly(pts).buffer(0.03).contains(c): ok = True; break
            if ok: break
        if not ok: unsupported.append(dict(instance_id=inst['id'], name=inst['name'], bottom_above_floor_m=round(zb, 2)))
    # furniture-vs-furniture overlaps: legal in FFXIV but almost always a design accident (the user's "家具疊在一起"); reported for every pair, stacked placements excluded
    overlaps = []
    hard = [(inst, fp, zb, zt) for inst, it, fp, zb, zt in items if it['ptype'] not in ('rug', 'wall', 'ceiling') and zt - zb >= 0.3 and zb < 1.4 and not any(k in inst['name'].lower() for k in STRUCT)]
    for _i in range(len(hard)):
        for _j in range(_i + 1, len(hard)):
            a, b = hard[_i], hard[_j]
            if a[2] >= b[3] - 0.12 or b[2] >= a[3] - 0.12: continue   # one rests on top of the other: legal stacking
            area = a[1].intersection(b[1]).area
            if area > 0.05: overlaps.append(dict(a=a[0]['id'], a_name=a[0]['name'], b=b[0]['id'], b_name=b[0]['name'], overlap_m2=round(area, 2)))
    overlaps.sort(key=lambda d: -d['overlap_m2'])
    # wall_gaps: narrow slits between full-height partitions / pillars / the room wall. Too narrow to walk (<0.6 m) but wide enough
    # (>3 cm) to leak an enclosure, so a room that should be sealed silently is not. Reported with the gap centre so it can be closed.
    wall_gaps = []
    seal = [(inst['id'], sess.footprint(inst)) for inst, it, fp, zb, zt in items
            if any(k in inst['name'].lower() for k in ('partition', 'pillar')) and zt - zb >= 3.0]   # full-height furniture posts seal too
    seal_ids = {sid: k for k, (sid, _) in enumerate(seal)}
    others = seal + [(f'pillar-{k}', g) for k, g in enumerate(room.pillars_by_level.get(level, []))] + [('room-wall', floor.exterior)]
    from shapely.ops import nearest_points
    inner = floor.buffer(-0.05)
    for i, (ida, ga) in enumerate(seal):
        for idb, gb in others:
            if idb == ida or (idb in seal_ids and seal_ids[idb] < i): continue
            dist = ga.distance(gb)
            if 0.03 < dist < 0.6:
                pa, pb = nearest_points(ga, gb)
                mid = Point((pa.x + pb.x) / 2, (pa.y + pb.y) / 2)
                if not inner.contains(mid): continue   # slit runs along the room wall the partition already meets
                if not _slit_open(ga, gb if idb != 'room-wall' else gb.buffer(0.01).intersection(pb.buffer(1.5)), pa, pb,
                                  [g for gid, g in others[:-1] if gid not in (ida, idb)]): continue   # bridged by a third piece
                wall_gaps.append(dict(a=ida, b=idb, width_m=round(dist, 2), at=[round((pa.x + pb.x) / 2, 2), round((pa.y + pb.y) / 2, 2)]))
    wall_gaps.sort(key=lambda g: g['width_m'])
    # entrance_tall: pieces >= 2 m tall within 1.5 m of the arrival lane (3 m wide, 4 m deep from the main door toward the room
    # centre). They read as crowding on arrival even when the lane itself is clear. Interior ground floor only.
    entrance_tall = []
    if level == 'ground' and getattr(cat, 'scope', 'interior') == 'interior' and getattr(room, 'door_xy', None):
        import math as _m
        dx, dy = room.door_xy; c = floor.centroid
        ux, uy = c.x - dx, c.y - dy; n = _m.hypot(ux, uy) or 1.0; ux, uy = ux / n, uy / n
        if abs(ux) > abs(uy): ux, uy = (1.0 if ux > 0 else -1.0), 0.0   # walls are axis-aligned: snap inward direction
        else: ux, uy = 0.0, (1.0 if uy > 0 else -1.0)
        px, py = -uy, ux
        lane = Polygon([(dx + px * 1.5, dy + py * 1.5), (dx - px * 1.5, dy - py * 1.5),
                        (dx - px * 1.5 + ux * 4, dy - py * 1.5 + uy * 4), (dx + px * 1.5 + ux * 4, dy + py * 1.5 + uy * 4)])
        for inst, it, fp, zb, zt in items:
            if it['ptype'] in ('rug', 'ceiling') or zt - zb < 2.0 or zb > 1.0: continue
            dist = fp.distance(lane)
            if dist < 1.5:
                entrance_tall.append(dict(instance_id=inst['id'], name=inst['name'], height_m=round(zt - zb, 2), distance_to_lane_m=round(dist, 2)))
        entrance_tall.sort(key=lambda e: e['distance_to_lane_m'])
    return dict(ok=True, level=level, revision=sess.revision, enclosures=enclosures, wall_gaps=wall_gaps[:40], entrance_tall=entrance_tall[:20], unsupported=unsupported, overlaps=overlaps, note='facts only: nothing here blocks an edit; overlap and tight placements are legal in FFXIV',
                reachability=dict(start=[sx, sy], path_width_m=path_width, walkable_m2=round(float(free.sum() * STEP * STEP), 1), unreachable_regions=unreachable, instances_without_access=no_access[:30]),
                front_clearance=sorted(front, key=lambda d: -d['front_blocked_fraction'])[:30], seat_orientation=orient[:30],
                wall_alignment=dict(tall_items=len(tall), floating_0p3_to_1p2m_off_wall=[t for t in tall if 0.3 < t['gap_to_wall_m'] < 1.2][:30], off_axis=[t for t in tall if 3 < t['off_axis_deg'] < 87][:30]),
                balance=dict(floor_m2=round(floor.area, 1), covered_fraction=round(cov.intersection(floor).area / floor.area, 2) if cov is not None else 0.0, by_third=thirds))


def check_routes(sess, routes, width_m=0.8, level=None):
    """Which furniture bodies intrude on named walking routes. routes = [{name, points:[[x,y],...]}] (polylines, >=2 points).
    A route is a corridor of width_m around the polyline. Counted: floor items whose body is between 0.12 m and 2.0 m above the
    level (rugs, stepping stones and overhead pieces are ignored); door/sliding partitions use their measured walkable opening;
    raised platforms (is_platform) are listed as `steps`, not blockers.
    level selects the floor height (default ground; use basement/upper for those floors). Facts only, never blocks an edit."""
    import math as _m
    from shapely.geometry import LineString
    if not isinstance(width_m, (int, float)) or not (0 < width_m <= 5):
        raise DecoError('BAD_INPUT', 'width_m must be in (0, 5]')
    if not isinstance(routes, list) or not routes:
        raise DecoError('BAD_INPUT', 'routes needs at least one {name, points}')
    room = sess.room; cat = sess.cat
    levels = getattr(room, 'level_z', None) or {'ground': 0.0}
    if level is not None and level not in levels:
        raise DecoError('BAD_INPUT', f'level must be one of {list(levels)}')
    z0 = levels.get(level or 'ground', 0.0)
    out = []
    for r in routes:
        if not isinstance(r, dict) or not isinstance(r.get('name'), str) or not r['name'].strip():
            raise DecoError('BAD_INPUT', 'each route needs a nonempty name')
        pts = r.get('points')
        if not isinstance(pts, list) or len(pts) < 2 or any(not isinstance(p, (list, tuple)) or len(p) != 2 or not all(isinstance(v, (int, float)) and _m.isfinite(v) for v in p) for p in pts):
            raise DecoError('BAD_INPUT', f'route {r.get("name")!r} needs >=2 finite [x,y] points')
        lane = LineString([tuple(map(float, p)) for p in pts]).buffer(width_m / 2.0)
        blockers = []; steps = []
        for inst in sess.instances.values():
            it = cat.item(inst['item_id'])
            if it.get('ptype') in ('rug', 'wall', 'ceiling'): continue
            zb = inst['pivot'][2] + it['lo'][2] - z0; zt = zb + (it['hi'][2] - it['lo'][2])
            if zt - zb <= 0.12 or zt <= 0.12 or zb >= 2.0: continue   # flat pieces (rugs, mats, cushions on a platform) are stepped over
            fp = _solid_fp(inst, sess.footprint(inst), cat, it)
            a = fp.intersection(lane).area
            if a > 1e-3 and is_platform(it):
                steps.append(dict(instance_id=inst['id'], name=inst['name'], height_m=round(zt, 2))); continue
            if a > 1e-3:
                blockers.append(dict(instance_id=inst['id'], name=inst['name'], overlap_m2=round(a, 3)))
        blockers.sort(key=lambda b: -b['overlap_m2'])
        out.append(dict(name=r['name'], width_m=width_m, length_m=round(LineString(pts).length, 2), clear=not blockers, blockers=blockers, steps=steps))
    return out
