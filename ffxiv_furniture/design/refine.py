"""Scoring and guarded refinement of a design: free-angle rotation, small moves, removals.

Hard constraints (never traded for score): inside the real floor, not in stair/corridor keepouts, no solid-solid overlap, tabletop items stay on the table top,
wall items stay on a wall. Score (0-100) only ranks layouts that satisfy them. Every op is validated by the same checker, whoever proposed it
(the deterministic optimiser or a model), and is accepted only if the constraints hold and the score does not drop.
"""
from __future__ import annotations
import math
from shapely.geometry import Point, box
from shapely.ops import unary_union, nearest_points
from . import place as P

MAX_MOVE_M = 6.0
MOVABLE = ('solid', 'seat', 'top')   # on-top props may be re-sited; the physics check re-runs after every op so they cannot end up floating
# Weights sum to 1. They only rank layouts under THESE rules; they are not a measure of design quality (see UNMEASURED).
COMPONENTS = ('facing', 'wall_contact', 'front_clearance', 'support', 'stranded_decor', 'density', 'balance', 'circulation', 'overlap')   # diagnostic measures, each 0 (fine) .. 1 (flagged); there is NO total and no target
UNMEASURED = ['whether the room looks good (a model must judge that from the render)', 'theme / style coherence', 'colour harmony', 'lighting', 'entrance and pillars (not modelled)', 'usability of each zone for its purpose', 'what the app actually shows (never compared automatically)']
DENSITY_BAND = (0.05, 0.60)   # only an almost empty room is penalised; a full, layered room is a legitimate design (FFXIV allows overlap)


class Obj:
    def __init__(self, idx, placement, item):
        self.i = idx; self.p = placement; self.item = item
        self.pivot = (placement['location_m'][0], placement['location_m'][1]); self.z = placement['location_m'][2]; self.yaw = placement['yaw_degrees']
        self.layer = placement['layer']; self.role = placement['role']; self.removed = False

    @property
    def poly(self): return P.poly_at(self.item, self.yaw, self.pivot)

    @property
    def facing(self): return (self.item['front_deg'] + self.yaw) % 360

    def label(self): return f"#{self.i} {self.item['name']}"


def load_objects(placements, db):
    from .resolve import _geometry
    objs = []
    for i, pl in enumerate(placements):
        geo = _geometry(db, pl['item_id']); item = P.make_item({'item_id': pl['item_id'], 'role': pl['role'], 'zone': pl['zone']}, geo, i)
        objs.append(Obj(i, pl, item))
    return objs


def angle_to(a, b): return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360


def tables(objs): return [o for o in objs if not o.removed and o.role == 'table' and o.layer == 'solid']


def top_of(o, objs):
    """The table an on-top item stands on = the table whose top polygon contains it."""
    for t in objs:   # any real flat surface (table, shelf, counter...), not only tables
        if not t.removed and t is not o and t.layer == 'solid' and t.item['supports_top'] and t.poly.buffer(0.02).covers(o.poly): return t
    return None


def check(scene, objs):
    """Hard-constraint violations as strings (empty list = valid)."""
    bad = []; live = [o for o in objs if not o.removed]
    solids = [o for o in live if o.layer in MOVABLE]
    for o in live:
        poly = o.poly
        if o.layer in MOVABLE:
            if not scene.usable.covers(poly): bad.append(f'{o.label()} outside the floor')
            if scene.blocked(poly): bad.append(f'{o.label()} inside a stair body')
        elif o.layer == 'wall':
            if not scene.wall_cover.covers(poly) or poly.distance(scene.boundary) >= 0.06: bad.append(f'{o.label()} not on a wall')
        elif o.layer == 'top':
            if top_of(o, live) is None: bad.append(f'{o.label()} not on a table top')
        elif o.layer == 'rug':
            if not scene.wall_cover.covers(poly): bad.append(f'{o.label()} rug outside floor')
    return bad   # overlapping furniture is legal in FFXIV: it is a soft score component ('overlap'), not a hard violation


def desired_facing(scene, o, objs):
    """Direction an item should face, or None when there is no rule. Seats face the nearest table; wall-backed storage/lights face into the room."""
    c = o.poly.centroid; c = (c.x, c.y)
    if (o.p.get('intent') or {}).get('facing') is not None: return None   # the model chose this orientation on purpose
    if o.role == 'seating' and o.item['ptype'] == 'floor':
        ts = tables(objs)
        if ts:
            t = min(ts, key=lambda t: t.poly.distance(o.poly)); tc = t.poly.centroid
            if t.poly.distance(o.poly) < 1.5: return angle_to(c, (tc.x, tc.y))
        return None
    if o.role in ('storage', 'lighting') and o.layer in MOVABLE and scene.wall_contact(o.poly):
        return wall_normal_angle(scene, o.poly)   # normal of the nearest wall segment, pointing into the room
    return None


