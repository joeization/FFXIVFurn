"""Scoped indoor/yard editing over stdio MCP with native GPU previews.
Set DECO_SESSION, DECO_SCOPE and an explicit DECO_SEED layout path.
DECO_FROM_LAYOUT=1 imports furniture only on first creation; otherwise start empty.
No DB, game resources or private seed is distributed. stdout is protocol-only.
Run with the Python environment containing requirements-render.txt."""

from __future__ import annotations
from collections import OrderedDict
import hashlib, json, sys, time
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from .core import Catalog, Room, Session, DecoError, ROOT
from ..config import load_seed_layout, source_path

SESS_DIR = ROOT / "outputs/deco-sessions"

CAMERAS = {
    "overview": {
        "position": [13, -3, 21],
        "target": [0, 0, 0],
        "fov": 60,
        "cutaway": True,
        "cut_stairs_z": 3.0,
    },
    "overview_ne": {
        "position": [15, 13, 14],
        "target": [-1, -2, 0],
        "fov": 60,
        "cutaway": True,
        "cut_stairs_z": 3.0,
    },
    "overview_nw": {
        "position": [-15, 13, 14],
        "target": [1, -2, 0],
        "fov": 60,
        "cutaway": True,
        "cut_stairs_z": 3.0,
    },
    "entry": {"position": [0, 7.4, 2.4], "target": [0, -8, 1.2], "fov": 85},
    "tea": {"position": [0, -0.2, 2.8], "target": [0, -7, 0.9], "fov": 80},
    "library": {"position": [-5.6, -1.0, 2.6], "target": [-10, -6.2, 1.2], "fov": 90},
    "east": {"position": [5.5, -2.7, 2.7], "target": [11, -6.5, 1.0], "fov": 90},
    "garden": {"position": [-2.6, 4.2, 2.8], "target": [-9.0, -0.5, 1.0], "fov": 85},
    "up_overview": {
        "position": [15, -14, 27],
        "target": [0, 0, 7],
        "fov": 60,
        "cutaway": True,
        "hide_below_z": 6.9,
        "upper": True,
    },
    "up_overview_n": {
        "position": [15, 14, 24],
        "target": [-1, -2, 7],
        "fov": 60,
        "cutaway": True,
        "hide_below_z": 6.9,
        "upper": True,
    },
    "up_top": {
        "position": [0.5, 0, 52],
        "target": [0, 0, 7],
        "fov": 32,
        "cutaway": True,
        "hide_below_z": 6.9,
        "upper": True,
    },
    "up_entry": {"position": [1.0, -0.8, 9.6], "target": [-1, 8, 8.2], "fov": 85, "upper": True},
    "up_south": {"position": [0, 7.2, 9.6], "target": [0, -8, 8.2], "fov": 75, "upper": True},
    "up_west": {"position": [3, 0, 9.6], "target": [-12, 3, 8.2], "fov": 80, "upper": True},
    "west_wall": {"position": [8, -2, 2.4], "target": [-12, -2, 1.5], "fov": 80},
    "east_wall": {"position": [-8, -2, 2.4], "target": [12, -2, 1.5], "fov": 80},
    "south_wall": {"position": [0, 7, 2.6], "target": [0, -8, 1.5], "fov": 70},
    "north_wall": {"position": [0, -7, 2.6], "target": [0, 8, 1.5], "fov": 70},
}
# Apartment (single 12 x 16 m floor, ceiling 6.5 m, door at the north wall centre (0, 8)); no upper/stair views
APT_CAMERAS = {
    "overview": {"position": [11, -13, 17], "target": [0, 0, 0], "fov": 60, "cutaway": True},
    "overview_ne": {"position": [12, 14, 13], "target": [0, -1, 0], "fov": 60, "cutaway": True},
    "overview_nw": {"position": [-12, 14, 13], "target": [0, -1, 0], "fov": 60, "cutaway": True},
    "top": {"position": [0.5, 0, 40], "target": [0, 0, 0], "fov": 32, "cutaway": True},
    "entry": {"position": [0, 7.4, 2.4], "target": [0, -8, 1.2], "fov": 85},
    "south": {"position": [0, 7.0, 2.6], "target": [0, -8, 1.3], "fov": 75},
    "north": {"position": [0, -7.0, 2.6], "target": [0, 8, 1.3], "fov": 75},
    "west": {"position": [4.5, 0, 2.5], "target": [-6, 0, 1.3], "fov": 85},
    "east": {"position": [-4.5, 0, 2.5], "target": [6, 0, 1.3], "fov": 85},
    "south_west": {"position": [4.5, 6.5, 2.6], "target": [-6, -8, 1.0], "fov": 85},
    "south_east": {"position": [-4.5, 6.5, 2.6], "target": [6, -8, 1.0], "fov": 85},
}
# Small (main room x-6..6,y-6..6, door (0,6); basement stairwell east strip x6..10)
SMALL_CAMERAS = {
    "overview": {
        "position": [12, -12, 16],
        "target": [1, 0, 0],
        "fov": 60,
        "cutaway": True,
        "hide_below_z": -0.6,
        "hide_above_z": 4.6,
    },
    "overview_nw": {
        "position": [-11, 12, 14],
        "target": [1, -1, 0],
        "fov": 60,
        "cutaway": True,
        "hide_below_z": -0.6,
        "hide_above_z": 4.6,
    },
    "top": {
        "position": [1.5, 0, 38],
        "target": [1.5, 0, 0],
        "fov": 44,
        "cutaway": True,
        "hide_below_z": -0.6,
        "hide_above_z": 4.6,
    },  # ground plans must not show basement furniture beyond the ground footprint
    "entry": {"position": [0, 5.4, 2.4], "target": [0, -6, 1.2], "fov": 85},
    "south": {"position": [0, 5.0, 2.6], "target": [0, -6, 1.3], "fov": 80},
    "north": {"position": [0, -5.0, 2.6], "target": [0, 6, 1.3], "fov": 80},
    "west": {"position": [4.5, 0, 2.5], "target": [-6, 0, 1.3], "fov": 85},
    "east": {"position": [-4.5, 0, 2.5], "target": [9, -2, 1.3], "fov": 85},
    "bs_overview": {
        "position": [14, -12, 12],
        "target": [2, 4, -7],
        "fov": 60,
        "cutaway": True,
        "hide_above_z": -0.6,
        "basement": True,
    },
    "bs_top": {
        "position": [2.5, 4, 30],
        "target": [2, 4, -7],
        "fov": 40,
        "cutaway": True,
        "hide_above_z": -0.6,
        "basement": True,
    },
    "bs_stair": {"position": [8, 9.5, -4.6], "target": [0, 2, -6.0], "fov": 85, "basement": True},
    "bs_north": {"position": [2, -5, -4.6], "target": [2, 14, -6.0], "fov": 80, "basement": True},
    "bs_south": {"position": [2, 13, -4.6], "target": [2, -6, -6.0], "fov": 80, "basement": True},
}


