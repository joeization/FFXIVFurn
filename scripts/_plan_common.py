"""Helpers shared by layout_schematic.py and yard_schematic.py: fonts, item loading, geometry drawing, scale bar, JPEG save.

Deliberately light: numpy, PIL, shapely and the floor-assignment rule only (no deco stack)."""
from __future__ import annotations

import math
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont
from shapely.geometry import MultiPoint

from ffxiv_furniture.interiors import LEVEL_Z, level_for_span

FONT_DIR = "C:/Windows/Fonts/"
INDEX_X, INDEX_Y, INDEX_COL_W, INDEX_TEXT_W, INDEX_ROW_H, INDEX_FOOT = 85, 1775, 785, 745, 35, 130


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_DIR + ("segoeuib.ttf" if bold else "segoeui.ttf"), size)
    except OSError:
        return ImageFont.load_default()


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
    if any(w in s for w in ["plant", "tree", "ivy", "flower", "foliage", "shrub", "greenery", "planter"]):
        return "Plants"
    return "Other / details"


def load_items(layout: dict, db_path: Path) -> list[dict]:
    """Layout furniture as footprint rows. The floor comes from the transformed world bounds via the shared
    level_for_span rule (same as validation/render), and `height` is the item's bottom above THAT floor."""
    scale = layout["interiorScale"]
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = []
        for index, item in enumerate(layout["interiorFurniture"], 1):
            rec = con.execute("select * from furniture_bounds where id=?", (item["itemId"],)).fetchone()
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
            corners = np.array([[a, b, c] for a in [lo[0], hi[0]] for b in [lo[1], hi[1]] for c in [lo[2], hi[2]]])
            corners = (corners * np.array(item["transform"]["scale"])) @ rotation.T + loc
            bottom, top = float(corners[:, 2].min()), float(corners[:, 2].max())
            level = level_for_span(bottom, top)
            rows.append(
                dict(
                    id=index,
                    name=item["name"],
                    item_id=item["itemId"],
                    level=level,
                    poly=MultiPoint(corners[:, :2]).convex_hull,
                    loc=loc,
                    category=categorize(item["name"]),
                    height=bottom - LEVEL_Z[level],
                )
            )
        return rows
    finally:
        con.close()


_REVISION = re.compile(r"[-_ ]+([rR]\d+)$")


def title_revision(stem: str) -> tuple[str, str]:
    """('Display Title', 'r27') from a layout file stem; only a trailing -r<digits> is a revision ('r?' when absent)."""
    m = _REVISION.search(stem)
    return stem[: m.start()].replace("_", " ") if m else stem.replace("_", " "), m.group(1) if m else "r?"


def index_geometry(n_items: int, canvas_w: int) -> tuple[int, int, int]:
    """(columns, rows per column, canvas height) of the optional furniture index so that every item fits on the canvas."""
    cols = max(1, (canvas_w - INDEX_X - INDEX_TEXT_W) // INDEX_COL_W + 1)
    rows = -(-n_items // cols)
    return cols, rows, INDEX_Y + rows * INDEX_ROW_H + INDEX_FOOT


def scale_bar_labels(sx: float, unit: float, ticks: int = 3) -> list[tuple[float, str]]:
    """Digit label and x position of each scale-bar tick: the digits follow the ticks at any zoom."""
    return [(sx + i * unit, str(i)) for i in range(ticks)]


def draw_scale_bar(d, sx, sy, unit, label_font, color, text_color, line=5, tick=3, half=8, text_dy=13):
    n = len(scale_bar_labels(sx, unit))
    d.line((sx, sy, sx + (n - 1) * unit, sy), fill=color, width=line)
    for x, text in scale_bar_labels(sx, unit):
        d.line((x, sy - half, x, sy + half), fill=color, width=tick)
        d.text((x - d.textlength(text, font=label_font) / 2, sy + text_dy), text, font=label_font, fill=text_color)
    d.text((sx + (n - 1) * unit + 16, sy + text_dy), "m", font=label_font, fill=text_color)


def stroke_closed(d, pts, color, width):
    pts = list(pts)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 2:
        return
    # Plain segments plus vertex dots: PIL's joint="curve" bulges at corners and makes thick wall outlines wobbly.
    for a, b in zip(pts, pts[1:] + pts[:1]):
        d.line([a, b], fill=color, width=width)
    half = max(width / 2, 1)
    for px, py in pts:
        # Square patch per vertex swallows the perpendicular caps so corners stay clean at any angle.
        d.rectangle((px - half, py - half, px + half, py + half), fill=color)


def draw_geom(d, to_px, geom, fill=None, outline=None, width=1, hole_fill=None):
    """Draw any shapely geometry: Polygon (+holes), Multi*/collections, and degenerate hulls (Point/LineString)."""
    if geom.is_empty:
        return
    kind = geom.geom_type
    if hasattr(geom, "geoms"):
        for part in geom.geoms:
            draw_geom(d, to_px, part, fill, outline, width, hole_fill)
    elif kind == "Polygon":
        coords = [to_px(a, c) for a, c in geom.exterior.coords]
        if fill:
            d.polygon(coords, fill=fill)
        if outline:
            stroke_closed(d, coords, outline, width)
        if hole_fill:
            for ring in geom.interiors:
                d.polygon([to_px(a, c) for a, c in ring.coords], fill=hole_fill)
    elif kind == "Point":
        px, py = to_px(geom.x, geom.y)
        d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=fill or outline)
    else:   # LineString / LinearRing
        d.line([to_px(a, c) for a, c in geom.coords], fill=outline or fill, width=width)


def save_plan(img: Image.Image, path: Path, scale: float) -> None:
    """Drawn at full size for clean geometry/text, saved smaller."""
    img = img.convert("RGB")
    if scale != 1.0:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    img.save(path, "JPEG", quality=90)
