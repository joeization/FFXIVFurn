"""Native exterior fixtures and shared scene profile; no catalog or app writes."""

from pathlib import Path

from copy import deepcopy
import struct
import math
import numpy as np
from .config import source_path, catalog_path

ROOT = Path(__file__).resolve().parents[1]
SIZES = ("Small", "Medium", "Large")
CATEGORY_CODES = {
    3: "MainDoor",
    5: "Window",
    9: "Roof",
    10: "RoofDecor",
    11: "ExteriorWall",
    12: "ExteriorWallDecor",
    13: "Placard",
    14: "Fence",
}
FIXTURE_TYPES = {
    "ExteriorWall": "ExteriorWall",
    "Roof": "Roof",
    "Fence": "Fence",
    "Door": "MainDoor",
    "Window": "Window",
    "RoofDecor": "RoofDecor",
    "WallDecor": "ExteriorWallDecor",
    "Placard": "Placard",
}
KINDS = {
    "wall": "ExteriorWall",
    "exterior_wall": "ExteriorWall",
    "roof": "Roof",
    "fence": "Fence",
    "door": "MainDoor",
    "window": "Window",
    "roof_decor": "RoofDecor",
    "wall_decor": "ExteriorWallDecor",
    "placard": "Placard",
}
TYPE_FOR_CATEGORY = {v: k for k, v in FIXTURE_TYPES.items()}


def native_exterior_actors(size):
    """Bounded UE5.3 component schema. Reject unknown fields rather than guess poses."""
    from .rendering.native import Reader, names, tables

    if size not in SIZES:
        raise ValueError("Exterior scene requires Small, Medium or Large")
    path = source_path("houses") / "Maps" / ("XIV" + size + "Exterior.umap")
    tab = tables.map_tables(path)
    data = path.with_suffix(".uexp").read_bytes()
    nm = names(path)
    exports = {e["index"]: e for e in tab["exports"]}
    imports = {e["index"]: e for e in tab["imports"]}
    actors = []
    for comp in tab["exports"]:
        if not comp["class"].endswith(".StaticMeshComponent"):
            continue
        parent = exports[comp["outer"]]
        if not parent["class"].endswith((".HouseFixture", ".StaticMeshActor")):
            raise ValueError("Unsupported exterior mesh parent")
        raw = data[
            comp["serial_offset_in_uexp"] : comp["serial_offset_in_uexp"] + comp["serial_size"]
        ]
        reader = Reader(raw, nm)
        fields, zero = reader.header()
        ref = reader.read("<i")
        mesh = imports[ref]
        if mesh["class"] != "StaticMesh":
            raise ValueError("Exterior component has no native mesh")
        if parent["class"].endswith(".HouseFixture"):
            actor_raw = data[
                parent["serial_offset_in_uexp"] : parent["serial_offset_in_uexp"]
                + parent["serial_size"]
            ]
            ar = Reader(actor_raw, nm)
            af, az = ar.header()
            if not {0, 5, 7, 69} <= set(af) or set(af) - {0, 1, 2, 5, 7, 69} or az:
                raise ValueError("Unsupported HouseFixture property layout")
            category = CATEGORY_CODES[ar.read("<B")]
        else:
            category = "Ground"
        if category == "Ground":
            if (
                set(fields) != {4, 33, 110}
                or zero != ({110} if size != "Large" else set())
                or len(raw) != {"Small": 49, "Medium": 53, "Large": 56}[size]
            ):
                raise ValueError("Unsupported ground component schema")
            loc = (0.0, 0.0, 0.0)
            rot = (0.0, 0.0, 0.0)
            scale = (1.0, 1.0, 1.0)
        else:
            if (
                not {4, 124, 148, 169} <= set(fields)
                or set(fields) - {4, 23, 124, 148, 149, 150, 169}
                or zero
            ):
                raise ValueError("Unsupported exterior component transform schema")
            # Validated serialized primitive-property prefixes precede RelativeLocation.
            prefixes = [
                bytes.fromhex(x)
                for x in (
                    "00000214020d03010200000000000000ffff6045",
                    "15020d030200000000000000ffff6045",
                    "2303ffff6045",
                )
            ]
            prefix = next((p for p in prefixes if raw[reader.pos :].startswith(p)), None)
            if prefix is None:
                raise ValueError("Unsupported exterior primitive properties: " + parent["name"])
            pos = reader.pos + len(prefix)
            loc = struct.unpack_from("<3d", raw, pos)
            pos += 24
            rot = struct.unpack_from("<3d", raw, pos) if 149 in fields else (0.0, 0.0, 0.0)
            pos += 24 * (149 in fields)
            scale = struct.unpack_from("<3d", raw, pos) if 150 in fields else (1.0, 1.0, 1.0)
            pos += 24 * (150 in fields)
            if raw[pos:] not in (
                b"\x02" + bytes(12),
                bytes.fromhex("02000000000000000001000000010100000000000000000000000000000000"),
            ):
                raise ValueError("Unsupported exterior component tail")
            if abs(rot[0]) + abs(rot[2]) > 1e-5:
                raise ValueError("Non-yaw exterior rotation requires explicit decoder support")
        if not all(math.isfinite(x) for x in (*loc, *rot, *scale)) or any(
            abs(s) < 1e-8 for s in scale
        ):
            raise ValueError("Invalid exterior transform")
        actors.append(
            dict(
                name=parent["name"],
                category=category,
                native_reference=mesh["resolved"],
                translation_m=[v / 100 for v in loc],
                yaw_degrees=rot[1],
                scale=list(scale),
                component_export=comp["index"],
                map_sha256=tab["sha256"],
                evidence="native component RelativeLocation/Rotation/Scale; absent transform fields use engine defaults",
                app_verified=False,
            )
        )
    expected = {"Small": 30, "Medium": 42, "Large": 60}[size]
    if len(actors) != expected:
        raise ValueError("Unexpected exterior component count")
    return actors