def _cameras():
    if _sess is None:
        return CAMERAS
    if getattr(getattr(_sess, "cat", None), "scope", "interior") == "exterior":
        x0, y0, x1, y1 = _sess.room.floor.bounds
        r = max(x1 - x0, y1 - y0)
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        return dict(
            overview=dict(
                position=[cx + 0.85 * r, cy + 0.9 * r, 0.8 * r], target=[cx, cy, 2], fov=65
            ),
            entry=dict(position=[cx, y1 + 4, 2.6], target=[cx, cy, 2], fov=85),
            top=dict(position=[cx + 0.01, cy, 1.6 * r], target=[cx, cy, 0], fov=45),
            east=dict(position=[x1 + 4, cy, 2.6], target=[cx, cy, 2], fov=85),
            west=dict(position=[x0 - 4, cy, 2.6], target=[cx, cy, 2], fov=85),
        )
    return {"Apartment": APT_CAMERAS, "Small": SMALL_CAMERAS}.get(_sess.room.house_size, CAMERAS)


mcp = FastMCP(
    "ffxiv-deco",
    instructions=(
        "DECO_SCOPE=exterior opens a separate Small/Medium/Large yard session with outdoor furniture and set_exterior for wall/roof/fence/door/window/decor; indoor fields are preserved. Default scope is interior. "
        "Decorate an FFXIV Medium house (2 floors, 450 items), Small (ground floor + basement stair, 300 items, door at 0,6) or Apartment (1 floor, 150 items, no stairs); chosen by the seed houseSize. Coordinates are metres: +x east/right, +y north (door at 0,8), +z up. yaw_deg is counter-clockwise: "
        "0 faces local +y north, 90 west, 180 south, 270 east. Default anchor is bottom_center (XY = footprint centre, Z = bottom). Only physics is enforced "
        "(unknown item, malformed input, current scope/house item cap). Position checks (outside the floor, inside stairs, wall item not on a wall) are ADVISORY WARNINGS only: FFXIV lets you bury partitions in stairs, float wall items, stack and overlap; pass strict=true to batch for the old hard rejection. A rejected batch changes nothing. "
        "Use list_interiors/set_interior to choose structure; inspect(level=ground|upper|basement where supported,include_geometry=true) supplies matching walls/floor/stairs. place_along_wall accepts level. "
        "Workflow: search_materials/set_fixtures (wall, floor, ceiling light) -> inspect -> search_furniture -> batch -> render -> look -> repeat; snapshot before big changes; export_json at the end."
    ),
)
_cat = None
_room = None
_sess = None
_render_cache = OrderedDict()
_RENDER_CACHE_LIMIT = 64


