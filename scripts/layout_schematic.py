"""Two-floor flat planning/review schematic from a ReMakePlace layout JSON.

Pure schematic: colored bounding footprints drawn from the layout's own
transforms plus catalog-measured bounds. No game textures, meshes, or 3D
rendering; nothing except the output PNG is written.

View is mirrored horizontally by default (+X to the left, +Y up) to match the
app as observed by the user, same convention as MCP renders. Doors and windows
come from the selected interior profile. Labels use greedy collision-avoidance
placement with leader lines. Use plans before placement and after spatial
batches; a full furniture inventory is omitted unless --index is requested.

Usage (project root):
    .venv/Scripts/python.exe scripts/layout_schematic.py <layout.json>
        [--district Mist] [--out DIR] [--no-labels] [--no-mirror] [--index]
"""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import math
import sqlite3
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import MultiPoint, Point

from ffxiv_furniture.deco.core import Room

CATEGORIES = [
    ("Seating", "#6F91AC"),
    ("Tables / worktops", "#C39C63"),
    ("Storage / shelving", "#9986AA"),
    ("Plants", "#72947A"),
    ("Partitions", "#707875"),
    ("Rugs", "#D1C8B6"),
    ("Other / details", "#B8B6AE"),
]
CATEGORY_COLORS = dict(CATEGORIES)
PAPER = "#F5F3ED"
PANEL = "#FFFDF8"
INK = "#283932"
MUTED = "#58675F"
OUTLINE = "#394B41"
ELEVATED_OUTLINE = "#78847B"
ELEVATED_Z = 2.3
GRID_COLOR = "#E6E9E3"
SNAP_TOL = 0.25  # metres; game-extracted profiles carry sub-decimetre skew
MIN_EDGE = 0.12  # metres; adjacent vertices closer than this are mesh noise


def _snap(value: float) -> float:
    nearest = round(value)
    return float(nearest) if abs(value - nearest) <= SNAP_TOL else value


def sanitize_polygon(p):
    """Display-only cleanup of the extracted room profile.

    The local profile comes from the game mesh, so wall vertices carry
    sub-decimetre skew (5.945 instead of 6.0) and 2 cm micro-teeth. At print
    scale those read as wobbly lines and fake diagonals. Furniture footprints
    are untouched; this only squares the outline we draw.
    """
    from shapely.geometry import Polygon as _Polygon

    def clean_ring(coords):
        pts = []
        for x, y in coords:
            sx, sy = _snap(x), _snap(y)
            if pts and abs(sx - pts[-1][0]) < 1e-6 and abs(sy - pts[-1][1]) < 1e-6:
                continue
            pts.append((sx, sy))
        if len(pts) > 2 and pts[0] == pts[-1]:
            pts.pop()
        # Collapse zero-width spikes (out-and-back teeth left by snapping):
        # a vertex whose neighbours coincide adds nothing but a zigzag.
        changed = True
        while changed and len(pts) > 3:
            changed = False
            for i in range(len(pts)):
                prev, nxt = pts[i - 1], pts[(i + 1) % len(pts)]
                if abs(prev[0] - nxt[0]) < 1e-6 and abs(prev[1] - nxt[1]) < 1e-6:
                    del pts[i]
                    changed = True
                    break
        # Collapse mesh-noise micro-edges (6-10 cm steps from the extracted
        # profile) that read as wobbly stair-notches at print scale.
        changed = True
        while changed and len(pts) > 4:
            changed = False
            for i in range(len(pts)):
                prev, nxt = pts[i - 1], pts[(i + 1) % len(pts)]
                d_prev = math.hypot(prev[0] - pts[i][0], prev[1] - pts[i][1])
                if d_prev < MIN_EDGE:
                    del pts[i]
                    changed = True
                    break
        out = []
        for i, pt in enumerate(pts):
            prev, nxt = pts[i - 1], pts[(i + 1) % len(pts)]
            cross = (pt[0] - prev[0]) * (nxt[1] - pt[1]) - (pt[1] - prev[1]) * (nxt[0] - pt[0])
            if abs(cross) > 1e-6:
                out.append(pt)
        return out

    if p.is_empty or p.geom_type == "MultiPolygon":
        parts = p.geoms if p.geom_type == "MultiPolygon" else []
        from shapely.geometry import MultiPolygon as _MultiPolygon

        return _MultiPolygon([sanitize_polygon(part) for part in parts if not part.is_empty])
    exterior = clean_ring(p.exterior.coords)
    if len(exterior) < 3:
        return p
    interiors = [clean_ring(ring.coords) for ring in p.interiors]
    interiors = [ring for ring in interiors if len(ring) >= 3]
    try:
        cleaned = _Polygon(exterior, interiors)
    except Exception:
        return p
    return cleaned if not cleaned.is_empty else p
