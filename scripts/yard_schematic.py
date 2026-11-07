"""Flat yard plan for an exported layout's exteriorFurniture: measured footprints on the native plot outline, the house
void, gate and front door from the native exterior actors. SVG by default (vector, small); --format jpg for raster-only
viewers. Read-only: the layout, catalog DB and session state are hash-checked unchanged. No textures or 3D rendering.

    python scripts/yard_schematic.py <layout.json> [--limit 20] [--max-patch 7.2] [--format svg|jpg] [--out DIR]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from layout_schematic import font, load_items  # noqa: E402
from ffxiv_furniture.exteriors import ExteriorProfile, native_exterior_actors  # noqa: E402

PAPER, PANEL, GRID, INK, MUTED, EDGE = "#F8F6F0", "#EFF1E9", "#DDE2D8", "#34483B", "#526358", "#435E4B"
DEFAULT_LIMIT = {"Small": 40, "Medium": 60, "Large": 80}


def colour(name):
    n = name.lower()
    if "aetheryte" in n: return "#56B4CE"
    if "stone" in n and ("step" in n or "path" in n): return "#D6CDB5"
    if "paving" in n: return "#C6947D"
    if "light" in n or "lamp" in n or "lantern" in n: return "#D1B75B"
    if any(w in n for w in ("flower", "shrub", "planter", "hedge", "bamboo", "moss")): return "#94A17D"
    return "#B39977"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("layout", type=Path)
    ap.add_argument("--db", type=Path, default=ROOT / "data/furniture.sqlite3")
    ap.add_argument("--out", type=Path, default=None, help="Defaults to the layout's renders/ directory")
    ap.add_argument("--limit", type=int, default=None, help="Outdoor furnishing budget to print (default: the house size cap)")
    ap.add_argument("--max-patch", default=None, help="Patch restriction to print, e.g. 7.2")
    ap.add_argument("--format", choices=("svg", "jpg"), default="svg")
    a = ap.parse_args()

    src = a.layout.resolve()
    protected = [p for p in (src, a.db.resolve(), src.parent / "state.json") if p.exists()]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    raw = src.read_bytes()
    layout = json.loads(raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw)
    size = layout.get("houseSize", "Small")
    budget = a.limit or DEFAULT_LIMIT.get(size, 40)
    rows = load_items(dict(layout, interiorFurniture=layout["exteriorFurniture"], interiorScale=layout["exteriorScale"]), a.db)
    yard = ExteriorProfile(size, layout["exteriorFixture"], db_path=a.db).polygon()
    actors = {x["name"]: x for x in native_exterior_actors(size)}
    marks = [(actors[k]["translation_m"][0], actors[k]["translation_m"][1], label)
             for k, label in (("OutsideEntrance", "GATE"), ("MainDoor", "DOOR")) if k in actors]

    W, H = 1600, 1550
    box = (50, 180, 1550, 1410)
    x0, y0, x1, y1 = yard.bounds
    S = min((box[2] - box[0] - 60) / (x1 - x0), (box[3] - box[1] - 60) / (y1 - y0))
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2

    def xy(x, y):   # +X to the LEFT (app view), +Y up
        return cx - (x - mx) * S, cy - (y - my) * S

    svg = raster = None
    if a.format == "svg":
        from svgdraw import SvgCanvas
        svg = d = SvgCanvas(W, H, PAPER)
    else:
        from PIL import Image, ImageDraw
        raster = Image.new("RGB", (W, H), PAPER); d = ImageDraw.Draw(raster)
    f18, f22, f38 = font(18), font(22), font(38, True)
    title = src.stem.replace("_", " ").rsplit("-r", 1)[0]
    revision = src.stem.rsplit("-r", 1)[-1] if "-r" in src.stem else "?"
    d.text((50, 35), f"{title.upper()} / YARD", font=f38, fill=INK)
    patch = f" | patch <= {a.max_patch}" if a.max_patch else ""
    d.text((50, 92), f"{size} house | revision {revision} | {len(rows)} / {budget} outdoor furnishings{patch}", font=f22, fill=MUTED)
    d.text((50, 125), "Flat measured footprints; tree crowns are outlines, not trunk obstacles. No textures or 3D rendering.", font=f18, fill=MUTED)
    d.rounded_rectangle(box, 20, fill=PANEL, outline="#B9C3B7", width=2)
    for gx in range(int(x0) - 6, int(x1) + 7):
        px = xy(gx, 0)[0]
        if box[0] + 3 < px < box[2] - 3: d.line((px, box[1] + 3, px, box[3] - 3), fill=GRID)
    for gy in range(int(y0) - 6, int(y1) + 7):
        py = xy(0, gy)[1]
        if box[1] + 3 < py < box[3] - 3: d.line((box[0] + 3, py, box[2] - 3, py), fill=GRID)

    def poly(p, fill, outline="#FAF9F4", width=2):
        d.polygon([xy(x, y) for x, y in p.exterior.coords], fill=fill, outline=outline, width=width)

    for ring in yard.interiors:   # house footprint (native void), display only
        d.polygon([xy(x, y) for x, y in ring.coords], fill="#C9C9BE", outline=MUTED, width=3)
        hx, hy = ring.centroid.coords[0] if hasattr(ring, "centroid") else (0, 0)
        tx, ty = xy(hx, hy); d.text((tx - 30, ty - 12), "HOUSE", font=f22, fill=MUTED)
    for r in sorted(rows, key=lambda r: -r["poly"].area):
        if "tree" in r["name"].lower(): poly(r["poly"], None, "#769066", 3)
        else: poly(r["poly"], colour(r["name"]))
    d.line([xy(x, y) for x, y in yard.exterior.coords], fill=EDGE, width=3)

    placed = []
    def overlaps(p, q): return not (p[2] < q[0] or p[0] > q[2] or p[3] < q[1] or p[1] > q[3])
    for x, y, label in marks:   # no door swing arc (user preference)
        px, py = xy(x, y); tw = d.textlength(label, font=f18)
        bb = (px - tw / 2 - 6, py - 31, px + tw / 2 + 6, py - 6)
        d.rectangle(bb, fill=PAPER, outline=EDGE); d.text((bb[0] + 6, bb[1] + 2), label, font=f18, fill=INK); placed.append(bb)
    for r in rows:
        c = r["poly"].centroid; px, py = xy(c.x, c.y); label = str(r["id"]); tw = d.textlength(label, font=f18)
        for dx, dy in [(0, 0), (0, -28), (0, 28), (32, 0), (-32, 0), (45, -30), (-45, 30), (0, -56), (0, 56)]:
            bb = (px + dx - tw / 2 - 4, py + dy - 12, px + dx + tw / 2 + 4, py + dy + 13)
            if not any(overlaps(bb, p) for p in placed):
                if dx or dy: d.line((px, py, px + dx, py + dy), fill="#73856E")
                d.rounded_rectangle(bb, 3, fill=PAPER, outline="#9BAC97"); d.text((bb[0] + 4, bb[1] - 1), label, font=f18, fill=INK)
                placed.append(bb); break
    sx, sy = 100, box[3] - 60
    d.line((sx, sy, sx + 2 * S, sy), fill=EDGE, width=3)
    for i in range(3):
        d.line((sx + i * S, sy - 5, sx + i * S, sy + 5), fill=EDGE, width=2); d.text((sx + i * S - 4, sy + 10), str(i), font=f18, fill=MUTED)
    d.text((sx + 2 * S + 20, sy + 10), "m", font=f18, fill=MUTED); d.text((box[2] - 250, box[3] - 40), "+X left / +Y up", font=f18, fill=MUTED)
    d.text((50, 1450), "Planning view: intentional overlap is legal; crowns and bounds are not navigation or game collision.", font=f18, fill=MUTED)
    d.text((50, 1485), "Inspect gate, door, junctions and occupied eye-level views together with this plan. No furniture inventory.", font=f18, fill=MUTED)

    out_dir = a.out or (src.parent / "renders"); out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{src.stem}-plan.{a.format}"
    if svg is not None: svg.save(path)
    elif raster is not None: raster.save(path, "JPEG", quality=92)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    assert before == after, "source/database/session changed"
    print(json.dumps({"image": str(path), "count": len(rows), "limit": budget, "protected_files_unchanged": True}))


if __name__ == "__main__":
    main()