def category_for_type(value):
    return {
        "Wall": "ExteriorWall",
        "Exterior Wall": "ExteriorWall",
        "MainDoor": "MainDoor",
        "RoofDecoration": "RoofDecor",
        "WallDecoration": "ExteriorWallDecor",
    }.get(value, FIXTURE_TYPES.get(value, value))


def compatible(name, size, category):
    if category not in ("ExteriorWall", "Roof"):
        return True
    token = {"Small": "Cottage", "Medium": "House", "Large": "Mansion"}[size]
    return token in name


def fixture_row(db, size, category, *, name=None, item_id=None):
    clause = "item_id=?" if item_id is not None else "name=?"
    rows = db.execute(
        "SELECT * FROM house_materials WHERE category=? AND " + clause,
        (category, item_id if item_id is not None else name),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError(
            "No unique exterior "
            + category
            + " fixture: "
            + str(item_id if item_id is not None else name)
        )
    row = dict(rows[0])
    if not compatible(row["name"], size, category):
        raise ValueError(row["name"] + " is not compatible with " + size)
    return row


def fixture_folder(row):
    return source_path("materials") / Path(row["asset_key"]).relative_to("MakePlace/Content")


class ExteriorProfile:
    style = "Exterior"
    levels = ("ground",)

    def __init__(self, house_size="Small", fixtures=(), db_path=None):
        if house_size not in SIZES:
            raise ValueError("Exterior scene requires Small, Medium or Large")
        self.house_size = house_size
        self.db_path = Path(db_path or catalog_path()).resolve()
        self.fixtures = deepcopy(list(fixtures))

    def scene(self):
        import sqlite3
        from contextlib import closing
        from .rendering.assets import find_asset

        selected = {}
        with closing(sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            for fixture in self.fixtures:
                cat = category_for_type(fixture.get("type"))
                if cat not in FIXTURE_TYPES.values():
                    raise ValueError(
                        "Unsupported exterior fixture type: " + str(fixture.get("type"))
                    )
                if cat in selected:
                    raise ValueError("Duplicate exterior fixture slot: " + cat)
                if fixture.get("name") in ("", "Empty", None) and not fixture.get("itemId"):
                    continue
                row = (
                    fixture_row(db, self.house_size, cat, name=fixture.get("name"))
                    if fixture.get("name")
                    else fixture_row(db, self.house_size, cat, item_id=fixture.get("itemId"))
                )
                if fixture.get("itemId") and fixture["itemId"] != row["item_id"]:
                    raise ValueError("Conflicting exterior fixture itemId/name")
                selected[cat] = (row, fixture)
        output = []
        content = source_path("houses")
        for template in native_exterior_actors(self.house_size):
            actor = deepcopy(template)
            cat = actor["category"]
            native_ref = actor["native_reference"]
            color = None
            if cat in selected:
                row, fixture = selected[cat]
                folder = fixture_folder(row)
                suffix = ""
                if cat == "Fence":
                    original = native_ref.split(".")[0].rsplit("/", 1)[-1]
                    suffix = next((s for s in ("_b", "_c", "_d") if original.endswith(s)), "")
                path = folder / (folder.name + suffix + ".uexp")
                actor.update(fixture_name=row["name"], fixture_item_id=row["item_id"])
                rawcolor = fixture.get("color", "")
                if rawcolor:
                    color = rawcolor
            else:
                if "/Others/Empty/" in native_ref:
                    continue
                path = find_asset(content, native_ref.split(".")[0]).with_suffix(".uexp")
            if not path.is_file():
                raise ValueError("Missing native exterior mesh: " + str(path))
            actor.update(mesh=str(path), color=color)
            output.append(actor)
        return output

    def polygon(self, level="ground"):
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        from .geometry import read_static_mesh_bounds
        from .geometry_mesh import read_static_mesh_triangles
        from .rendering.projection import projected_footprint
        from .interiors import transform_points

        if level != "ground":
            return Polygon()
        polys = {}
        for actor in self.scene():
            if actor["category"] not in ("Ground", "ExteriorWall"):
                continue
            v, t = read_static_mesh_triangles(read_static_mesh_bounds(Path(actor["mesh"])))
            polys[actor["category"]] = projected_footprint(
                transform_points(v, actor), np.asarray(t)
            )
        ground = polys["Ground"]
        wall = polys.get("ExteriorWall")
        if wall is not None:
            building = unary_union(
                [Polygon(p.exterior) for p in getattr(wall, "geoms", [wall]) if p.area > 1e-6]
            )
            ground = ground.difference(building)
        return ground

    def stair_footprints(self, level="ground"):
        return []

    def pillar_footprints(self, level="ground"):
        return []

    def summary(self):
        return dict(
            scope="exterior",
            house_size=self.house_size,
            levels={"ground": 0.0},
            renderable=True,
            app_verified=False,
            native_transforms_decoded=True,
            limitations=[
                "Native component transforms decoded from exterior map; app placement/camera calibration not verified.",
                "Yard region subtracts filled native wall projection; not character navigation or collision.",
                "Native shader graphs, water, reflections and game sunlight are not reconstructed.",
            ],
        )
