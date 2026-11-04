"""Interactive decoration engine behind the MCP server (no MCP dependency here, so it is unit-testable).

Conventions (metres, +x east/right, +y north/door side, +z up):
  yaw_deg is counter-clockwise about +z: 0 maps the asset's local +y to north, 90 -> west, 180 -> south, 270 -> east.
  anchor 'pivot'         : position is the asset pivot.
  anchor 'bottom_center' : XY is the centre of the rotated local bounds, Z is the bounds bottom.
Only physics is enforced (inside floor, outside stair bodies, wall items on a wall, whole-house budget). Overlap, stacking,
floating, blocked circulation are LEGAL. Nothing is ever silently moved/rotated/removed; a failed batch changes nothing.
"""

from __future__ import annotations
import re, copy, hashlib, json, math, os, sqlite3, time
from pathlib import Path
from ..config import source_path, catalog_path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = catalog_path()
INTERIOR_LIMITS = {"Medium": 450, "Apartment": 150, "Small": 300}
INTERIOR_LIMIT = 450  # legacy name: Medium cap
TOL = 0.02


class DecoError(Exception):
    def __init__(self, code, message, issues=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.issues = issues or []

    def payload(self, revision=None):
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "revision": revision,
                "issues": self.issues,
            },
        }


def _rot(x, y, yaw_deg):
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return c * x - s * y, s * x + c * y