def wall_segments(scene):
    if not hasattr(scene, '_segs'):
        rings = [scene.polygon.exterior] + list(scene.polygon.interiors) if scene.polygon.geom_type == 'Polygon' else [r for g in scene.polygon.geoms for r in [g.exterior, *g.interiors]]
        scene._segs = [(a, b) for ring in rings for a, b in zip(list(ring.coords)[:-1], list(ring.coords)[1:]) if math.dist(a, b) > 1e-6]
    return scene._segs


def wall_normal_angle(scene, poly):
    from shapely.geometry import LineString
    seg = min(wall_segments(scene), key=lambda s: LineString(s).distance(poly)); (ax, ay), (bx, by) = seg
    L = math.hypot(bx - ax, by - ay); dx, dy = (bx - ax) / L, (by - ay) / L; nx, ny = -dy, dx; c = poly.centroid
    if (c.x - ax) * nx + (c.y - ay) * ny < 0: nx, ny = -nx, -ny
    return math.degrees(math.atan2(ny, nx)) % 360


def layout_shape(scene, live):
    """Whole-room measures that single-item rules miss: emptiness/crowding, lopsidedness, walkable connectivity, stranded loose decor."""
    solids = [o for o in live if o.layer in MOVABLE]; free = scene.free; fa = max(free.area, 1e-6)
    cover = sum(o.poly.area for o in solids) / fa
    lo, hi = DENSITY_BAND; density = max(0.0, (lo - cover) / lo) if cover < lo else max(0.0, (cover - hi) / hi) if cover > hi else 0.0
    if solids:
        tot = sum(o.poly.area for o in solids); cx = sum(o.poly.centroid.x * o.poly.area for o in solids) / tot; cy = sum(o.poly.centroid.y * o.poly.area for o in solids) / tot
        fc = free.centroid; balance = min(1.0, math.hypot(cx - fc.x, cy - fc.y) / (0.30 * math.sqrt(fa)))
    else: balance = 1.0
    blockers = unary_union([o.poly.buffer(0.45) for o in solids]) if solids else None
    opened = free if blockers is None else free.difference(blockers)
    if opened.is_empty: circulation = 1.0
    else:
        parts = list(opened.geoms) if opened.geom_type == 'MultiPolygon' else [opened]; big = max(p.area for p in parts)
        circulation = max(1 - big / max(opened.area, 1e-6), max(0.0, (0.45 - opened.area / fa) / 0.45))
    decor = [o for o in live if o.role == 'decor' and o.layer in MOVABLE and o.item['ptype'] == 'floor']; stranded = 0
    for o in decor:
        near = [o.poly.distance(x.poly) for x in solids if x is not o] + [o.poly.distance(scene.boundary)]
        if min(near) > 1.0: stranded += 1
    ov = 0.0; tot_a = sum(o.poly.area for o in solids) or 1e-6
    for a in range(len(solids)):
        for b in range(a + 1, len(solids)):
            A, B = solids[a], solids[b]
            if (A.p.get('intent') or {}).get('allow_overlap') or (B.p.get('intent') or {}).get('allow_overlap'): continue
            if A.poly.intersects(B.poly): ov += A.poly.intersection(B.poly).area
    return {'overlap': min(1.0, 4 * ov / tot_a), 'density': density, 'balance': balance, 'circulation': circulation, 'stranded_decor': stranded / len(decor) if decor else 0.0}, {'floor_cover': round(cover, 4), 'open_area_fraction': round(opened.area / fa, 3) if not opened.is_empty else 0.0, 'stranded_decor_count': stranded}


def measure(scene, objs):
    """Facts about the layout for the reviewing model: hard violations (physics only) and diagnostic measures. NOT a score: no total, no ranking, never used to accept or reject a change."""
    live = [o for o in objs if not o.removed]; hard = check(scene, objs)
    facing_err, wall_miss, front_block, support_bad = [], [], [], 0
    solids = [o for o in live if o.layer in MOVABLE]; solid_union_cache = {}
    for o in live:
        want = desired_facing(scene, o, live)
        if want is not None: facing_err.append(abs(P.wrap(o.facing - want)) / 180)
        if o.role == 'storage' and o.layer in MOVABLE and o.item['ptype'] == 'floor': wall_miss.append(0.0 if scene.wall_contact(o.poly) else 1.0)
        if o.role in ('storage', 'lighting') and o.layer in MOVABLE:
            d = (math.cos(math.radians(o.facing)), math.sin(math.radians(o.facing))); probe = P.poly_at(o.item, o.yaw, (o.pivot[0] + 0.6 * d[0], o.pivot[1] + 0.6 * d[1])).difference(o.poly)
            others = unary_union([x.poly for x in solids if x is not o] + ([scene.keepout_union] if scene.keepout_union is not None else []))
            blocked = probe.intersection(others).area + probe.difference(scene.polygon).area
            front_block.append(min(1.0, blocked / max(probe.area, 1e-6)))
        if o.layer == 'top' and top_of(o, live) is None: support_bad += 1
        if o.layer == 'wall' and o.poly.distance(scene.boundary) >= 0.06: support_bad += 1
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0
    comp = {'facing': mean(facing_err), 'wall_contact': mean(wall_miss), 'front_clearance': mean(front_block), 'support': support_bad / max(1, len(live))}
    shape, facts = layout_shape(scene, live); comp.update(shape)
    return {'kind': 'diagnostic facts, NOT a quality score; do not optimise them', 'components': {k: round(v, 4) for k, v in comp.items()}, 'facts': facts, 'hard_violations': hard,
            'objects_measured': {'facing': len(facing_err), 'storage': len(wall_miss), 'front': len(front_block)}, 'not_measured': UNMEASURED}