def _boot():
    global _cat, _room, _sess
    if _sess is not None:
        return _sess
    import os

    name = os.environ.get("DECO_SESSION", "default")
    seed_value = os.environ.get("DECO_SEED")
    if not seed_value:
        raise DecoError(
            "SETUP_REQUIRED",
            "Set DECO_SEED to your complete local layout JSON; no seed or game database is distributed. Run python -m ffxiv_furniture.doctor for setup checks.",
        )
    seed_path = Path(seed_value)
    try:
        layout = load_seed_layout(seed_path)
    except (OSError, ValueError, UnicodeError) as error:
        raise DecoError("BAD_SEED", f"Cannot read DECO_SEED: {error}") from error
    scope = os.environ.get("DECO_SCOPE", "interior")
    if scope not in ("interior", "exterior"):
        raise DecoError("BAD_INPUT", "DECO_SCOPE must be interior or exterior")
    if scope == "exterior":
        from .exterior import ExteriorCatalog, ExteriorRoom, ExteriorSession

        _cat = ExteriorCatalog(layout.get("houseSize", "Small"))
        _room = ExteriorRoom(
            layout.get("houseSize", "Small"), layout.get("exteriorFixture", []), db_path=_cat.path
        )
        _sess = ExteriorSession(
            name,
            _cat,
            _room,
            SESS_DIR,
            seed_layout={k: v for k, v in layout.items() if k != "exteriorFurniture"},
            from_layout=layout if os.environ.get("DECO_FROM_LAYOUT") == "1" else None,
            max_patch=(
                float(os.environ["DECO_MAX_PATCH"]) if os.environ.get("DECO_MAX_PATCH") else None
            ),
        )
        _room = _sess.room
        return _sess
    _cat = Catalog()
    if os.environ.get("DECO_STYLE"):
        for fx in layout["interiorFixture"]:
            if fx["type"] == "District":
                fx["name"] = os.environ["DECO_STYLE"]
    style = next(f["name"] for f in layout["interiorFixture"] if f["type"] == "District").replace(
        " ", ""
    )
    _room = Room(style, layout.get("houseSize", "Medium"))
    _sess = Session(
        name,
        _cat,
        _room,
        SESS_DIR,
        seed_layout={k: v for k, v in layout.items() if k != "interiorFurniture"},
        from_layout=layout if os.environ.get("DECO_FROM_LAYOUT") == "1" else None,
        max_patch=float(os.environ["DECO_MAX_PATCH"]) if os.environ.get("DECO_MAX_PATCH") else None,
    )
    _room = _sess.room  # persisted state (including switched style) wins over environment/seed
    return _sess


def _wrap(fn):
    try:
        return fn()
    except DecoError as e:
        raise ToolError(
            json.dumps(e.payload(_sess.revision if _sess else None), ensure_ascii=False)
        )


@mcp.tool()
def status() -> dict:
    """Session revision, item count vs the current scope/house cap, snapshots, undo/redo availability, and the named cameras."""
    return _wrap(lambda: dict(_boot().status(), session=_sess.name, cameras=sorted(_cameras())))