def _num(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise DecoError("BAD_INPUT", f"{name} must be a finite number, got {v!r}")
    return float(v)


def _vec(v, n, name):
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise DecoError("BAD_INPUT", f"{name} must be a list of {n} numbers")
    return [_num(x, name) for x in v]


_STAINS = None


def housing_stains():
    """Housing-applicable dyes from data/external/Stain.csv: [(name, (r,g,b), shade, metallic)]. The app matches properties.color by RGB against these."""
    global _STAINS
    if _STAINS is None:
        import csv

        _STAINS = []
        with open(source_path("stains_csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                c = int(r["Color"])
                if c and r["IsHousingApplicable"] == "True":
                    _STAINS.append(
                        (
                            r["Name"],
                            ((c >> 16) & 255, (c >> 8) & 255, c & 255),
                            int(r["Shade"]),
                            r["IsMetallic"] == "True",
                        )
                    )
    return _STAINS


def resolve_dye(spec):
    """spec = dye name (exact, case-insensitive) or '#rrggbb' (snapped to the nearest housing dye). Returns (name, rgb)."""
    st = housing_stains()
    s = str(spec).strip()
    for n, rgb, _, _ in st:
        if n.lower() == s.lower():
            return n, rgb
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", s):
        h = s.lstrip("#")
        want = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        n, rgb, _, _ = min(st, key=lambda x: sum((a - b) ** 2 for a, b in zip(x[1], want)))
        return n, rgb
    raise DecoError("UNKNOWN_DYE", f"unknown dye {spec!r}; use search_dyes or #rrggbb")


_FO = None


def _front_overrides():
    global _FO
    if _FO is None:
        p = ROOT / "data/front-overrides.json"
        _FO = (
            {
                k: v
                for k, v in json.loads(p.read_text(encoding="utf-8")).items()
                if not k.startswith("_")
            }
            if p.exists()
            else {}
        )
    return _FO


def _patch_num(p):
    try:
        return float(p)
    except (TypeError, ValueError):
        return None  # unknown patch: not filtered


class Catalog:
    """Read-only view of data/furniture.sqlite3 (never goes through FurnitureDB, which can migrate)."""

    def __init__(self, path=None, scope="interior"):
        if scope not in ("interior", "exterior"):
            raise DecoError("BAD_INPUT", "scope must be interior or exterior")
        self.scope = scope
        self.path = Path(path or catalog_path())
        self.db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row
        self._cache = {}
        self._emb = None

    def sha(self):
        return hashlib.sha256(
            f"{self.path.stat().st_size}:{self.path.stat().st_mtime_ns}".encode()
        ).hexdigest()[:16]

    def item(self, item_id=None, name=None):
        key = item_id if item_id is not None else ("n", name)
        if key in self._cache:
            return self._cache[key]
        q = """SELECT b.id,b.name,b.min_x,b.min_y,b.min_z,b.max_x,b.max_y,b.max_z,p.placement_type,p.front_deg,p.front_source,p.supports_top,p.top_z_local,p.mount_bottom_z,b.dyeable,b.dye_channels
               FROM furniture_bounds b LEFT JOIN placement_info p ON p.item_id=b.id WHERE b.scope=? AND """
        rows = self.db.execute(
            q + ("b.id=?" if item_id is not None else "b.name=?"),
            (self.scope, item_id if item_id is not None else name),
        ).fetchall()
        if len(rows) != 1:
            raise DecoError(
                "UNKNOWN_ITEM",
                f"no unique {self.scope} item for {item_id if item_id is not None else name!r} ({len(rows)} matches)",
            )
        r = rows[0]
        surf = [
            dict(
                idx=s[0],
                z=s[1],
                min=[s[2], s[3]],
                max=[s[4], s[5]],
                area_m2=s[6],
                clearance_m=s[7],
                is_top=bool(s[8]),
            )
            for s in self.db.execute(
                "SELECT surface_idx,z_local,min_x,min_y,max_x,max_y,area_m2,clearance_above_m,is_top FROM support_surfaces WHERE item_id=? ORDER BY z_local",
                (r["id"],),
            )
        ]
        d = dict(
            id=r["id"],
            name=r["name"],
            lo=[r["min_x"], r["min_y"], r["min_z"]],
            hi=[r["max_x"], r["max_y"], r["max_z"]],
            ptype=r["placement_type"] or "floor",
            front_deg=r["front_deg"] if r["front_deg"] is not None else 90.0,
            supports_top=bool(r["supports_top"]),
            dyeable=bool(r["dyeable"]),
            dye_channels=r["dye_channels"],
            mount_bottom_z=r["mount_bottom_z"],
            surfaces=surf,
        )
        d["front_guessed"] = str(r["front_source"] or "prior").startswith("prior")
        ov = _front_overrides().get(str(d["id"]))
        if ov:
            d["front_deg"] = float(ov["front_deg"])
            d["front_guessed"] = False
        pr = self.db.execute("SELECT patch FROM furniture WHERE id=?", (d["id"],)).fetchone()
        d["patch"] = _patch_num(pr[0] if pr else None)
        self._cache[key] = d
        self._cache[d["id"]] = d
        return d

    KIND = {
        "wall": "Wallpaper",
        "floor": "Flooring",
        "light": "CeilingLight",
        "window": "Window",
        "door": "MainDoor",
    }
    FT = {
        "Wall": "Wallpaper",
        "Floor": "Flooring",
        "Light": "CeilingLight",
        "Window": "Window",
        "Door": "MainDoor",
    }

    def material(self, item_id, name, ftype):
        cat = self.FT[ftype]
        q = "SELECT item_id,name,patch,asset_key FROM house_materials WHERE category=? AND " + (
            "item_id=?" if item_id is not None else "name=?"
        )
        rows = self.db.execute(q, (cat, item_id if item_id is not None else name)).fetchall()
        if len(rows) != 1:
            raise DecoError(
                "UNKNOWN_ITEM",
                f"no unique {cat} material for {item_id if item_id is not None else name!r}",
            )
        mp = _patch_num(rows[0]["patch"])
        if self.max_patch is not None and mp is not None and mp > self.max_patch:
            raise DecoError(
                "ITEM_TOO_NEW",
                f"{rows[0]['name']} is from patch {rows[0]['patch']}, newer than max_patch {self.max_patch}",
            )
        folder = source_path("materials") / Path(rows[0]["asset_key"]).relative_to(
            "MakePlace/Content"
        )
        if not folder.exists():
            raise DecoError(
                "GEOMETRY_UNAVAILABLE",
                f"{rows[0]['name']} has no extracted textures (not renderable)",
            )
        return rows[0]

    def search_materials(self, query, kind, limit=20):
        cat = self.KIND.get(kind)
        if cat is None:
            raise DecoError("BAD_INPUT", "kind must be wall, floor or light")
        words = [w for w in query.lower().split() if w]
        where = ["category=?"]
        args = [cat]
        for w in words:
            where.append(
                "(lower(name) LIKE ? OR lower(visual_description) LIKE ? OR lower(proposed_tags) LIKE ?)"
            )
            args += [f"%{w}%"] * 3
        if self.max_patch is not None:
            where.append("(patch IS NULL OR CAST(patch AS REAL) <= ?)")
            args.append(self.max_patch)
        rows = self.db.execute(
            "SELECT item_id,name,visual_description,proposed_tags,asset_key FROM house_materials WHERE "
            + " AND ".join(where)
            + " ORDER BY name LIMIT ?",
            args + [min(int(limit), 60)],
        ).fetchall()
        base = source_path("materials") / "HouseAssets" / cat
        return [
            dict(
                item_id=r["item_id"],
                name=r["name"],
                description=(r["visual_description"] or "")[:160],
                tags=json.loads(r["proposed_tags"] or "[]")[:5],
                renderable=(
                    source_path("materials") / Path(r["asset_key"]).relative_to("MakePlace/Content")
                ).exists(),
            )
            for r in rows
        ]

    def search_dyes(self, query="", limit=40):
        q = query.lower().strip()
        rows = [
            dict(name=n, hex="%02X%02X%02X" % c, shade=sh, metallic=m)
            for n, c, sh, m in housing_stains()
            if not q or q in n.lower()
        ]
        if re.fullmatch(r"#?[0-9a-fA-F]{6}", query.strip()):
            n, c = resolve_dye(query)
            rows = [
                dict(
                    name=n, hex="%02X%02X%02X" % c, note="nearest housing dye to the requested hex"
                )
            ]
        return rows[:limit]

    def tags(self, item_id):
        return [
            f"{c}:{n}"
            for c, n in self.db.execute(
                "SELECT t.category,t.name FROM furniture_tags ft JOIN tags t ON t.id=ft.tag_id WHERE ft.furniture_id=?",
                (item_id,),
            )
        ]

    max_patch = None  # set by the Session: hide items newer than this game patch (e.g. 7.2)

    def _too_new(self, item_id):
        if self.max_patch is None:
            return False
        p = self.item(item_id)["patch"]
        return p is not None and p > self.max_patch

    def search(self, query="", mode="text", placement_types=(), tags_all=(), limit=20, offset=0):
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        if mode == "semantic":
            return self._semantic(query, placement_types, tags_all, limit, offset)
        words = [w for w in query.lower().split() if w]
        where = ["b.scope=?"]
        args = [self.scope]
        for w in words:
            where.append("(lower(b.name) LIKE ? OR lower(f.description) LIKE ?)")
            args += [f"%{w}%", f"%{w}%"]
        if placement_types:
            where.append(
                "COALESCE(p.placement_type,'floor') IN (%s)" % ",".join("?" * len(placement_types))
            )
            args += list(placement_types)
        for t in tags_all:
            cat, _, nm = t.partition(":")
            where.append(
                "EXISTS(SELECT 1 FROM furniture_tags ft JOIN tags t ON t.id=ft.tag_id WHERE ft.furniture_id=b.id AND t.name=?"
                + (" AND t.category=?" if nm else "")
                + ")"
            )
            args += [nm, cat] if nm else [cat]
        sql = (
            """SELECT b.id FROM furniture_bounds b JOIN furniture f ON f.id=b.id LEFT JOIN placement_info p ON p.item_id=b.id WHERE """
            + " AND ".join(where)
            + " ORDER BY (lower(b.name) LIKE ?) DESC, length(b.name), b.name LIMIT ? OFFSET ?"
        )
        ids = [
            r[0]
            for r in self.db.execute(
                sql.replace("LIMIT ? OFFSET ?", ""), args + [f"%{query.lower()}%"]
            )
        ]
        ids = [i for i in ids if not self._too_new(i)][offset : offset + limit + 1]
        return self._rows(ids[:limit], None), len(ids) > limit

    def _semantic(self, query, placement_types, tags_all, limit, offset):
        from ffxiv_furniture import semantic as S

        if self._emb is None:
            S.load_sqlite_vec(self.db)
            self._emb = S.E5Embedder(
                local_files_only=True, cache_dir=str(ROOT / "data/model-cache")
            )
        if any(ch.isalpha() and ord(ch) > 0x24F for ch in query):
            raise DecoError("SEMANTIC_UNAVAILABLE", "semantic queries must be English")
        blob = self._emb.embed([query], query=True)[0]
        rows = self.db.execute(
            """SELECT f.id, vec_distance_cosine(v.embedding,?) d FROM furniture f JOIN furniture_vectors v ON v.rowid=f.id
               WHERE f.scope=? ORDER BY d LIMIT ?""",
            (blob, self.scope, 400),
        ).fetchall()
        out = []
        for r in rows:
            it = self.item(r[0]) if self._ok(r[0]) else None
            if it is None or self._too_new(it["id"]):
                continue
            if placement_types and it["ptype"] not in placement_types:
                continue
            if tags_all and not all(
                t in self.tags(it["id"]) or any(x.endswith(":" + t) for x in self.tags(it["id"]))
                for t in tags_all
            ):
                continue
            out.append((it["id"], 1 - r[1]))
        page = out[offset : offset + limit]
        return self._rows([i for i, _ in page], {i: s for i, s in page}), len(out) > offset + limit

    def _ok(self, i):
        try:
            self.item(i)
            return True
        except DecoError:
            return False

    def _rows(self, ids, scores):
        res = []
        for i in ids:
            it = self.item(i)
            res.append(
                dict(
                    item_id=it["id"],
                    name=it["name"],
                    size_m=[round(it["hi"][k] - it["lo"][k], 2) for k in range(3)],
                    placement_type=it["ptype"],
                    front_deg=it["front_deg"],
                    supports_top=it["supports_top"],
                    surfaces=[
                        dict(
                            idx=s["idx"],
                            z=round(s["z"], 2),
                            size=[
                                round(s["max"][0] - s["min"][0], 2),
                                round(s["max"][1] - s["min"][1], 2),
                            ],
                        )
                        for s in it["surfaces"]
                        if s["is_top"] or s["clearance_m"] > 0.3
                    ][:4],
                    tags=self.tags(i)[:8],
                    **({"score": round(scores[i], 3)} if scores else {}),
                )
            )
        return res


class Room:
    """Medium geometry from the same native profile as rendering."""

    UPPER_Z = 7.0

    def __init__(self, style="Shirogane", house_size="Medium"):
        from ffxiv_furniture.interiors import InteriorProfile, ApartmentProfile, SmallProfile

        if house_size not in ("Medium", "Apartment", "Small"):
            raise DecoError(
                "UNSUPPORTED_HOUSE", "MCP supports Medium, Small and Apartment houses only"
            )
        try:
            self.profile = {"Apartment": ApartmentProfile, "Small": SmallProfile}.get(
                house_size, InteriorProfile
            )(style)
        except ValueError as e:
            raise DecoError("UNSUPPORTED_INTERIOR", str(e)) from e
        self.house_size = house_size
        self.limit = INTERIOR_LIMITS[house_size]
        self.levels = (
            ("ground", "upper")
            if house_size == "Medium"
            else tuple(getattr(self.profile, "levels", ("ground",)))
        )
        self.level_z = {"ground": 0.0, "upper": 7.0, "basement": -7.0}
        self.door_xy = getattr(self.profile, "door_xy", (0.0, 8.0))
        self.style = self.profile.style
        self.floor = self.profile.polygon("ground")
        self.upper = self.profile.polygon("upper")
        from shapely.geometry import Polygon as _P

        self.basement = self.profile.polygon("basement") if "basement" in self.levels else _P()
        self.polys = {"ground": self.floor, "upper": self.upper, "basement": self.basement}
        self.openings = self.profile.openings() if hasattr(self.profile, "openings") else []
        self.stairs = self.profile.stair_footprints("ground")
        self.walls_by_level = {
            level: (self._walls(self.profile.polygon(level)) if level in self.levels else [])
            for level in ("ground", "upper", "basement")
        }
        self.walls = self.walls_by_level["ground"]
        self.pillars_by_level = {
            level: (self.profile.pillar_footprints(level) if level in self.levels else [])
            for level in ("ground", "upper", "basement")
        }

    @staticmethod
    def _walls(floor):
        from shapely.geometry import Point

        ring = list(floor.exterior.coords)[:-1]
        walls = []
        seen = {}
        for a, b in zip(ring, ring[1:] + ring[:1]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dx, dy)
            if ln < 0.5:
                continue
            nx, ny = -dy / ln, dx / ln
            mid = Point((a[0] + b[0]) / 2 + nx * 0.05, (a[1] + b[1]) / 2 + ny * 0.05)
            if not floor.buffer(1e-6).contains(mid):
                nx, ny = -nx, -ny
            d = (
                "north"
                if ny > 0.7
                else (
                    "south"
                    if ny < -0.7
                    else "east" if nx > 0.7 else "west" if nx < -0.7 else "diag"
                )
            )
            name = {
                "north": "south",
                "south": "north",
                "east": "west",
                "west": "east",
                "diag": "diag",
            }[d]
            seen[name] = seen.get(name, 0) + 1
            walls.append(
                dict(
                    wall_id=f"{name}{seen[name]}",
                    start=[round(a[0], 3), round(a[1], 3)],
                    end=[round(b[0], 3), round(b[1], 3)],
                    inward=[round(nx, 3), round(ny, 3)],
                    length=round(ln, 3),
                )
            )
        return walls

    def _stair_world(self, name):
        return self.profile.actor_world(name)

    ACCESS_M = 1.2  # approach distance kept as a hint zone around the stair foot / upper arrival

    def stair_info(self):
        """Stair facts from the NATIVE stair mesh of the current interior (transforms incl. mirroring), not from hulls or assumptions.
        up: foot (lowest steps), top/arrival (highest steps = where you step onto the upper floor), solid (footprint of everything below 2.4 m),
        access zones (approach areas, hints only). down: the part of the basement stair at/above ground level.
        """
        if getattr(self, "_stair_info", None) is not None:
            return self._stair_info
        if self.house_size == "Apartment":
            self._stair_info = dict(
                up=dict(
                    top_height_m=None,
                    solid=None,
                    foot=None,
                    top=None,
                    foot_access=None,
                    arrival_access=None,
                ),
                down=dict(top=None, entry_access=None, hole=None),
            )
            return self._stair_info
        import numpy as np
        from shapely.geometry import Polygon, box
        from shapely.ops import unary_union

        def cells(w, tri, pred, step=0.25):
            P = w[tri]
            out = []
            for q in P:
                if pred(q[:, 2]) and Polygon(q[:, :2]).area > 1e-6:
                    out.append(Polygon(q[:, :2]))
            return unary_union(out) if out else None

        info = {}
        if self.house_size == "Small":
            w2, tri2 = self._stair_world("Stairs2_9")
            down_top = cells(w2, tri2, lambda z: z.max() > -0.6)
            bfoot = cells(w2, tri2, lambda z: z.max() < -6.0)  # lowest steps
            bus = self.under_stair("Stairs2_9", -7.0, self.basement)
            bsolid = bus[
                "blocked"
            ]  # walking-height obstacle per style: low flight + boxed (enclosed) underside
            bfoot_access = (
                bfoot.buffer(self.ACCESS_M).difference(bsolid).intersection(self.basement)
                if bfoot is not None and bsolid is not None
                else None
            )
            landing = box(4.6, -4.8, 6.0, -2.8).intersection(
                self.floor
            )  # approach to the stair-landing doorway in the x=6 wall (wall-mesh gap y -4.6..-3.0)
            self._stair_info = dict(
                up=dict(
                    top_height_m=None,
                    solid=None,
                    foot=None,
                    top=None,
                    foot_access=landing,
                    arrival_access=None,
                ),
                basement=dict(
                    solid=bsolid.buffer(0.02) if bsolid is not None else None,
                    foot=bfoot,
                    foot_access=bfoot_access,
                    under=bus,
                ),
                down=dict(
                    landing_door_access=landing,
                    top=down_top,
                    entry_access=(
                        down_top.buffer(self.ACCESS_M).intersection(self.floor)
                        if down_top is not None
                        else None
                    ),
                    hole=box(*self.floor.bounds).difference(self.floor),
                ),
            )
            return self._stair_info
        w, tri = self._stair_world("Stairs")
        zmax = float(w[:, 2].max())
        solid = cells(w, tri, lambda z: z.min() < 2.0)
        foot = cells(w, tri, lambda z: z.max() < 1.0 and z.min() > -0.5)
        top = cells(
            w, tri, lambda z: z.min() > 6.2 and z.max() < 7.5
        )  # steps at upper-floor height (excludes side walls/handrails that rise higher)
        opening = box(*self.upper.bounds).difference(self.upper)
        gz = self.floor
        info["up"] = dict(
            top_height_m=round(zmax, 2),
            solid=solid.buffer(0.02) if solid is not None else None,
            foot=foot,
            top=top,
            foot_access=(
                foot.buffer(self.ACCESS_M).difference(solid).intersection(gz)
                if foot is not None and solid is not None
                else None
            ),
            arrival_access=(
                top.buffer(self.ACCESS_M).difference(opening.buffer(0.02)).intersection(self.upper)
                if top is not None
                else None
            ),
        )
        w2, tri2 = self._stair_world("Stairs2_9")
        down_top = cells(w2, tri2, lambda z: z.max() > -0.6)
        hole = box(*self.floor.bounds).difference(self.floor)
        info["down"] = dict(
            top=down_top,
            entry_access=(
                down_top.buffer(self.ACCESS_M).intersection(self.floor)
                if down_top is not None
                else None
            ),
            hole=hole,
        )
        self._stair_info = info
        return info

    def under_stair(self, name, floor_z, room_poly, step=0.25, cap=3.0):
        """Usable space under a native stair flight, per interior style (user-reported: some styles box the underside, e.g. Mist Small's
        stepped side panel, while Minimalist's open flight leaves room underneath). For each `step` cell of the stair's XY projection:
        clearance = lowest stair surface above `floor_z` (vertical ray); the cell is ENCLOSED when no horizontal ray (+-x, +-y at
        0.4/0.9/1.4 m, below the clearance) leaves the projection into `room_poly` without hitting stair geometry (room walls count as closed).
        Enclosed cells have no usable space (clearance reported 0). Mesh facts only; game collision/placement under stairs is not app-verified.
        """
        cache = self.__dict__.setdefault("_under", {})
        if name in cache:
            return cache[name]
        import numpy as np
        from shapely.geometry import Polygon, Point, box
        from shapely.ops import unary_union
        from shapely import prepared

        w, tri = self._stair_world(name)
        P = w[tri]
        proj = unary_union(
            [Polygon(t[:, :2]) for t in P if Polygon(t[:, :2]).area > 1e-6]
        ).intersection(box(*room_poly.envelope.bounds))
        pp = prepared.prep(proj)
        inside = prepared.prep(room_poly.buffer(-0.05))
        in_room = prepared.prep(room_poly)
        x0, y0, x1, y1 = proj.bounds
        cs = [
            (x, y)
            for x in np.arange(math.floor(x0 / step) * step, x1, step) + step / 2
            for y in np.arange(math.floor(y0 / step) * step, y1, step) + step / 2
            if pp.contains(Point(x, y))
        ]
        if not cs:
            cache[name] = dict(
                cells=[], cell_m=step, enclosed=None, usable=None, blocked=None, projection=proj
            )
            return cache[name]
        C = np.array(cs)
        A, B, Cc = P[:, 0], P[:, 1], P[:, 2]
        E1, E2 = B - A, Cc - A

        def first_hit(o, d):
            """Moller-Trumbore over all triangles: smallest t > 0 along unit ray (o, d), inf when nothing is hit."""
            h = np.cross(np.broadcast_to(d, E2.shape), E2)
            a = (E1 * h).sum(1)
            ok = np.abs(a) > 1e-9
            f = np.where(ok, 1.0 / np.where(ok, a, 1), 0)
            sv = o - A
            u = f * (sv * h).sum(1)
            q = np.cross(sv, E1)
            v = f * (q * d).sum(1)
            t = f * (E2 * q).sum(1)
            m = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4)
            return float(t[m].min()) if m.any() else math.inf

        up = np.array([0.0, 0.0, 1.0])
        clear = np.array(
            [min(cap, first_hit(np.array([x, y, floor_z + 0.02]), up) + 0.02) for x, y in C]
        )
        open_ = np.zeros(len(C), bool)
        walled = np.array(
            [not in_room.contains(Point(x, y)) for x, y in C]
        )  # outside the style's walls: no space at all
        for hgt in (0.4, 0.9, 1.4):
            for i in np.where(~open_ & ~walled & (clear > hgt + 0.1))[0]:
                for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    t_ = 0.0
                    while t_ < 12 and pp.contains(Point(C[i, 0] + d[0] * t_, C[i, 1] + d[1] * t_)):
                        t_ += 0.1
                    t_ += 0.15
                    if not inside.contains(Point(C[i, 0] + d[0] * t_, C[i, 1] + d[1] * t_)):
                        continue  # exits into a room wall: closed
                    if (
                        first_hit(
                            np.array([C[i, 0], C[i, 1], floor_z + hgt]), np.array([d[0], d[1], 0.0])
                        )
                        > t_
                    ):
                        open_[i] = True
                        break
        enclosed = walled | (
            ~open_ & (clear > 0.5)
        )  # walled off by the style, or boxed in; very low cells (first steps) are simply solid
        usable_clear = np.where(open_, clear, 0.0)
        cell = lambda x, y: box(x - step / 2, y - step / 2, x + step / 2, y + step / 2)

        def U(mask):
            g = [cell(*C[i]) for i in np.where(mask)[0]]
            return unary_union(g) if g else None

        r = dict(
            cells=[
                [
                    round(float(x - step / 2), 3),
                    round(float(y - step / 2), 3),
                    round(float(c), 2),
                    bool(e),
                ]
                for (x, y), c, e in zip(C, usable_clear, enclosed)
            ],
            cell_m=step,
            enclosed=U(enclosed),
            usable=U(usable_clear >= 1.9),
            blocked=U(usable_clear < 1.9),
            projection=proj,
        )
        cache[name] = r
        return r

    def stair_summary(self):
        if self.house_size == "Apartment":
            return dict(note="Apartment has a single floor and no stairs.")
        if self.house_size == "Small":
            d = self.stair_info()["down"]
            b = lambda g: (
                [round(v, 2) for v in g.bounds] if g is not None and not g.is_empty else None
            )
            bs = self.stair_info()["basement"]
            u = bs["under"]
            ar = lambda g: round(g.area, 1) if g is not None and not g.is_empty else 0.0
            return dict(
                basement=dict(
                    stair_solid_xy_bounds=b(bs["solid"]),
                    stair_foot_xy_bounds=b(bs["foot"]),
                    stair_foot_access_xy_bounds=b(bs["foot_access"]),
                    floor_z=-7.0,
                    under_stair=dict(
                        projection_m2=ar(u.get("projection")),
                        enclosed_m2=ar(u["enclosed"]),
                        usable_ge_1p9m_m2=ar(u["usable"]),
                        usable_xy_bounds=b(u["usable"]),
                        note=f"{self.style}: enclosed = boxed underside, no usable space; usable = open underside with >=1.9 m headroom; per-cell headroom in inspect(include_geometry).stair_clearance.basement",
                    ),
                    note="basement floor is z=-7 (items: z=-7 for floor pieces); keep stair_foot_access walkable",
                ),
                down=dict(
                    landing_door_access_xy_bounds=b(d["landing_door_access"]),
                    landing_note="the stairwell sits in an east alcove (x 6..10, y -6..-1) entered through a doorway in the x=6 wall at y -4.6..-3.0; keep landing_door_access clear (STAIR_ACCESS_BLOCKED) unless hiding the stair",
                    entry_xy_bounds=b(d["top"]),
                    entry_access_xy_bounds=b(d["entry_access"]),
                    ground_hole_xy_bounds=b(d["hole"]),
                    note="basement stair (Small has no upper floor); hiding it is a legitimate design, otherwise keep entry_access walkable",
                ),
            )
        import numpy as np

        def b(g):
            return [round(v, 2) for v in g.bounds] if g is not None and not g.is_empty else None

        s = self.stair_info()
        u, d = s["up"], s["down"]
        return dict(
            up=dict(
                foot_xy_bounds=b(u["foot"]),
                foot_access_xy_bounds=b(u["foot_access"]),
                upper_arrival_xy_bounds=b(u["top"]),
                upper_arrival_access_xy_bounds=b(u["arrival_access"]),
                solid_below_2p4m_xy_bounds=b(u["solid"]),
                top_height_m=u["top_height_m"],
                note="first steps are at foot; you step onto the upper floor at upper_arrival. Keep the two access zones walkable unless you deliberately hide the stair.",
            ),
            down=dict(
                entry_xy_bounds=b(d["top"]),
                entry_access_xy_bounds=b(d["entry_access"]),
                ground_hole_xy_bounds=b(d["hole"]),
                note="basement stair; hiding it behind walls is a legitimate design",
            ),
        )

    def level_of(self, z):
        return "basement" if z <= -3.0 else ("upper" if z >= self.UPPER_Z - 1.0 else "ground")

    def floor_at(self, z):
        return self.polys[self.level_of(z)]

    def stair_clearance(self, step=0.5, cap=3.0):
        """Coarse headroom under the stairs at ground level: for each cell the height of the LOWEST stair surface above z=0 (None = no stair above this cell).
        Stairs are not solid blocks: items lower than `clearance_m` fit under the flights; `cells` lists only cells that have a stair above them.
        """
        if getattr(self, "_clear", None) is not None:
            return self._clear
        if self.house_size == "Small":
            u = self.stair_info()["basement"]["under"]
            self._clear = dict(
                basement=dict(
                    cell_m=u["cell_m"],
                    cells=u["cells"],
                    note="cell = [x_min, y_min, usable_clearance_m, enclosed]; enclosed (boxed underside) => 0, no space",
                )
            )
            return self._clear
        if self.house_size != "Medium":
            return {}
        import numpy as np
        from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles

        out = {}
        for name, label in (("Stairs", "up"), ("Stairs2_9", "down")):
            w, tri = self._stair_world(name)
            P = w[tri]
            x0, y0, x1, y1 = P[:, :, 0].min(), P[:, :, 1].min(), P[:, :, 0].max(), P[:, :, 1].max()
            cells = []
            for gx in np.arange(math.floor(x0), x1, step):
                for gy in np.arange(math.floor(y0), y1, step):
                    px, py = gx + step / 2, gy + step / 2
                    lo = None
                    A, B, C = P[:, 0, :2], P[:, 1, :2], P[:, 2, :2]
                    d = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (
                        A[:, 1] - C[:, 1]
                    )
                    ok = np.abs(d) > 1e-9
                    l1 = np.where(
                        ok,
                        (
                            (B[:, 1] - C[:, 1]) * (px - C[:, 0])
                            + (C[:, 0] - B[:, 0]) * (py - C[:, 1])
                        )
                        / np.where(ok, d, 1),
                        -1,
                    )
                    l2 = np.where(
                        ok,
                        (
                            (C[:, 1] - A[:, 1]) * (px - C[:, 0])
                            + (A[:, 0] - C[:, 0]) * (py - C[:, 1])
                        )
                        / np.where(ok, d, 1),
                        -1,
                    )
                    l3 = 1 - l1 - l2
                    hit = ok & (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
                    if hit.any():
                        z = (l1 * P[:, 0, 2] + l2 * P[:, 1, 2] + l3 * P[:, 2, 2])[hit]
                        z = z[z > 0.05]
                        if len(z):
                            lo = float(z.min())
                    if lo is not None:
                        cells.append(
                            [round(float(gx), 2), round(float(gy), 2), round(min(lo, cap), 2)]
                        )
            if label == "up":
                from shapely.geometry import Point as _Pt

                enc = self.under_stair(name, 0.0, self.floor, step=step)["enclosed"]
                if enc is not None:
                    cells = [
                        [
                            c[0],
                            c[1],
                            0.0 if enc.contains(_Pt(c[0] + step / 2, c[1] + step / 2)) else c[2],
                        ]
                        for c in cells
                    ]
            out[label] = dict(
                cell_m=step,
                cells=cells,
                note="cell = [x_min, y_min, clearance_m]; clearance 3.0 means >=3 m; 0 where this style boxes the underside (enclosed)",
            )
        self._clear = out
        return out

    def boundary_distance(self, x, y, z=0.0):
        from shapely.geometry import Point

        f = self.floor_at(z)
        return f.boundary.distance(Point(x, y))


def quat_to_yaw(q):
    return math.degrees(2 * math.atan2(q[2], q[3])) % 360


class Session:
    def __init__(
        self, name, catalog, room, base_dir, seed_layout=None, from_layout=None, max_patch=None
    ):
        self.name = name
        self.cat = catalog
        self.max_patch = max_patch
        catalog.max_patch = max_patch
        self.room = room
        self.dir = Path(base_dir) / name
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "renders").mkdir(exist_ok=True)
        if seed_layout is not None and seed_layout.get("houseSize", "Medium") != room.house_size:
            raise DecoError(
                "UNSUPPORTED_HOUSE",
                f"seed houseSize {seed_layout.get('houseSize')!r} does not match the room ({room.house_size})",
            )
        self.seed = seed_layout
        self.instances = {}
        self.next_id = 1
        self.revision = 0
        self.undo_stack = []
        self.redo_stack = []
        self.snapshots = {}
        self.reserved_other_floors = 0
        self.fixtures = {}
        if (self.dir / "state.json").exists():
            self._load()
        elif from_layout is not None:
            self._import(from_layout)
            self._save()
        else:
            self._save()

    # -------- persistence
    def _state(self):
        return copy.deepcopy(
            {
                "instances": self.instances,
                "next_id": self.next_id,
                "fixtures": self.fixtures,
                "style": self.room.style,
            }
        )

    def _set_state(self, st):
        legacy_style = next(
            (
                f["name"]
                for f in (self.seed or {}).get("interiorFixture", [])
                if f["type"] == "District"
            ),
            self.room.style,
        ).replace(" ", "")
        style = st.get("style", legacy_style)
        room = self.room if self.room.style == style else Room(style, self.room.house_size)
        self.instances = copy.deepcopy(st["instances"])
        self.next_id = st["next_id"]
        self.fixtures = copy.deepcopy(st.get("fixtures", {}))
        self.room = room
        self.instances_view = None

    def _save(self):
        d = dict(
            name=self.name,
            revision=self.revision,
            state=self._state(),
            undo=self.undo_stack,
            redo=self.redo_stack,
            snapshots=self.snapshots,
            seed=self.seed,
            catalog=self.cat.sha(),
            max_patch=self.max_patch,
        )
        tmp = self.dir / "state.json.tmp"
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, self.dir / "state.json")

    def _load(self):
        d = json.loads((self.dir / "state.json").read_text(encoding="utf-8"))
        if d.get("scope", "interior") != getattr(self.cat, "scope", "interior"):
            raise DecoError(
                "SCOPE_MISMATCH", "Use a separate named session for interior and exterior"
            )
        saved_size = (d.get("seed") or {}).get("houseSize")
        if saved_size is not None and saved_size != self.room.house_size:
            raise DecoError(
                "HOUSE_MISMATCH",
                f"Saved session is {saved_size!r}; use a matching DECO_SEED or a new session name",
            )
        self.max_patch = d.get("max_patch", self.max_patch)
        self.cat.max_patch = self.max_patch
        self.seed = d["seed"]
        self.revision = d["revision"]
        self._set_state(d["state"])
        self.undo_stack = d["undo"]
        self.redo_stack = d["redo"]
        self.snapshots = d["snapshots"]

    def _import(self, layout):
        self.seed = {k: v for k, v in layout.items() if k != "interiorFurniture"}
        for f in layout.get("interiorFurniture", []):
            t = f["transform"]
            it = self.cat.item(f["itemId"])
            iid = f"i{self.next_id}"
            self.next_id += 1
            self.instances[iid] = dict(
                id=iid,
                item_id=it["id"],
                name=it["name"],
                pivot=[v / 100 for v in t["location"]],
                yaw=quat_to_yaw(t["rotation"]),
            )
            c = (f.get("properties") or {}).get("color")
            if isinstance(c, str) and len(c) >= 6:
                self.instances[iid]["color"] = c[:6].upper()

    # -------- geometry
    def footprint(self, inst):
        from shapely.geometry import Polygon

        it = self.cat.item(inst["item_id"])
        px, py, _ = inst["pivot"]
        pts = [
            (px + _rot(x, y, inst["yaw"])[0], py + _rot(x, y, inst["yaw"])[1])
            for x, y in (
                (it["lo"][0], it["lo"][1]),
                (it["hi"][0], it["lo"][1]),
                (it["hi"][0], it["hi"][1]),
                (it["lo"][0], it["hi"][1]),
            )
        ]
        return Polygon(pts)

    def bounds_world(self, inst):
        it = self.cat.item(inst["item_id"])
        xs, ys = zip(*self.footprint(inst).exterior.coords)
        return dict(
            min=[round(min(xs), 3), round(min(ys), 3), round(inst["pivot"][2] + it["lo"][2], 3)],
            max=[round(max(xs), 3), round(max(ys), 3), round(inst["pivot"][2] + it["hi"][2], 3)],
        )

    def view(self, inst):
        it = self.cat.item(inst["item_id"])
        cx, cy = (it["lo"][0] + it["hi"][0]) / 2, (it["lo"][1] + it["hi"][1]) / 2
        rx, ry = _rot(cx, cy, inst["yaw"])
        return dict(
            instance_id=inst["id"],
            item_id=inst["item_id"],
            name=inst["name"],
            dye=(self._dye_name(inst["color"]) if inst.get("color") else None),
            dyeable=it["dyeable"],
            pivot_m=[round(v, 3) for v in inst["pivot"]],
            yaw_deg=round(inst["yaw"] % 360, 3),
            bottom_center_m=[
                round(inst["pivot"][0] + rx, 3),
                round(inst["pivot"][1] + ry, 3),
                round(inst["pivot"][2] + it["lo"][2], 3),
            ],
            bounds_world=self.bounds_world(inst),
            placement_type=it["ptype"],
            front_deg=it["front_deg"],
            facing_deg=round((it["front_deg"] + inst["yaw"]) % 360, 1),
            front_guessed=it["front_guessed"],
        )

    @staticmethod
    def _dye_name(hex6):
        rgb = tuple(int(hex6[i : i + 2], 16) for i in (0, 2, 4))
        return next((n for n, c, _, _ in housing_stains() if c == rgb), "#" + hex6)

    def _set_dye(self, inst, spec):
        it = self.cat.item(inst["item_id"])
        if spec in (None, "", "default"):
            inst.pop("color", None)
            return
        if not it["dyeable"]:
            raise DecoError(
                "DYE_NOT_SUPPORTED", f"{inst['name']} is not dyeable; the app would ignore a colour"
            )
        n, rgb = resolve_dye(spec)
        inst["color"] = "%02X%02X%02X" % rgb

    def _pivot_from(self, it, anchor, pos, yaw):
        if anchor == "pivot":
            return list(pos)
        if anchor != "bottom_center":
            raise DecoError("BAD_INPUT", "anchor must be 'pivot' or 'bottom_center'")
        cx, cy = (it["lo"][0] + it["hi"][0]) / 2, (it["lo"][1] + it["hi"][1]) / 2
        rx, ry = _rot(cx, cy, yaw)
        return [pos[0] - rx, pos[1] - ry, pos[2] - it["lo"][2]]

    # -------- validation (physics only)
    instances_view = None

    ADVISORY = {
        "OUTSIDE_FLOOR",
        "STAIR_INTERSECTION",
        "STAIR_ACCESS_BLOCKED",
        "WALL_MOUNT_INVALID",
        "FACING_UNVERIFIED",
        "PILLAR_CONFLICT",
        "WINDOW_OVERLAP",
    }
    strict = False

    def validate(self, inst, issues, op_index=None):
        if self.instances_view is None:
            self.instances_view = self.instances
        it = self.cat.item(inst["item_id"])
        fp = self.footprint(inst)

        def add(code, msg):
            issues.append(dict(code=code, message=msg, instance_id=inst["id"], op_index=op_index))

        if not all(math.isfinite(v) for v in inst["pivot"] + [inst["yaw"]]):
            add("BAD_INPUT", "non-finite transform")
            return
        _zb = inst["pivot"][2] + it["lo"][2]
        _lv = self.room.level_of(_zb)
        if _lv == "ground" and self.room.openings:
            from shapely.geometry import box as _box

            _bw = self.bounds_world(inst)
            _thin = it["ptype"] == "wall" or (it["hi"][1] - it["lo"][1]) < 0.35
            for _o in self.room.openings:
                _x, _y = _o["xy"]
                _h = _o["half_width"]
                _d = 0.35 if _thin else 0.8
                _zone = (
                    _box(_x - _h, _y - _d, _x + _h, _y + _d)
                    if _o["along"] == "x"
                    else _box(_x - _d, _y - _h, _x + _d, _y + _h)
                )
                if (
                    fp.intersection(_zone).area > 0.03
                    and _bw["max"][2] > _o["z"][0] + 0.2
                    and _bw["min"][2] < _o["z"][1]
                ):
                    add(
                        "WINDOW_OVERLAP",
                        f"{it['name']} overlaps/covers the native {_o['kind']} at {_o['xy']} (z {_o['z'][0]}..{_o['z'][1]}); move it, or cover the opening deliberately (e.g. a full partition in front), or change the window/door style via set_fixtures",
                    )
        _pa = sum(fp.intersection(p).area for p in self.room.pillars_by_level.get(_lv, []))
        if _pa > 0.01:
            add(
                "PILLAR_CONFLICT",
                f"{it['name']} overlaps a structural pillar by {_pa:.2f} m2 (wall items: it would sit in/behind the pillar; floor items: clipped). See inspect.pillars",
            )
        if inst.get("faced") and it.get("front_guessed"):
            add(
                "FACING_UNVERIFIED",
                f"{it['name']}: front direction is a default guess (+Y), not measured; `face` may point the wrong way - check the render (back/kneehole/drawers) before trusting it",
            )
        if it["ptype"] == "wall" or (
            it["ptype"] == "floor"
            and it["hi"][1] - it["lo"][1] < 0.35
            and it["hi"][2] - it["lo"][2] > 0.5
            and (it["hi"][0] - it["lo"][0]) / max(it["hi"][1] - it["lo"][1], 1e-6) > 2.5
            and inst["pivot"][2] + it["lo"][2] > 0.3
        ):
            from shapely.geometry import Point

            d = self.room.boundary_distance(inst["pivot"][0], inst["pivot"][1], inst["pivot"][2])
            pt = Point(inst["pivot"][0], inst["pivot"][1])
            host = None
            if (
                d > 0.45
            ):  # a wall item may also hang on a placed tall object (partition, pillar, shelf) whose face is within reach and tall enough
                for o in self.instances_view.values():
                    if o["id"] == inst["id"]:
                        continue
                    oit = self.cat.item(o["item_id"])
                    if (
                        o["pivot"][2] + oit["hi"][2] >= inst["pivot"][2]
                        and o["pivot"][2] + oit["lo"][2] <= inst["pivot"][2]
                        and self.footprint(o).exterior.distance(pt) <= 0.45
                    ):
                        host = o["id"]
                        break
            if d > 0.45 and host is None:
                add(
                    "WALL_MOUNT_INVALID",
                    f"wall item pivot is {d:.2f} m from any wall and not on a placed object (must be within 0.45 m of a wall or of a tall item's face)",
                )
            return
        tol = (
            0.25 if inst["pivot"][2] + it["lo"][2] > 0.3 else TOL
        )  # raised items (on wall shelves/tables) may touch the wall surface; ground items may not
        lvl = self.room.floor_at(inst["pivot"][2] + it["lo"][2])
        if not lvl.buffer(tol).contains(fp):
            out = fp.difference(lvl.buffer(tol)).area
            add(
                "OUTSIDE_FLOOR",
                f"{out:.2f} m2 of the footprint lies outside the floor (walls / basement hole)",
            )
        zb = inst["pivot"][2] + it["lo"][2]
        si = self.room.stair_info()
        lvl_name = self.room.level_of(zb)
        if lvl_name == "basement" and "basement" in si:
            bsi = si["basement"]
            u = bsi.get("under") or {}
            enc = u.get("enclosed")
            top = zb + (it["hi"][2] - it["lo"][2]) + 7.0  # item top above the basement floor
            if enc is not None and fp.intersection(enc).area > 0.02:
                add(
                    "STAIR_INTERSECTION",
                    f"{fp.intersection(enc).area:.2f} m2 lies inside the boxed (closed) underside of the {self.room.style} basement stair: there is no space there",
                )
            elif u.get("cells") and it["ptype"] not in ("rug", "wall"):
                from shapely.geometry import box as _bx

                st = u["cell_m"]
                hit = [
                    (c, fp.intersection(_bx(c[0], c[1], c[0] + st, c[1] + st)).area)
                    for c in u["cells"]
                    if not c[3] and c[2] < top
                ]
                hit = [(c, a) for c, a in hit if a > 0.005]
                if sum(a for _, a in hit) > 0.02:
                    add(
                        "STAIR_INTERSECTION",
                        f"item top {top:.2f} m is above the stair underside there (min headroom {min(c[2] for c, _ in hit):.2f} m)",
                    )
            if (
                it["ptype"] != "rug"
                and bsi["foot_access"] is not None
                and fp.intersection(bsi["foot_access"]).area > 0.05
            ):
                add(
                    "STAIR_ACCESS_BLOCKED",
                    "item stands in the basement stair-foot approach zone; see inspect.stairs",
                )
            return
        if lvl_name == "ground" and zb < 1.0 and si["up"]["solid"] is not None:
            a = fp.intersection(si["up"]["solid"]).area
            if a > 0.02:
                add(
                    "STAIR_INTERSECTION",
                    f"footprint overlaps the up-stair body (below 2.4 m) by {a:.2f} m2",
                )
        if it["ptype"] != "rug" and zb - (self.room.UPPER_Z if lvl_name == "upper" else 0.0) < 1.8:
            zone = si["up"]["arrival_access"] if lvl_name == "upper" else si["up"]["foot_access"]
            if zone is not None and fp.intersection(zone).area > 0.05:
                add(
                    "STAIR_ACCESS_BLOCKED",
                    f"item stands in the {'upper arrival' if lvl_name == 'upper' else 'stair foot'} approach zone ({fp.intersection(zone).area:.2f} m2); see inspect.stairs",
                )

    def _budget(self, instances, issues):
        n = len(instances) + self.reserved_other_floors
        if n > self.room.limit:
            issues.append(
                dict(
                    code="BUDGET_EXCEEDED",
                    message=f"{n} > {self.room.limit} interior items (whole-house cap)",
                    instance_id=None,
                    op_index=None,
                )
            )

    # -------- operations
    def _new_id(self, st):
        while True:
            iid = f'i{st["next_id"]}'
            st["next_id"] += 1
            if iid not in st["instances"]:
                return iid

    def _resolve_item(self, op):
        return (
            self.cat.item(item_id=op.get("item_id"))
            if op.get("item_id") is not None
            else self.cat.item(name=op["name"]) if op.get("name") else None
        )

    def _get(self, st, iid):
        if iid not in st["instances"]:
            raise DecoError("UNKNOWN_INSTANCE", f"unknown instance {iid!r}")
        return st["instances"][iid]

    def _target_inst(self, st, op):
        iid = op.get("instance_id")
        it = self._resolve_item(op)
        if iid is not None and iid in st["instances"]:
            return st["instances"][iid], self.cat.item(st["instances"][iid]["item_id"])
        if it is None:
            raise DecoError(
                "UNKNOWN_INSTANCE" if iid is not None else "BAD_INPUT",
                (
                    f"unknown instance {iid!r}"
                    if iid is not None
                    else "operation needs instance_id or item_id/name"
                ),
            )
        if iid is not None and not (
            isinstance(iid, str)
            and iid.replace("_", "").replace("-", "").isalnum()
            and len(iid) <= 40
        ):
            raise DecoError("BAD_INPUT", "client instance_id must be alphanumeric/_/-")
        if self.cat._too_new(it["id"]):
            raise DecoError(
                "ITEM_TOO_NEW",
                f"{it['name']} is from patch {it['patch']}, newer than this session's max_patch {self.cat.max_patch}",
            )
        new = dict(
            id=iid or self._new_id(st), item_id=it["id"], name=it["name"], pivot=[0, 0, 0], yaw=0.0
        )
        st["instances"][new["id"]] = new
        return new, it

    def _apply_one(self, st, op):
        kind = op.get("op")
        touched = set()
        removed = set()
        if kind == "remove":
            self._get(st, op["instance_id"])
            del st["instances"][op["instance_id"]]
            removed.add(op["instance_id"])
            return touched, removed
        if kind == "place":
            inst, it = self._target_inst(st, op)
            yaw = _num(op.get("yaw_deg", 0), "yaw_deg")
            pos = _vec(op.get("position"), 3, "position")
            inst["yaw"] = yaw
            inst["pivot"] = self._pivot_from(it, op.get("anchor", "bottom_center"), pos, yaw)
            touched.add(inst["id"])
            if op.get("color") is not None:
                self._set_dye(inst, op["color"])
        elif kind == "move":
            inst = self._get(st, op["instance_id"])
            it = self.cat.item(inst["item_id"])
            if "delta" in op:
                d = _vec(op["delta"], 3, "delta")
                inst["pivot"] = [inst["pivot"][i] + d[i] for i in range(3)]
            else:
                inst["pivot"] = self._pivot_from(
                    it,
                    op.get("anchor", "bottom_center"),
                    _vec(op.get("position"), 3, "position"),
                    inst["yaw"],
                )
            touched.add(inst["id"])
        elif kind == "rotate":
            inst = self._get(st, op["instance_id"])
            it = self.cat.item(inst["item_id"])
            anchor = op.get("anchor", "bottom_center")
            new = (
                _num(op["yaw_deg"], "yaw_deg")
                if "yaw_deg" in op
                else inst["yaw"] + _num(op.get("yaw_delta_deg"), "yaw_delta_deg")
            )
            if anchor == "bottom_center":
                v = self.view(inst)["bottom_center_m"]
                inst["yaw"] = new
                inst["pivot"] = self._pivot_from(it, "bottom_center", v, new)
            else:
                inst["yaw"] = new
            touched.add(inst["id"])
        elif kind == "interior":
            room = Room(op.get("style"), self.room.house_size)
            st["style"] = room.style
        elif kind == "dye":
            inst = self._get(st, op["instance_id"])
            self._set_dye(inst, op.get("color"))
            touched.add(inst["id"])
        elif kind == "fixture":
            ft = op.get("type")
            lvl = op.get("level", "ground")
            if ft not in ("Wall", "Floor", "Light", "Window", "Door"):
                raise DecoError(
                    "BAD_INPUT", "fixture type must be Wall, Floor, Light, Window or Door"
                )
            if ft in ("Window", "Door"):
                lvl = "ground"
            if lvl not in self.room.levels:
                raise DecoError(
                    "BAD_INPUT",
                    f"level must be one of {list(self.room.levels)} for a {self.room.house_size}",
                )
            row = self.cat.material(op.get("item_id"), op.get("name"), ft)
            st.setdefault("fixtures", {})[
                (
                    ("Ext:" + ft)
                    if ft in ("Window", "Door")
                    else (
                        ft
                        if lvl == "ground"
                        else {"upper": "Upper:", "basement": "Basement:"}[lvl] + ft
                    )
                )
            ] = dict(item_id=row["item_id"], name=row["name"])
        elif kind == "face":
            inst = self._get(st, op["instance_id"])
            it = self.cat.item(inst["item_id"])
            v = self.view(inst)["bottom_center_m"]
            if "target_id" in op:
                t = self.view(self._get(st, op["target_id"]))["bottom_center_m"]
                ang = math.degrees(math.atan2(t[1] - v[1], t[0] - v[0]))
            else:
                ang = _num(op["direction_deg"], "direction_deg")
            inst["yaw"] = (ang - it["front_deg"]) % 360
            inst["pivot"] = self._pivot_from(it, "bottom_center", v, inst["yaw"])
            touched.add(inst["id"])
            inst["faced"] = True
        elif kind == "place_on":
            tgt = self._get(st, op["target_id"])
            tit = self.cat.item(tgt["item_id"])
            inst, it = self._target_inst(st, op)
            surfs = tit["surfaces"]
            if "surface_idx" in op:
                s = next((x for x in surfs if x["idx"] == op["surface_idx"]), None)
            else:
                s = next((x for x in reversed(surfs) if x["is_top"]), surfs[-1] if surfs else None)
            if s is None:
                raise DecoError(
                    "SURFACE_UNVERIFIED",
                    f"{tit['name']} has no measured support surface; use place with an explicit z instead",
                )
            off = _vec(op.get("offset_xy", [0, 0]), 2, "offset_xy")
            lx, ly = (s["min"][0] + s["max"][0]) / 2 + off[0], (
                s["min"][1] + s["max"][1]
            ) / 2 + off[1]
            rx, ry = _rot(lx, ly, tgt["yaw"])
            yaw = _num(op.get("yaw_deg", tgt["yaw"]), "yaw_deg")
            gap = _num(op.get("gap_m", 0), "gap_m")
            inst["yaw"] = yaw
            inst["pivot"] = self._pivot_from(
                it,
                "bottom_center",
                [tgt["pivot"][0] + rx, tgt["pivot"][1] + ry, tgt["pivot"][2] + s["z"] + gap],
                yaw,
            )
            touched.add(inst["id"])
        elif kind == "place_along_wall":
            level = op.get("level", "ground")
            if level not in self.room.levels:
                raise DecoError("BAD_INPUT", f"level must be one of {list(self.room.levels)}")
            room = (
                self.room
                if st.get("style", self.room.style) == self.room.style
                else Room(st["style"], self.room.house_size)
            )
            w = next(
                (x for x in room.walls_by_level[level] if x["wall_id"] == op.get("wall_id")), None
            )
            if w is None:
                raise DecoError(
                    "BAD_INPUT", f"unknown wall_id {op.get('wall_id')!r}; inspect lists walls"
                )
            inst, it = self._target_inst(st, op)
            ax, ay = w["start"]
            bx, by = w["end"]
            L = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / L, (by - ay) / L
            along = _num(op["along_m"], "along_m")
            gap = _num(op.get("gap_m", 0), "gap_m")
            nx, ny = w["inward"]
            if op.get("facing", "inward") not in ("inward", "outward"):
                raise DecoError("BAD_INPUT", "facing must be 'inward' or 'outward'")
            ang = math.degrees(math.atan2(ny, nx)) + (
                180 if op.get("facing", "inward") == "outward" else 0
            )
            inst["yaw"] = (ang - it["front_deg"]) % 360
            if it["ptype"] == "wall":
                px, py = ax + ux * along, ay + uy * along
                z = room.level_z[level] + _num(op.get("height_m", 1.5), "height_m")
                inst["pivot"] = [px + nx * gap, py + ny * gap, z]
            else:
                fp = self.footprint(dict(inst, pivot=[0, 0, 0]))
                m = min(x * nx + y * ny for x, y in fp.exterior.coords)
                c = fp.centroid
                wall_n = ax * nx + ay * ny
                along_u = ax * ux + ay * uy + along - (c.x * ux + c.y * uy)
                n_off = wall_n + gap - m
                inst["pivot"] = [
                    nx * n_off + ux * along_u,
                    ny * n_off + uy * along_u,
                    _num(op.get("z", room.level_z[level]), "z") - it["lo"][2],
                ]
            touched.add(inst["id"])
        else:
            raise DecoError("BAD_INPUT", f"unknown op {kind!r}")
        return touched, removed

    def apply(self, ops, expected_revision=None, label="", strict=False):
        if expected_revision is not None and expected_revision != self.revision:
            raise DecoError(
                "REVISION_CONFLICT",
                f"expected revision {expected_revision}, session is at {self.revision}",
            )
        if not isinstance(ops, list) or not 1 <= len(ops) <= 450:
            raise DecoError("BAD_INPUT", "operations must be a list of 1..450")
        st = self._state()
        touched = set()
        removed = set()
        issues = []
        idx_of = {}
        for i, op in enumerate(ops):
            try:
                t, r = self._apply_one(st, op)
                touched |= t
                removed |= r
                touched -= r
                for x in t:
                    idx_of[x] = i
            except DecoError as e:
                issues.append(
                    dict(
                        code=e.code,
                        message=e.message,
                        instance_id=op.get("instance_id"),
                        op_index=i,
                    )
                )
            except KeyError as e:
                issues.append(
                    dict(
                        code="BAD_INPUT",
                        message=f"missing field {e}",
                        instance_id=op.get("instance_id"),
                        op_index=i,
                    )
                )
        if not issues:
            old_room = self.room
            try:
                if st.get("style", self.room.style) != self.room.style:
                    self.room = Room(st["style"], self.room.house_size)
                    touched.update(st["instances"])
                self.instances_view = st["instances"]
                for iid in touched:
                    if iid in st["instances"]:
                        n0 = len(issues)
                        self.validate(st["instances"][iid], issues)
                        for x in issues[n0:]:
                            x["op_index"] = idx_of.get(iid)
                self._budget(st["instances"], issues)
            finally:
                self.room = old_room
                self.instances_view = None
        advisory = [
            i
            for i in issues
            if i["code"] in self.ADVISORY and (not strict or i["code"] == "FACING_UNVERIFIED")
        ]
        issues = [i for i in issues if i not in advisory]
        for a in advisory:
            a["severity"] = "advisory"
        if issues:
            raise DecoError("REJECTED", f"{len(issues)} problem(s); nothing was changed", issues)
        self.undo_stack.append(
            dict(revision=self.revision, state=self._state(), label=label or ops[0].get("op"))
        )
        self.redo_stack = []
        self._set_state(st)
        self.revision += 1
        self._save()
        return dict(
            ok=True,
            revision=self.revision,
            style=self.room.style,
            changed=[
                self.view(self.instances[i]) for i in [k for k in self.instances if k in touched]
            ],
            removed=sorted(removed),
            count=len(self.instances),
            warnings=advisory + self._warnings(touched),
        )

    def _warnings(self, touched):
        w = []
        for iid in touched:
            inst = self.instances.get(iid)
            if inst is None:
                continue
            fp = self.footprint(inst)
            it = self.cat.item(inst["item_id"])
            if it["ptype"] in ("floor", "rug") and it["hi"][2] - it["lo"][2] > 0.3:
                for o in self.instances.values():
                    if (
                        o["id"] != iid
                        and self.cat.item(o["item_id"])["ptype"] in ("floor",)
                        and fp.intersection(self.footprint(o)).area
                        > 0.6 * min(fp.area, self.footprint(o).area)
                        and abs(o["pivot"][2] - inst["pivot"][2]) < 0.3
                    ):
                        w.append(
                            dict(
                                code="LARGE_OVERLAP",
                                message=f"{inst['name']} overlaps {o['name']} ({o['id']}) heavily (legal; check it is deliberate)",
                                instance_id=iid,
                            )
                        )
                        break
        return w[:8]

    # -------- history
    def undo(self):
        if not self.undo_stack:
            raise DecoError("NOTHING_TO_UNDO", "undo stack empty")
        u = self.undo_stack.pop()
        self.redo_stack.append(dict(revision=self.revision, state=self._state(), label="undo"))
        self._set_state(u["state"])
        self.revision += 1
        self._save()
        return self.status()

    def redo(self):
        if not self.redo_stack:
            raise DecoError("NOTHING_TO_REDO", "redo stack empty")
        r = self.redo_stack.pop()
        self.undo_stack.append(dict(revision=self.revision, state=self._state(), label="redo"))
        self._set_state(r["state"])
        self.revision += 1
        self._save()
        return self.status()

    def snapshot(self, label):
        sid = f"s{len(self.snapshots) + 1}"
        self.snapshots[sid] = dict(
            label=label, revision=self.revision, state=self._state(), sha=self.state_hash()
        )
        self._save()
        return dict(
            ok=True,
            snapshot_id=sid,
            revision=self.revision,
            state_sha256=self.snapshots[sid]["sha"],
        )

    def restore(self, sid):
        if sid not in self.snapshots:
            raise DecoError("UNKNOWN_SNAPSHOT", f"unknown snapshot {sid!r}")
        st = self.snapshots[sid]["state"]
        issues = []
        previous = self.room
        try:
            self.room = Room(
                house_size=previous.house_size,
                style=st.get(
                    "style",
                    next(
                        (
                            f["name"]
                            for f in (self.seed or {}).get("interiorFixture", [])
                            if f["type"] == "District"
                        ),
                        previous.style,
                    ),
                ).replace(" ", ""),
            )
            self.instances_view = st["instances"]
            for inst in st["instances"].values():
                self.validate(inst, issues)
        finally:
            self.room = previous
            self.instances_view = None
        issues = [i for i in issues if i["code"] not in self.ADVISORY]
        if issues:
            raise DecoError("REJECTED", "snapshot no longer validates", issues)
        self.undo_stack.append(
            dict(revision=self.revision, state=self._state(), label=f"restore {sid}")
        )
        self.redo_stack = []
        self._set_state(st)
        self.revision += 1
        self._save()
        return self.status()

    def state_hash(self):
        return hashlib.sha256(json.dumps(self._state(), sort_keys=True).encode()).hexdigest()

    def status(self):
        return dict(
            ok=True,
            revision=self.revision,
            style=self.room.style,
            house_size=self.room.house_size,
            capabilities={
                "levels": list(self.room.levels),
                "render": True,
                "switch_interior": True,
                "app_verified": False,
            },
            count=len(self.instances),
            limit=self.room.limit,
            max_patch=self.max_patch,
            snapshots={
                k: dict(label=v["label"], revision=v["revision"]) for k, v in self.snapshots.items()
            },
            can_undo=bool(self.undo_stack),
            can_redo=bool(self.redo_stack),
        )

    def inspect(self, region=None, instance_ids=(), level="ground"):
        if level not in self.room.levels:
            raise DecoError(
                "BAD_INPUT",
                f"level must be one of {list(self.room.levels)} for a {self.room.house_size}",
            )
        out = []
        for inst in self.instances.values():
            if instance_ids and inst["id"] not in instance_ids:
                continue
            v = self.view(inst)
            if region:
                lo, hi = region["min"], region["max"]
                b = v["bounds_world"]
                if (
                    b["max"][0] < lo[0]
                    or b["min"][0] > hi[0]
                    or b["max"][1] < lo[1]
                    or b["min"][1] > hi[1]
                ):
                    continue
            out.append(v)
        surf = []
        for v in out:
            it = self.cat.item(v["item_id"])
            for s in it["surfaces"]:
                if s["is_top"] or s["clearance_m"] > 0.3:
                    surf.append(
                        dict(
                            owner_id=v["instance_id"],
                            surface_idx=s["idx"],
                            z_world=round(self.instances[v["instance_id"]]["pivot"][2] + s["z"], 3),
                            size=[
                                round(s["max"][0] - s["min"][0], 2),
                                round(s["max"][1] - s["min"][1], 2),
                            ],
                            is_top=s["is_top"],
                        )
                    )
        return dict(
            ok=True,
            revision=self.revision,
            instances=out,
            surfaces=surf[:200],
            style=self.room.style,
            level=level,
            profile=self.room.profile.summary(),
            walls=self.room.walls_by_level[level],
            floor_polygon=[
                [round(x, 3), round(y, 3)] for x, y in self.room.polys[level].exterior.coords
            ],
            openings=self.room.openings,
            stair_footprints=[
                [[round(x, 2), round(y, 2)] for x, y in s.exterior.coords]
                for s in self.room.profile.stair_footprints(level)
            ],
            stair_clearance=self.room.stair_clearance(),
            stairs=self.room.stair_summary(),
            pillars=[
                [round(v, 2) for v in p.bounds] for p in self.room.pillars_by_level.get(level, [])
            ],
            used=len(self.instances),
            limit=self.room.limit,
        )

    # -------- export / layout
    def layout_dict(self):
        if self.seed is None:
            raise DecoError("IO_ERROR", "session has no seed layout (fixtures/metadata)")
        d = copy.deepcopy(self.seed)
        items = []
        slots = [f for f in d.get("interiorFixture", []) if f["type"] == "District"]
        if len(slots) != 1:
            raise DecoError("IO_ERROR", "seed requires one District slot")
        # the app matches District by its spaced display name ('Dark Minimalist'), not our
        # compact geometry token ('DarkMinimalist'): split camelCase so both worlds agree.
        slots[0]["name"] = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", self.room.style)
        # house sizes without an upper floor must not ship leftover Upper Floor fixture slots
        if "upper" not in self.room.levels:
            d["interiorFixture"] = [
                f for f in d["interiorFixture"] if f.get("level") != "Upper Floor"
            ]
        for key, sel in self.fixtures.items():
            ft = key.split(":")[-1]
            level = (
                "Upper Floor"
                if key.startswith("Upper:")
                else (
                    "Basement"
                    if key.startswith("Basement:")
                    else ("" if key.startswith("Ext:") else "Ground Floor")
                )
            )
            slot = [
                x
                for x in d.get(
                    "exteriorFixture" if key.startswith("Ext:") else "interiorFixture", []
                )
                if x["type"] == ft and x.get("level", "") == level
            ]
            if len(slot) != 1:
                raise DecoError("IO_ERROR", f"seed has no unique {level} {ft} slot")
            slot[0].update({"name": sel["name"], "itemId": sel["item_id"], "color": ""})
        for inst in self.instances.values():
            a = math.radians(inst["yaw"])
            items.append(
                {
                    "itemId": inst["item_id"],
                    "name": inst["name"],
                    "transform": {
                        "location": [round(v * 100, 2) for v in inst["pivot"]],
                        "rotation": [0, 0, round(math.sin(a / 2), 6), round(math.cos(a / 2), 6)],
                        "scale": [1, 1, 1],
                    },
                    "properties": ({"color": inst["color"] + "FF"} if inst.get("color") else {}),
                    "attachments": [],
                }
            )
        d["interiorFurniture"] = items
        return d

    def write_layout(self, path):
        data = b"\xff\xfe" + json.dumps(self.layout_dict(), ensure_ascii=False).encode("utf-16-le")
        path = Path(path)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return data

    def export(self, name):
        safe = "".join(c for c in name if c.isalnum() or c in "-_") or "layout"
        p = self.dir / f"{safe}-r{self.revision}.json"
        data = self.write_layout(p)
        back = json.loads(p.read_bytes())
        assert len(back["interiorFurniture"]) == len(self.instances)
        m = self.dir / f"{safe}-r{self.revision}.map.json"
        m.write_text(
            json.dumps(
                [dict(index=i, instance_id=k) for i, k in enumerate(self.instances)], indent=1
            ),
            encoding="utf-8",
        )
        return dict(
            ok=True,
            revision=self.revision,
            layout=dict(path=str(p), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)),
            instance_map=str(m),
            item_count=len(self.instances),
            encoding="UTF-16LE-BOM",
            note="valid JSON round-trip only; not verified by importing into ReMakePlace",
        )
