"""Native mesh placement measurements shared by bootstrap and maintenance."""

import json
import numpy as np
from shapely.geometry import MultiPoint
from .geometry_mesh import read_static_mesh_triangles

HANG = ("pendant", "chandelier", "hanging", "ceiling")
CABINETISH = ("cabinet", "shelf", "rack", "cupboard", "shelves")
SEAT_CATEGORY = "Furniture/Chair"


def measure(row, vertices=None):
    iid, name, category, ev, length, width, height, minz = row
    if vertices is None:
        rec = json.loads(ev)
        vertices, _ = read_static_mesh_triangles(rec)
    v = np.asarray(vertices, float)
    z0, z1 = v[:, 2].min(), v[:, 2].max()
    h = z1 - z0
    # --- placement type
    thin = (
        min(length, width) < 0.35 and height > 0.5 and max(length, width) > 2.5 * min(length, width)
    )  # flat hanging things: posters, scrolls (a scroll is 0.27 m deep)
    if category == "Furniture/Wall-Mounted" or (category == "Item/Printed" and thin):
        ptype = "wall"
    elif category == "Lighting" and "wall" in name.lower().split():
        ptype = "wall"  # "Pendant Wall Light" is a wall lamp, not a ceiling pendant
    elif category == "Furniture/Rug" or (height < 0.1 and length * width > 1.5):
        ptype = "rug"
    elif category == "Lighting" and any(w in name.lower() for w in HANG):
        ptype = "ceiling"
    else:
        ptype = "floor"
    small = int(height < 0.6 and max(length, width) < 0.7)
    # --- flat top
    top = v[v[:, 2] >= z1 - 0.03]
    frac = 0.0
    if len(top) >= 3:
        hull = MultiPoint(top[:, :2]).convex_hull
        bbox = max(length * width, 1e-9)
        frac = float(min(1.0, hull.area / bbox))
    supports = int(
        ptype == "floor"
        and category not in ("Item/Printed", "Lighting")
        and frac >= 0.6
        and 0.2 <= h <= 1.4
    )
    # --- front
    front, src, conf = (
        90.0,
        "prior +Y (64/73 measured chairs have the backrest on -Y; thin axis of wall art is Y)",
        0.0,
    )
    if category == SEAT_CATEGORY and h > 0.5:
        high = v[v[:, 2] > z0 + 0.65 * h]
        low = v[(v[:, 2] > z0 + 0.1 * h) & (v[:, 2] < z0 + 0.5 * h)]
        if len(high) >= 20 and len(low) >= 20:
            dy = high[:, 1].mean() - low[:, 1].mean()
            dx = high[:, 0].mean() - low[:, 0].mean()
            if abs(dy) >= 0.08 or abs(dx) >= 0.08:
                if abs(dy) >= abs(dx):
                    front = 90.0 if dy < 0 else 270.0
                    conf = abs(dy)
                else:
                    front = 0.0 if dx > 0 else 180.0
                    conf = abs(dx)  # backrest on +x means the front looks toward -x ... see below
                if abs(dy) < abs(dx):
                    front = 180.0 if dx > 0 else 0.0
                src = "measured from backrest side of the mesh"
    # --- mount height for wall items
    mount = None
    if ptype == "wall":
        bottom = 1.55 - h / 2
        if any(w in name.lower() for w in CABINETISH):
            bottom = 1.3
        if category == "Lighting":
            bottom = 1.7 - h / 2
        mount = round(max(0.05, bottom), 3)
    return (
        iid,
        ptype,
        small,
        front,
        src,
        round(conf, 3),
        supports,
        round(float(z1), 4),
        round(frac, 3),
        mount,
    )
