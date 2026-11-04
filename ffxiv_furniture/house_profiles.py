"""Dependency-free measured room profiles shared by rendering and design."""

# Measured Shirogane structure meshes (native resource suffixes). Actor transforms are NOT calibrated: identity is assumed.
# 'footprint' is only used when no floor mesh exists (Apartment) and is the measured SimpleFrame/Frame XY bounds.
HOUSE_PROFILES = {
    "Medium": {
        "floor": "Shirogane/Medium/GroundFloor.uexp",
        "room-frame": "Shirogane/Medium/GroundFloorFrame.uexp",
        "ceiling": "SizeCommon/Medium/Ceiling.uexp",
        "walls": "SizeCommon/Medium/Wall.uexp",
        "pillars": "Shirogane/Medium/GroundFloorPillars.uexp",
        "corridor": (-1.2, -8, 1.2, 8),
        "main-door": {
            "mesh": "MainDoor/HinganDoor0x28Mokuzo0x29/HinganDoor0x28Mokuzo0x29.uexp",
            "translation_m": [0.0, 7.25, 0.0],
            "yaw_degrees": 0.0,
            "evidence": "map imports MainDoor/HinganDoor0x28Mokuzo0x29 (verified reference); standing on the floor at the documented north-wall centre (0,8) convention",
        },
    },
    "Small": {
        "floor": "Shirogane/Small/GroundFloor.uexp",
        "room-frame": "Shirogane/Small/GroundFloorFrame.uexp",
        "ceiling": "SizeCommon/Small/GroundFloorCeiling.uexp",
        "walls": "SizeCommon/Small/GroundFloorWall.uexp",
        "pillars": "Shirogane/Small/GroundFloorPillars.uexp",
        "main-door": {
            "mesh": "MainDoor/RivieraWoodenDoor/RivieraWoodenDoor.uexp",
            "translation_m": [0.0, 5.68, 0.0],
            "yaw_degrees": 0.0,
            "evidence": "map names a RivieraDoor fixture; this is the only Riviera main door with a decodable native mesh; the north wall plane is measured at y=+6 (wall mesh flat triangles) and the door sits flush on it; placement along x is the centre convention, unverified for this size",
        },
    },
    "Large": {
        "floor": "SizeCommon/Large/GroundFloor/GroundFloorFloor.uexp",
        "room-frame": "Shirogane/Large/GroundFloor/GroundFloorFrame.uexp",
        "ceiling": "SizeCommon/Large/GroundFloor/GroundFloorCeiling.uexp",
        "walls": "SizeCommon/Large/GroundFloor/GroundFloorWall.uexp",
        "pillars": "Shirogane/Large/GroundFloor/GroundFloorPillars.uexp",
        "main-door": {
            "mesh": "MainDoor/RivieraWoodenDoor/RivieraWoodenDoor.uexp",
            "translation_m": [0.0, 11.68, 0.0],
            "yaw_degrees": 0.0,
            "evidence": "map names RivieraDoor2/3 fixtures; only Riviera main door with a decodable native mesh; placement at the north wall (y=12) is a convention, unverified for this size",
        },
    },
    "Apartment": {
        "footprint": "SizeCommon/Apartment/SimpleFrame.uexp",
        "room-frame": "Shirogane/Apt/GroundFloorFrame.uexp",
        "ceiling": "SizeCommon/Apartment/Ceiling.uexp",
        "walls": "SizeCommon/Apartment/Wall.uexp",
        "pillars": "Shirogane/Apt/Pillars.uexp",
        "main-door": {
            "mesh": "MainDoor/HinganDoor0x28Mokuzo0x29/HinganDoor0x28Mokuzo0x29.uexp",
            "translation_m": [0.0, 7.25, 0.0],
            "yaw_degrees": 0.0,
            "evidence": "map bakes a Mist/ChamberDoor (plain wood), but the user app screenshots show this Mokuzo-styled door (timber frame, gold ornaments, cloud grilles) -- app ground truth wins; (0,8) north-wall centre placement per README convention, not actor-verified",
        },
    },
}
DEFAULT_CATALOG_CANDIDATES = ("data/furniture.sqlite3", "data/furniture-test.sqlite3")


def room_bounds(root, house_size):
    """Measured floor XY bounds in metres directly from supplied native meshes (identity actor transform assumed)."""
    import json
    from pathlib import Path

    profile = HOUSE_PROFILES[house_size]
    key = profile.get("floor") or profile["footprint"]
    found = structure_record(root, key)
    return {
        "min": found["local_min_m"][:2],
        "max": found["local_max_m"][:2],
        "ceiling_z": 6.5,
        "corridor": profile.get("corridor"),
        "source": key,
    }


def room_polygon(root, house_size):
    """Real ground-floor walkable outline (union of the floor mesh's horizontal triangles) as a shapely geometry.

    Medium is L-shaped (x -12..-4, y 2..8 is NOT floor), so the bounding rectangle must never be used for placement.
    Apartment has no floor mesh; its SimpleFrame XY rectangle is used instead (flagged by the caller).
    """
    import json
    from pathlib import Path
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    from .geometry_mesh import read_static_mesh_triangles

    profile = HOUSE_PROFILES[house_size]
    key = profile.get("floor") or profile["footprint"]
    rec = structure_record(root, key)
    if "floor" not in profile:
        return box(
            rec["local_min_m"][0],
            rec["local_min_m"][1],
            rec["local_max_m"][0],
            rec["local_max_m"][1],
        )
    v, t = read_static_mesh_triangles(rec)
    return (
        unary_union(
            [p for tri in t if (p := Polygon([(v[i][0], v[i][1]) for i in tri])).area > 1e-8]
        )
        .buffer(0.002)
        .buffer(-0.002)
    )


def room_keepouts(root, house_size, floor="ground", with_clearance=False):
    """Decoded stair keepouts as shapely polygons: the stair hull itself, or (with_clearance) hull + 1 m approach clearance. Only Medium is verified; others return []."""
    import json
    from pathlib import Path
    from shapely.geometry import Polygon

    if house_size != "Medium":
        return []
    p = Path(root) / "outputs/house-layouts/medium-stair-transforms.json"
    if not p.exists():
        return []
    ks = json.loads(p.read_text(encoding="utf-8"))["keepouts"][floor]
    polys = [Polygon(ring) for ring in ks["polygons"]]
    return polys if with_clearance else [g.buffer(-ks["clearance_m"], join_style=2) for g in polys]


def stair_actors(root, house_size="Medium"):
    """Decoded stair actors (translation m, yaw deg, scale) for rendering; empty when not verified."""
    import json
    from pathlib import Path

    p = Path(root) / "outputs/house-layouts/medium-stair-transforms.json"
    if house_size != "Medium" or not p.exists():
        return {}
    return {
        k: v
        for k, v in json.loads(p.read_text(encoding="utf-8"))["actors"].items()
        if k.startswith("Stairs")
    }


def structure_record(root, suffix):
    """Read a current native structure directly, without private inventory JSON."""
    from pathlib import Path
    from .config import source_path
    from .geometry import read_static_mesh_bounds

    path = source_path("interiors", root=root) / "HouseAssets/InteriorStyles" / suffix
    return _structure_record(
        str(path.resolve()), path.stat().st_mtime_ns, path.with_suffix(".uasset").stat().st_mtime_ns
    )


from functools import lru_cache


@lru_cache(maxsize=256)
def _structure_record(path, mesh_version, header_version):
    from pathlib import Path
    from .geometry import read_static_mesh_bounds

    return read_static_mesh_bounds(Path(path))