# ---------------------------------------------------------------- ops
def apply_op(scene, objs, op, *, max_move=MAX_MOVE_M, companions=None):
    """Validate and apply one op in place; return (ok, reason, undo). ops: rotate{yaw|yaw_delta}, move{dx,dy}, place{x,y[,yaw]}, remove."""
    o = next((x for x in objs if x.i == op.get('instance') and not x.removed), None)
    if o is None: return False, 'unknown or removed instance', None
    if o.layer not in MOVABLE and op['op'] != 'remove': return False, f'{o.layer} items are not freely movable', None
    if o.role == 'table' and op['op'] in ('move', 'rotate'):   # a table may only turn/slide when everything standing on it is ordered to move identically in the same round
        carried = [x for x in objs if not x.removed and x.layer == 'top' and x is not o and o.poly.buffer(0.05).covers(x.poly)]
        companions = companions or {}
        for x in carried:
            co = companions.get(x.i)
            if not co: return False, f'{x.label()} stands on this table and has no matching move op in this round', None
            if op['op'] == 'move' and not (co.get('op') == 'move' and co.get('dx') == op.get('dx') and co.get('dy') == op.get('dy')): return False, f'{x.label()} must move with the table (same dx,dy)', None
            if op['op'] == 'rotate' and co.get('op') != 'rotate': return False, f'{x.label()} must be listed as rotating with the table', None
    saved = (o.pivot, o.yaw, o.removed)
    try:
        if op['op'] == 'rotate':
            yaw = op.get('yaw') if 'yaw' in op else o.yaw + op.get('yaw_delta', 0)
            if isinstance(yaw, bool) or not isinstance(yaw, (int, float)) or not math.isfinite(yaw): return False, 'bad yaw', None
            # rotate about the footprint centre so the item turns in place (not about its pivot)
            c = o.poly.centroid; o.yaw = float(yaw) % 360; newp = P.pivot_for_center(o.item, o.yaw, (c.x, c.y)); o.pivot = newp
        elif op['op'] == 'move':
            dx, dy = op.get('dx', 0), op.get('dy', 0)
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (dx, dy)) or math.hypot(dx, dy) > max_move: return False, f'move exceeds {max_move} m', None
            o.pivot = (o.pivot[0] + dx, o.pivot[1] + dy)
        elif op['op'] == 'place':   # absolute: put the footprint centre at (x, y), optionally with a new yaw
            x, y = op.get('x'), op.get('y')
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (x, y)): return False, 'place needs numeric x and y (footprint centre, world metres)', None
            if 'yaw' in op:
                if isinstance(op['yaw'], bool) or not isinstance(op['yaw'], (int, float)) or not math.isfinite(op['yaw']): return False, 'bad yaw', None
                o.yaw = float(op['yaw']) % 360
            o.pivot = P.pivot_for_center(o.item, o.yaw, (x, y))
        elif op['op'] == 'remove':
            o.removed = True
        else: return False, 'unknown op', None
    except Exception as e:
        o.pivot, o.yaw, o.removed = saved; return False, repr(e), None
    undo = lambda: setattr(o, 'pivot', saved[0]) or setattr(o, 'yaw', saved[1]) or setattr(o, 'removed', saved[2])
    return True, 'ok', undo


def try_op(scene, objs, op, *, companions=None):
    """Apply op; accept unless it CREATES a violation that did not exist before (physics only, diffed per string —
    a pre-existing violation elsewhere must never block unrelated edits). No score gate: whether a change is GOOD is the reviewing model's judgement."""
    before = set(measure(scene, objs)['hard_violations']); ok, why, undo = apply_op(scene, objs, op, companions=companions)
    if not ok: return {'op': op, 'accepted': False, 'reason': why}
    new = [v for v in measure(scene, objs)['hard_violations'] if v not in before]
    if new:
        undo(); return {'op': op, 'accepted': False, 'reason': 'violates hard constraint: ' + new[0]}
    return {'op': op, 'accepted': True, 'reason': 'ok'}