LABEL_MIN_AREA = 0.35


def categorize(name: str) -> str:
    s = name.lower()
    if any(w in s for w in ["partition", "door partition", "wooden beam"]):
        return "Partitions"
    if any(w in s for w in ["rug", "carpet", "flooring mat"]):
        return "Rugs"
    if any(w in s for w in ["sofa", "chair", "stool", "bench", "bed", "couch"]):
        return "Seating"
    if any(w in s for w in ["table", "desk", "counter", "kitchen", "sink", "dresser"]):
        return "Tables / worktops"
    if any(w in s for w in ["shelf", "bookcase", "cupboard", "cabinet", "wardrobe"]):
        return "Storage / shelving"
    if any(
        w in s
        for w in ["plant", "tree", "ivy", "flower", "foliage", "shrub", "greenery", "planter"]
    ):
        return "Plants"
    return "Other / details"


def load_items(layout: dict, db_path: Path) -> list[dict]:
    scale = layout["interiorScale"]
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = []
        for index, item in enumerate(layout["interiorFurniture"], 1):
            rec = con.execute(
                "select * from furniture_bounds where id=?", (item["itemId"],)
            ).fetchone()
            if rec is None:
                raise SystemExit(f"Missing measured bounds for itemId {item['itemId']}")
            loc = np.array(item["transform"]["location"], float) / scale
            q = np.array(item["transform"]["rotation"], float)
            q /= np.linalg.norm(q)
            x, y, z, w = q
            rotation = np.array(
                [
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
                ]
            )
            lo = [rec["min_x"], rec["min_y"], rec["min_z"]]
            hi = [rec["max_x"], rec["max_y"], rec["max_z"]]
            corners = np.array(
                [[a, b, c] for a in [lo[0], hi[0]] for b in [lo[1], hi[1]] for c in [lo[2], hi[2]]]
            )
            corners = (corners * np.array(item["transform"]["scale"])) @ rotation.T + loc
            footprint = MultiPoint(corners[:, :2]).convex_hull
            level = "basement" if loc[2] < -3 else "ground"
            # Medium/Large upper floors are at +7 m. Use the transformed bottom,
            # not a high pivot, so tall ground-floor panels remain downstairs.
            if layout.get("houseSize") in ("Medium", "Large") and float(corners[:, 2].min()) >= 6.4:
                level = "upper"
            rows.append(
                dict(
                    id=index,
                    name=item["name"],
                    item_id=item["itemId"],
                    level=level,
                    poly=footprint,
                    loc=loc,
                    category=categorize(item["name"]),
                    height=float(corners[:, 2].min()) - {"basement": -7.0, "ground": 0.0, "upper": 7.0}[level],
                )
            )
        return rows
    finally:
        con.close()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("C:/Windows/Fonts/" + ("segoeuib.ttf" if bold else "segoeui.ttf"), size)
    except OSError:
        return ImageFont.load_default()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layout", type=Path)
    ap.add_argument("--district", default=None, help="Interior style (from layout fixtures if omitted)")
    ap.add_argument("--db", type=Path, default=ROOT / "data/furniture.sqlite3")
    ap.add_argument("--out", type=Path, default=None, help="Defaults to the layout's renders/ directory")
    ap.add_argument("--no-labels", action="store_true")
    ap.add_argument("--index", action="store_true", help="Include an optional furniture inventory (omitted from planning views by default)")
    ap.add_argument("--no-mirror", action="store_true", help="Raw world axes (+X right) instead of the app-mirrored view")
    args = ap.parse_args()

    source = args.layout.resolve()
    data = source.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    layout = json.loads(data)
    if str(args.db).endswith("furniture.sqlite3"):
        protected = [source, args.db, source.parent / "state.json"]
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.exists()}
    else:
        before = None

    district = args.district
    if district is None:
        for fixture in layout.get("interiorFixture") or []:
            if str(fixture.get("type", "")).lower() == "district" and fixture.get("name"):
                district = fixture["name"]
                break
    room = Room(style=district or "Shirogane", house_size=layout["houseSize"])
    # Square the game-extracted profile for display only (see sanitize_polygon).
    room.polys = {lvl: sanitize_polygon(poly) for lvl, poly in room.polys.items()}
    items = load_items(layout, args.db)
    counts = collections.Counter(r["level"] for r in items)
    floors = [level for level in room.levels if level in room.polys and not room.polys[level].is_empty]
    if set(counts) - set(floors):
        raise SystemExit(f"Furniture on unsupported schematic floors: {sorted(set(counts)-set(floors))}")

    W, H = 3200, 3080 if args.index else 1800
    panel_w, panel_h = 1500, 1340
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    f20, f23, f26, f32, f48 = font(20), font(23), font(26), font(32, True), font(48, True)
    title = source.stem.replace("_", " ").rstrip(" -0123456789.rR")
    d.text((80, 45), title.upper(), font=f48, fill=INK)
    revision = "r?" if "-" not in source.stem else source.stem.rsplit("-", 1)[-1]
    d.text(
        (82, 112),
        f"{revision}  /  {len(floors)}-FLOOR SCHEMATIC  /  {layout['houseSize']} - {district or 'Shirogane'} interior",
        font=f26,
        fill=MUTED,
    )
    mirror = not args.no_mirror
    view_note = (
        "View matches the app: +X to the LEFT, +Y up (coordinates unchanged)."
        if mirror
        else "Raw world axes: +X right, +Y up."
    )
    d.text(
        (82, 157),
        "Positioned from the layout JSON. Rotated bounding footprints only; no textures, models, or 3D rendering. "
        + view_note,
        font=f23,
        fill=MUTED,
    )

    # Grid canvas: 1 m graph paper is the panel background, aligned to whole
    # world meters. The floor sits on that canvas (centered, then nudged so
    # furniture that pokes through walls stays inside the panel). Furniture
    # intentionally outside the floor outline is legal FF14 placement.
    pad_side, pad_top, pad_bottom = 40, 80, 100
    avail_w, avail_h = panel_w - 2 * pad_side, panel_h - pad_top - pad_bottom
    unions = {}
    for level in floors:
        bounds = [room.polys[level].bounds] + [r["poly"].bounds for r in items if r["level"] == level]
        unions[level] = (
            min(b[0] for b in bounds) - 0.4,
            min(b[1] for b in bounds) - 0.4,
            max(b[2] for b in bounds) + 0.4,
            max(b[3] for b in bounds) + 0.4,
        )
    common = min(
        min(avail_w / (u[2] - u[0]) for u in unions.values()),
        min(avail_h / (u[3] - u[1]) for u in unions.values()),
        140.0,
    )

    for panel_index, level in enumerate(floors):
        panel_x = 65 + panel_index * (panel_w + 70)
        panel_y = 220
        d.rounded_rectangle(
            (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), radius=22, fill=PANEL, outline="#D7DDD5", width=2
        )
        d.text(
            (panel_x + 40, panel_y + 25),
            {"ground": "GROUND FLOOR", "upper": "UPPER FLOOR", "basement": "BASEMENT"}[level] + f"  /  {counts[level]} items",
            font=f32,
            fill=INK,
        )
        # Center on the floor footprint (not the furniture union), then shift
        # minimally so every drawn item stays inside the panel.
        fb = room.polys[level].bounds
        cx, cy = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
        origin_x = panel_x + panel_w / 2
        origin_y = panel_y + pad_top + avail_h / 2

        def to_px(a: float, c: float, ox: float, oy: float):
            px = ox - (a - cx) * common if mirror else ox + (a - cx) * common
            return (px, oy - (c - cy) * common)

        left_limit, right_limit = panel_x + pad_side, panel_x + panel_w - pad_side
        top_limit, bottom_limit = panel_y + pad_top, panel_y + panel_h - pad_bottom
        ux = [to_px(a, cy, origin_x, origin_y)[0] for a in (unions[level][0], unions[level][2])]
        uy = [to_px(cx, c, origin_x, origin_y)[1] for c in (unions[level][1], unions[level][3])]
        if min(ux) < left_limit:
            origin_x += left_limit - min(ux)
        if max(ux) > right_limit:
            origin_x -= max(ux) - right_limit
        if min(uy) < top_limit:
            origin_y += top_limit - min(uy)
        if max(uy) > bottom_limit:
            origin_y -= max(uy) - bottom_limit

        def xy(a: float, c: float):
            px = origin_x - (a - cx) * common if mirror else origin_x + (a - cx) * common
            return (px, origin_y - (c - cy) * common)

        def stroke_closed(pts, color, width):
            pts = list(pts)
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            if len(pts) < 2:
                return
            # Plain segments plus vertex dots: PIL's joint="curve" bulges at
            # corners and makes thick wall outlines read as wobbly lines.
            for a, b in zip(pts, pts[1:] + pts[:1]):
                d.line([a, b], fill=color, width=width)
            half = max(width / 2, 1)
            for px, py in pts:
                # Square patch per vertex: PIL leaves perpendicular square
                # caps on each segment; centred squares swallow every cap so
                # corners stay clean at any angle.
                d.rectangle((px - half, py - half, px + half, py + half), fill=color)

        def draw_poly(p, fill=None, outline=None, width=1):
            if p.is_empty:
                return
            if p.geom_type == "MultiPolygon":
                for part in p.geoms:
                    draw_poly(part, fill, outline, width)
                return
            coords = [xy(a, c) for a, c in p.exterior.coords]
            if fill:
                d.polygon(coords, fill=fill)
            if outline:
                stroke_closed(coords, outline, width)
            for ring in p.interiors:
                d.polygon([xy(a, c) for a, c in ring.coords], fill=PANEL)

        def draw_grid():
            inner = (panel_x + 3, panel_y + 3, panel_x + panel_w - 3, panel_y + panel_h - 3)
            wx_left = cx + (origin_x - inner[2]) / common if mirror else cx + (inner[0] - origin_x) / common
            wx_right = cx + (origin_x - inner[0]) / common if mirror else cx + (inner[2] - origin_x) / common
            wy_bottom = cy - (inner[3] - origin_y) / common
            wy_top = cy - (inner[1] - origin_y) / common
            for gx in range(math.floor(wx_left) - 1, math.ceil(wx_right) + 1):
                px = xy(gx, 0)[0]
                if inner[0] <= px <= inner[2]:
                    d.line([(px, inner[1]), (px, inner[3])], fill="#E6E9E3", width=1)
            for gy in range(math.floor(wy_bottom) - 1, math.ceil(wy_top) + 1):
                py = xy(0, gy)[1]
                if inner[1] <= py <= inner[3]:
                    d.line([(inner[0], py), (inner[2], py)], fill="#E6E9E3", width=1)

        draw_poly(room.polys[level], fill="#F0F0E8")
        draw_grid()
        # Re-mask the void holes (stair openings etc.) so the grid does not read as floor there.
        for ring in getattr(room.polys[level], "interiors", []):
            d.polygon([xy(a, c) for a, c in ring.coords], fill=PANEL)
        for stair in room.profile.stair_footprints(level):
            stair = sanitize_polygon(stair)
            draw_poly(stair, fill="#E0E3DD", outline="#A0AAA1", width=2)
            mid = stair.centroid
            hx, hy = xy(mid.x, mid.y)
            d.text((hx - 24, hy - 11), "STAIRS", font=font(18, True), fill="#66705F")

        # Doors and windows from the selected interior profile (ground floor only for Small).
        placed: list[tuple[float, float, float, float]] = []
        if level == "ground":
            for opening in room.openings:
                ox, oy = opening["xy"]
                along = opening.get("along", "x")
                hw = opening["half_width"]
                if along == "x":
                    corners_box = [(ox - hw, oy - 0.12), (ox + hw, oy + 0.12)]
                else:
                    corners_box = [(ox - 0.12, oy - hw), (ox + 0.12, oy + hw)]
                if opening["kind"] == "door":
                    d.polygon([xy(*c) for c in corners_box], fill=PANEL)
                    # One jamb line along the wall centreline (not the box
                    # diagonal, which read as a stray slanted stroke).
                    if along == "x":
                        jam = [xy(ox - hw, oy), xy(ox + hw, oy)]
                    else:
                        jam = [xy(ox, oy - hw), xy(ox, oy + hw)]
                    d.line(jam, fill=OUTLINE, width=4)
                    label = "ENTRY DOOR"
                    tw = d.textlength(label, font=f23)
                    (x1, y1), (x2, y2) = jam
                    door_mid = ((x1 + x2) / 2, (y1 + y2) / 2)
                    lx, ly = door_mid[0] - tw / 2, door_mid[1] - (40 if oy > cy else -12)
                    d.rounded_rectangle((lx - 8, ly - 4, lx + tw + 8, ly + 30), radius=5, fill=PANEL, outline=OUTLINE, width=2)
                    d.text((lx, ly), label, font=f23, fill=INK)
                    placed.append((lx - 8, ly - 4, lx + tw + 8, ly + 30))
                else:
                    d.polygon([xy(*c) for c in corners_box], fill="#BBD4E4", outline="#7E9DB4", width=2)

        subset = [r for r in items if r["level"] == level]
        subset.sort(key=lambda r: (r["category"] != "Rugs", r["height"] > ELEVATED_Z, -r["poly"].area))
        for r in subset:
            p = r["poly"]
            col = CATEGORY_COLORS[r["category"]]
            if p.geom_type != "Polygon":
                px, py = xy(*r["loc"][:2])
                d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=col)
                continue
            elevated = r["height"] > ELEVATED_Z
            draw_poly(p, fill=None if elevated else col, outline=ELEVATED_OUTLINE if elevated else "#FAF9F5", width=2)

        # Greedy, collision-free numbering labels (drawn above footprints).
        if not args.no_labels:
            candidates = [r for r in subset if r["poly"].area >= LABEL_MIN_AREA and r["height"] <= ELEVATED_Z]
            candidates.sort(key=lambda r: -r["poly"].area)
            for r in candidates:
                label = str(r["id"])
                tw = d.textlength(label, font=f20)
                wbox, hbox = tw / 2 + 5, 13
                c = r["poly"].centroid
                bx, by = xy(c.x, c.y)
                panel_box = (panel_x + 8, panel_y + 70, panel_x + panel_w - 8, panel_y + panel_h - 90)

                def free(box):
                    return all(
                        box[2] < pb[0] or box[0] > pb[2] or box[3] < pb[1] or box[1] > pb[3] for pb in placed
                    ) and (box[0] >= panel_box[0] and box[1] >= panel_box[1] and box[2] <= panel_box[2] and box[3] <= panel_box[3])

                offsets = [(0, 0)]
                steps = [(0, -26), (0, 26), (34, 0), (-34, 0), (24, -20), (24, 20), (-24, -20), (-24, 20), (0, -52), (0, 52), (60, 0), (-60, 0)]
                found = None
                for dx, dy in offsets + [(dx * 2, dy * 2) for dx, dy in steps]:
                    box = (bx + dx - wbox, by + dy - hbox, bx + dx + wbox, by + dy + hbox)
                    if free(box):
                        found = (box, dx, dy)
                        break
                if found is None:
                    continue
                box, dx, dy = found
                if dx or dy:
                    d.line([(bx, by), (bx + dx, by + dy)], fill="#93A196", width=1)
                    d.ellipse((bx - 2, by - 2, bx + 2, by + 2), fill="#5C6E60")
                d.rounded_rectangle(box, radius=4, fill=PANEL, outline="#C9D2C8", width=1)
                d.text((box[0] + 5, box[1] - 1), label, font=f20, fill=INK)
                placed.append(box)

        draw_poly(room.polys[level], outline=OUTLINE, width=5)
        sx, sy = panel_x + 48, panel_y + panel_h - 65
        d.line((sx, sy, sx + 2 * common, sy), fill=OUTLINE, width=5)
        for dx in [0, common, 2 * common]:
            d.line((sx + dx, sy - 8, sx + dx, sy + 8), fill=OUTLINE, width=3)
        d.text((sx, sy + 13), "0        1        2 m", font=f20, fill=MUTED)
        d.text((panel_x + panel_w - 240, sy + 5), "+X left / +Y up" if mirror else "+X right / +Y up", font=f20, fill=MUTED)

    x = 85
    for label, col in CATEGORIES:
        d.rounded_rectangle((x, 1598, x + 25, 1623), radius=4, fill=col)
        d.text((x + 36, 1594), label, font=f23, fill=OUTLINE)
        x += int(d.textlength(label, font=f23)) + 83
    d.rounded_rectangle((x, 1598, x + 25, 1623), radius=4, fill="#E0E3DD", outline="#A0AAA1", width=2)
    d.text((x + 36, 1594), "Stairs", font=f23, fill=OUTLINE)
    x += int(d.textlength("Stairs", font=f23)) + 83
    d.rectangle((x, 1601, x + 25, 1620), fill="#BBD4E4", outline="#7E9DB4", width=2)
    d.text((x + 36, 1594), "Window", font=f23, fill=OUTLINE)

    if args.index:
        d.text((85, 1665), "FURNITURE INDEX", font=f32, fill=INK)
        d.text(
            (85, 1715),
            "Numbers use JSON order. G = ground, U = upper, B = basement. Small props and elevated items are drawn but may skip the "
            "numbered tag when no collision-free spot exists; every item remains in this index.",
            font=f20,
            fill=MUTED,
        )
        for i, r in enumerate(items):
            col, row = divmod(i, 28)
            x = 85 + col * 785
            y = 1775 + row * 35
            label = f'{r["id"]:03d}  {dict(ground="G",upper="U",basement="B")[r["level"]]}  {r["name"]}'
            while d.textlength(label, font=f20) > 745:
                label = label[:-2] + "…"
            d.text((x, y), label, font=f20, fill=OUTLINE)
    d.text(
        (85, H - 95),
        "SCHEMATIC ONLY - Bounding footprints can overlap intentionally. Not collision, clearance, or in-game placement validation.",
        font=f23,
        fill=MUTED,
    )
    d.text(
        (85, H - 56),
        "Floor outline, doors, windows, and stairs follow the selected local profile; floor assignment is inferred from placement height. Source layout unchanged.",
        font=f20,
        fill=MUTED,
    )

    out_dir = args.out or (source.parent / "renders")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"{source.stem}-schematic-{stamp}.png"
    img.save(out)

    assert len(items) == len(layout["interiorFurniture"]) == sum(counts.values())
    if before is not None:
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.exists()}
        assert before == after, "Source/database/session changed"
    print(
        json.dumps(
            {
                "image": str(out),
                "items": len(items),
                "floors": dict(counts),
                "mirrored_view": mirror,
                "labels": not args.no_labels,
                "furniture_index": args.index,
                "source_hash": source_hash,
                "source_db_state_unchanged": before is not None,
                "uses_game_textures": False,
                "uses_3d_rendering": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