@mcp.tool()
def search_furniture(
    query: str = "",
    mode: str = "text",
    placement_types: list[str] | None = None,
    tags_all: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Search the session-scoped furniture catalog (interior or exterior). mode 'text' matches words in name/description (all words); 'semantic' is English-only embedding search.
    Results include size_m [x,y,z], placement_type (floor|wall|ceiling|rug), front_deg (local direction of the item's front, 90 = +y), support surfaces and tags.
    tags_all entries are 'category:name' or bare names."""

    def f():
        _boot()
        rows, more = _cat.search(query, mode, placement_types or [], tags_all or [], limit, offset)
        return dict(ok=True, results=rows, has_more=more)

    return _wrap(f)


@mcp.tool()
def search_materials(query: str = "", kind: str = "wall", limit: int = 20) -> dict:
    """Search fixtures: interior kinds wall/floor/light/window/door; exterior kinds wall/roof/fence/door/window/roof_decor/wall_decor/placard. Exterior wall/roof choices are house-size filtered. Matches name/description.
    renderable=false means textures are not extracted, so the render cannot show it (it can still be exported).
    """

    def f():
        _boot()
        return dict(ok=True, results=_cat.search_materials(query, kind, limit))

    return _wrap(f)


@mcp.tool()
def set_fixtures(
    wall: int | str | None = None,
    floor: int | str | None = None,
    light: int | str | None = None,
    level: str = "ground",
    window: int | str | None = None,
    door: int | str | None = None,
    expected_revision: int | None = None,
) -> dict:
    """window/door (Small): the native exterior window/door STYLE (positions are fixed; see inspect.openings), from search_materials(kind=window|door). Set the wallpaper / flooring / ceiling light of level='ground' (default) or 'upper' (second floor) by item_id or exact name (from search_materials). One undoable revision. Rendering shows wall and floor
    textures and the chandelier mesh; the ceiling light also becomes the main light source in lit renders.
    """
    ops = []
    for typ, v in (
        ("Wall", wall),
        ("Floor", floor),
        ("Light", light),
        ("Window", window),
        ("Door", door),
    ):
        if v is None:
            continue
        ops.append(
            dict(
                op="fixture",
                type=typ,
                level=level,
                **({"item_id": v} if isinstance(v, int) else {"name": v}),
            )
        )
    if not ops:
        raise ToolError(
            json.dumps(
                dict(
                    ok=False,
                    error=dict(code="BAD_INPUT", message="give at least one of wall/floor/light"),
                )
            )
        )
    r = _wrap(lambda: _boot().apply(ops, expected_revision, "fixtures"))
    r["fixtures"] = _sess.fixtures
    return r


@mcp.tool()
def set_exterior(
    wall: int | str | None = None,
    roof: int | str | None = None,
    fence: int | str | None = None,
    door: int | str | None = None,
    window: int | str | None = None,
    roof_decor: int | str | None = None,
    wall_decor: int | str | None = None,
    placard: int | str | None = None,
    expected_revision: int | None = None,
) -> dict:
    """Exterior sessions only (DECO_SCOPE=exterior). Select native house/fence/door/window/decor by search_materials ID or exact name. Native positions stay fixed. Wall/roof choices are house-size filtered. One undoable revision; indoor fields are preserved."""

    def f():
        s = _boot()
        if getattr(getattr(s, "cat", None), "scope", "interior") != "exterior":
            raise DecoError("BAD_INPUT", "set_exterior requires a separate exterior session")
        ops = []
        for typ, value in [
            ("ExteriorWall", wall),
            ("Roof", roof),
            ("Fence", fence),
            ("Door", door),
            ("Window", window),
            ("RoofDecor", roof_decor),
            ("WallDecor", wall_decor),
            ("Placard", placard),
        ]:
            if value is not None:
                ops.append(
                    dict(
                        op="fixture",
                        type=typ,
                        **({"item_id": value} if isinstance(value, int) else {"name": value}),
                    )
                )
        if not ops:
            raise DecoError("BAD_INPUT", "Give at least one exterior fixture")
        result = s.apply(ops, expected_revision, "exterior fixtures")
        result["fixtures"] = s.fixtures
        return result

    return _wrap(f)


@mcp.tool()
def search_dyes(query: str = "", limit: int = 40) -> dict:
    """List housing dyes (name, hex, shade, metallic). query = part of a name, or '#rrggbb' to get the nearest housing dye. Only these colours exist in the app."""

    def f():
        _boot()
        return dict(ok=True, dyes=_cat.search_dyes(query, limit))

    return _wrap(f)


@mcp.tool()
def dye(instance_id: str, color: str | None = None, expected_revision: int | None = None) -> dict:
    """Set the dye of one instance: dye name (see search_dyes) or '#rrggbb' (snapped to the nearest housing dye); color=null/'default' clears it. Only dyeable items accept a colour
    (`dyeable` in inspect). Dye tints the item's dyeable material slots (those with a Tint); fixed-colour parts (metal trim, glass...) do not change. In batch use {'op':'dye','instance_id':..,'color':..}; place also accepts color.
    """
    return _wrap(
        lambda: _boot().apply(
            [dict(op="dye", instance_id=instance_id, color=color)], expected_revision
        )
    )


@mcp.tool()
def inspect(
    region_min: list[float] | None = None,
    region_max: list[float] | None = None,
    instance_ids: list[str] | None = None,
    include_geometry: bool = False,
    level: str = "ground",
) -> dict:
    """List placed instances (optionally within a world XY region or by id) with world bounds, yaw, facing; plus walls (ids for place_along_wall),
    floor polygon, stair footprints and measured support surfaces. level='ground'|'upper' selects the wall/polygon geometry (instances remain queryable across floors). include_geometry=false omits geometry to save context.
    """

    def f():
        s = _boot()
        r = s.inspect(
            {"min": region_min, "max": region_max} if region_min and region_max else None,
            instance_ids or [],
            level,
        )
        if not include_geometry:
            r = {
                k: v
                for k, v in r.items()
                if k
                not in ("floor_polygon", "stair_footprints", "walls", "stair_clearance", "profile")
            }
        return r

    return _wrap(f)


@mcp.tool()
def list_interiors() -> dict:
    """List the seven Medium interior styles and explicit render/level capability. App equivalence is not claimed."""
    from ffxiv_furniture.interiors import list_interiors as choices, APT_STYLES

    s = _boot()
    if getattr(getattr(s, "cat", None), "scope", "interior") == "exterior":
        return dict(
            ok=True,
            interiors=[],
            scope="exterior",
            note="Use search_materials/set_exterior for exterior appearances.",
        )
    if s.room.house_size == "Apartment":
        return dict(
            ok=True,
            interiors=[
                dict(
                    style=x,
                    house_size="Apartment",
                    renderable=True,
                    levels=["ground"],
                    app_verified=False,
                )
                for x in APT_STYLES
            ],
        )
    if s.room.house_size == "Small":
        from ffxiv_furniture.interiors import SMALL_STYLES

        return dict(
            ok=True,
            interiors=[
                dict(
                    style=x,
                    house_size="Small",
                    renderable=True,
                    levels=["ground"],
                    app_verified=False,
                )
                for x in SMALL_STYLES
            ],
        )
    return dict(ok=True, interiors=choices())


@mcp.tool()
def set_interior(style: str, expected_revision: int | None = None) -> dict:
    """Switch Medium interior structure (District), preserving all furniture. One undoable revision; snapshots/restore cover style. Recomputes geometry diagnostics; never auto-moves/removes items."""
    return _wrap(
        lambda: _boot().apply([dict(op="interior", style=style)], expected_revision, "interior")
    )


def _one(op, expected_revision):
    return _wrap(lambda: _boot().apply([op], expected_revision))


@mcp.tool()
def place(
    item_id: int | None = None,
    name: str | None = None,
    position: list[float] = [0, 0, 0],
    yaw_deg: float = 0,
    anchor: str = "bottom_center",
    color: str | None = None,
    expected_revision: int | None = None,
) -> dict:
    """Create an instance. Give item_id or exact name. position = [x,y,z] metres (z = bottom of the item for bottom_center). Returns the new instance_id."""
    return _one(
        dict(
            op="place",
            item_id=item_id,
            name=name,
            position=position,
            yaw_deg=yaw_deg,
            anchor=anchor,
            **({"color": color} if color else {}),
        ),
        expected_revision,
    )


@mcp.tool()
def move(
    instance_id: str,
    position: list[float] | None = None,
    delta: list[float] | None = None,
    anchor: str = "bottom_center",
    expected_revision: int | None = None,
) -> dict:
    """Move an instance to an absolute position or by a [dx,dy,dz] delta (metres)."""
    return _one(
        {
            k: v
            for k, v in dict(
                op="move", instance_id=instance_id, position=position, delta=delta, anchor=anchor
            ).items()
            if v is not None
        },
        expected_revision,
    )


@mcp.tool()
def rotate(
    instance_id: str,
    yaw_deg: float | None = None,
    yaw_delta_deg: float | None = None,
    anchor: str = "bottom_center",
    expected_revision: int | None = None,
) -> dict:
    """Set absolute yaw or add a delta. With bottom_center the item turns about its own footprint centre."""
    return _one(
        {
            k: v
            for k, v in dict(
                op="rotate",
                instance_id=instance_id,
                yaw_deg=yaw_deg,
                yaw_delta_deg=yaw_delta_deg,
                anchor=anchor,
            ).items()
            if v is not None
        },
        expected_revision,
    )


@mcp.tool()
def remove(instance_id: str, expected_revision: int | None = None) -> dict:
    """Delete an instance."""
    return _one(dict(op="remove", instance_id=instance_id), expected_revision)


@mcp.tool()
def batch(
    operations: list[dict],
    expected_revision: int | None = None,
    label: str = "",
    strict: bool = False,
) -> dict:
    """Apply many operations atomically (all or nothing). Each op is a dict with 'op' in:
    place {item_id|name, position[3], yaw_deg, anchor?}; move {instance_id, position[3]|delta[3]}; rotate {instance_id, yaw_deg|yaw_delta_deg};
    remove {instance_id}; face {instance_id, target_id|direction_deg} (turn so the item's front points at a target / compass angle);
    place_on {instance_id|item_id|name, target_id, surface_idx?, offset_xy?[2], gap_m?, yaw_deg?} (set on a measured support surface; offset from surface centre in the target's local frame);
    place_along_wall {instance_id|item_id|name, wall_id, level? ground|upper, along_m, gap_m?, facing? 'inward'|'outward', height_m (relative to level for wall items) | z (absolute for floor items)}. interior {style}.
    A 'place'/'place_on'/'place_along_wall' op may carry a client-chosen instance_id (alphanumeric) together with item_id|name to CREATE that instance; later ops in the same batch can then reference it (e.g. place a table as 't1', then place_on target_id 't1'). Without a client id the server assigns i<N>.
    """
    return _wrap(lambda: _boot().apply(operations, expected_revision, label, strict))


@mcp.tool()
def snapshot(label: str = "") -> dict:
    """Save a named restore point of the current state."""
    return _wrap(lambda: _boot().snapshot(label))


@mcp.tool()
def restore(snapshot_id: str) -> dict:
    """Restore a snapshot (becomes a new revision; can be undone)."""
    return _wrap(lambda: _boot().restore(snapshot_id))


@mcp.tool()
def undo() -> dict:
    """Undo the last committed change."""
    return _wrap(lambda: _boot().undo())


@mcp.tool()
def redo() -> dict:
    """Redo an undone change."""
    return _wrap(lambda: _boot().redo())


def _renderer_version():
    # cached renders are keyed by the renderer code too, so tuning the lighting never serves stale images
    d = ROOT / "ffxiv_furniture/rendering"
    from ffxiv_furniture.interiors import BASE

    files = [
        d / n
        for n in (
            "pipeline.py",
            "raster.py",
            "raster_gpu.py",
            "house_materials.py",
            "assets.py",
            "native.py",
            "projection.py",
            "resources.py",
        )
    ]
    files.extend(
        ROOT / "ffxiv_furniture" / n
        for n in (
            "interiors.py",
            "geometry_mesh.py",
            "house_profiles.py",
            "deco/server.py",
            "deco/core.py",
            "deco/exterior.py",
            "exteriors.py",
            "rendering/exterior.py",
        )
    )
    files.extend(
        (source_path("houses", root=ROOT) / "Maps" / ("XIV" + s + "Exterior" + ext))
        for s in ("Small", "Medium", "Large")
        for ext in (".umap", ".uexp")
    )
    return (
        "|".join(f"{p.name}:{p.stat().st_mtime_ns}" for p in files)
        + f"|interior-assets:{BASE.stat().st_mtime_ns}"
    )


def _camera(view, session):
    if isinstance(view, str):
        cams = _cameras()
        if view not in cams:
            raise DecoError(
                "BAD_INPUT",
                f"unknown view {view!r}; use one of {sorted(cams)} or pass a camera dict {{position,target,fov}}",
            )
        c = dict(cams[view], name=view)
    elif isinstance(view, dict):
        if "position" not in view or "target" not in view:
            raise DecoError("BAD_INPUT", "camera needs position and target")
        c = dict(
            name="custom", fov=view.get("fov", 70), position=view["position"], target=view["target"]
        )
        for k in ("cutaway", "cut_stairs_z", "hide_above_z", "hide_below_z", "upper", "basement"):
            if k in view:
                c[k] = view[k]
    else:
        raise DecoError("BAD_INPUT", "view must be a name or a camera dict")
    if c.get("cutaway") and not c.get("upper") and "hide_above_z" not in c:
        c["hide_above_z"] = -0.6 if c.get("basement") else 6.4
    if not 1 < float(c["fov"]) < 175:
        raise DecoError("BAD_INPUT", "fov must be between 1 and 175")
    return c


@mcp.tool()
def render(
    view: str | dict = "overview",
    width: int = 960,
    height: int = 640,
    labels: bool = False,
    crop: list[int] | None = None,
    lighting: str = "dusk",
    mirror: bool = True,
    dye: str = "mi",
    diagnostics: bool = False,
) -> list:
    """Render the CURRENT revision from a named view (see status.cameras) or a custom camera {position:[x,y,z], target:[x,y,z], fov, cutaway?}.
    Saves PNGs in one renders/ directory, named by revision/view/settings hash; no per-render folders or JSON files by default.
    Returns the PNG (inline) plus metadata in the tool response. diagnostics=true explicitly saves named diagnostic JSONs in that same directory.
    Metadata cache is bounded and in memory; a server restart regenerates images/metadata when needed. labels=true overlays render-index numbers
    (use the returned `visible` list to map numbers to instance ids). crop=[x,y,w,h] in pixels of the full image. lighting: 'dusk' (default, warm lamps on dim ambient), 'night', 'day', or 'off' (the old flat shading). mirror=true (default) flips the picture horizontally so left/right match the ReMakePlace app (user-verified: the app shows +x on the RIGHT when looking south; world coordinates and ids are unchanged; pass false for the raw projection). dye='mi' (default) uses each material's own Tint/FixedTint = the item's real default look; 'default' = the DB default dye (known wrong for many items); 'none' = raw textures. Foliage/opacity-mask materials are alpha-cut. Lit renders use point lights from lamps/lanterns/fires and the ceiling fixture; NO shadows. ~5-10 s per call.
    """
    from PIL import Image as PILImage

    def f():
        s = _boot()
        if not (64 <= width <= 2048 and 64 <= height <= 2048):
            raise DecoError("BAD_INPUT", "width/height must be 64..2048")
        cam = _camera(view, s)
        t0 = time.time()
        if crop:
            if len(crop) != 4:
                raise DecoError("BAD_INPUT", "crop needs [x,y,w,h]")
            x, y, w, h = crop
            if not (0 <= x and 0 <= y and w > 0 and h > 0 and x + w <= width and y + h <= height):
                raise DecoError("BAD_INPUT", "crop outside the image")
        scene_scope = getattr(getattr(s, "cat", None), "scope", "interior")
        lay = s.layout_dict()
        raw = (
            json.dumps(lay, sort_keys=True)
            + json.dumps(cam, sort_keys=True)
            + f"{scene_scope}-{width}x{height}{lighting}-labels={labels}-m{mirror}-d{dye}-diagnostics={diagnostics}"
            + _renderer_version()
        )
        key = hashlib.sha256(raw.encode()).hexdigest()[:12]
        out = s.dir / "renders"
        prefix = (
            f"r{s.revision}-"
            + ("yard-" if scene_scope == "exterior" else "")
            + f'{cam["name"]}-{key}'
        )
        cache_key = (str(s.dir.resolve()), key)
        m = _render_cache.get(cache_key)
        cache_hit = (
            m is not None
            and Path(m["views"][0]["image"]).is_file()
            and all(Path(p).is_file() for p in m.get("artifacts", {}).values())
        )
        need_upper = bool(cam.get("upper")) or any(
            i["pivot"][2] + s.cat.item(i["item_id"])["lo"][2] >= 6.4 for i in s.instances.values()
        )
        if not cache_hit:
            from ffxiv_furniture.rendering.pipeline import run_pipeline

            need_bs = bool(cam.get("basement")) or any(
                i["pivot"][2] + s.cat.item(i["item_id"])["lo"][2] <= -3
                for i in s.instances.values()
            )
            m = run_pipeline(
                lay,
                out,
                basement_context=need_bs and s.room.house_size == "Small",
                room_context=True,
                rough_room_finish=True,
                size=(width, height),
                cameras=[cam],
                mirror_view=bool(mirror),
                dye_mode=dye,
                lighting=None if lighting == "off" else lighting,
                upper_context=need_upper,
                labels=labels,
                artifacts=diagnostics,
                image_prefix=prefix,
                overwrite=True,
                scope=scene_scope,
                db_path=getattr(getattr(s, "cat", None), "path", None),
            )
            _render_cache[cache_key] = m
        _render_cache.move_to_end(cache_key)
        while len(_render_cache) > _RENDER_CACHE_LIMIT:
            _render_cache.popitem(last=False)
        assert m is not None
        v = m["views"][0]
        img = Path(v["image"])
        if crop:
            x, y, w, h = crop
            cp = out / f'{prefix}-crop-{x}-{y}-{w}-{h}{"-labeled" if labels else ""}.png'
            with PILImage.open(img) as full_image:
                full_image.crop((x, y, x + w, y + h)).save(cp)
            img = cp
        ids = list(s.instances)
        vis = [
            dict(
                index=int(k),
                instance_id=ids[int(k) - 1],
                name=s.instances[ids[int(k) - 1]]["name"],
                pixels=n,
            )
            for k, n in v["visible_object_pixels"].items()
            if int(k) <= len(ids)
        ]
        meta = dict(
            ok=True,
            scope=scene_scope,
            revision=s.revision,
            style=s.room.style,
            profile=m.get("exterior_profile") or m.get("interior_profile"),
            image=str(img),
            width=width,
            height=height,
            camera=cam,
            cache_hit=cache_hit,
            elapsed_s=round(time.time() - t0, 1),
            visible=sorted(vis, key=lambda d: -d["pixels"])[:60],
            outside_floor=[
                ids[int(x.split("-")[1]) - 1]
                for x in m["outside_floor_projection"]
                if x.startswith("furniture-")
            ],
            stair_keepout_hits=[
                ids[int(x.split("-")[1]) - 1]
                for x in m["stair_keepout_hits"]
                if x.startswith("furniture-")
            ],
            notes="native style meshes and shared stair transforms; enclosure placement/lighting approximate, alpha cutout only, no translucency/shadows; geometry warnings are advisory, app-equivalence unverified",
        )
        if diagnostics:
            meta["artifacts"] = m["artifacts"]
        return [Image(path=str(img)), json.dumps(meta, ensure_ascii=False)]

    return _wrap(f)


@mcp.tool()
def analyze_layout(
    level: str = "ground",
    start: list[float] | None = None,
    path_width_m: float = 0.8,
    front_depth_m: float = 0.6,
) -> dict:
    """Read-only diagnostics of the CURRENT layout (facts, no pass/fail, never blocks edits): (1) reachability: area walkable at path_width_m from `start` (default the door),
    unreachable pockets and items with no access; (2) front clearance of seats/tall storage (fraction of a front_depth_m rectangle blocked by other items or the wall);
    (3) seat -> nearest-table facing error in degrees; (4) tall items floating 0.3-1.2 m off a wall or off the 0/90 deg axes; (5) covered floor fraction per west/centre/east third.
    Overlap and tight spots are legal in FFXIV: treat numbers as hints, then LOOK at a render. Not covered: line of sight / focal point, style and colour (visual judgement).
    """
    from .analyze import analyze

    return _wrap(
        lambda: analyze(
            _boot(), level, tuple(start) if start else None, path_width_m, front_depth_m
        )
    )


@mcp.tool()
def export_json(name: str = "layout") -> dict:
    """Write the final ReMakePlace layout.json (UTF-16LE BOM, fixtures/metadata preserved from the seed) plus an instance-id map. Never overwrites app saves."""
    return _wrap(lambda: _boot().export(name))


if __name__ == "__main__":
    print(
        "ffxiv-deco MCP server starting (preloading numpy/shapely/renderer on the main thread)",
        file=sys.stderr,
    )
    # Heavy native imports must happen on the main thread BEFORE the stdio loop: importing numpy lazily from a tool worker thread hung for minutes.
    import numpy, shapely, PIL.Image  # noqa: F401
    from ffxiv_furniture.rendering import pipeline  # noqa: F401

    _boot()
    print("ffxiv-deco ready", file=sys.stderr)
    mcp.run(transport="stdio")
