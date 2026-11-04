"""Build a new local runtime catalog from explicit native assets and game CSVs.

No private runs, model inference, downloads or existing database are inputs.
"""

from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata
from typing import Any

from .config import load_sources
from .database import FurnitureDB

SCHEMA = """
CREATE TABLE candidate_assets(
 asset_key TEXT PRIMARY KEY,item_id INTEGER REFERENCES furniture(id),name TEXT NOT NULL,
 source_category TEXT NOT NULL,scope TEXT NOT NULL,image_path TEXT,visual_description TEXT,
 item_id_evidence TEXT NOT NULL,metadata_status TEXT NOT NULL,length REAL,width REAL,height REAL);
CREATE TABLE asset_geometry(
 asset_key TEXT PRIMARY KEY REFERENCES candidate_assets(asset_key),item_id INTEGER UNIQUE REFERENCES furniture(id),
 min_x REAL,min_y REAL,min_z REAL,max_x REAL,max_y REAL,max_z REAL,
 center_x REAL,center_y REAL,center_z REAL,source TEXT,source_sha256 TEXT,method TEXT,evidence TEXT);
CREATE VIEW furniture_bounds AS SELECT f.*,g.min_x,g.min_y,g.min_z,g.max_x,g.max_y,g.max_z,
 g.center_x,g.center_y,g.center_z,f.length*f.width*f.height AS bounding_box_volume_m3
 FROM furniture f JOIN asset_geometry g ON g.item_id=f.id;
CREATE TABLE house_materials(
 asset_key TEXT PRIMARY KEY,item_id INTEGER UNIQUE,category TEXT NOT NULL,slot TEXT NOT NULL,scope TEXT,
 name TEXT NOT NULL,name_source TEXT NOT NULL,image_path TEXT,visual_description TEXT,
 patch TEXT,dyeable INTEGER,dye_channels INTEGER,marketable INTEGER,item_id_evidence TEXT,proposed_tags TEXT);
CREATE TABLE house_material_tags(
 asset_key TEXT REFERENCES house_materials(asset_key),tag_id INTEGER REFERENCES tags(id),
 confidence REAL,evidence TEXT,source TEXT,PRIMARY KEY(asset_key,tag_id));
CREATE TABLE placement_info(
 item_id INTEGER PRIMARY KEY REFERENCES furniture(id),placement_type TEXT,small INTEGER,
 front_deg REAL,front_source TEXT,front_confidence REAL,supports_top INTEGER,top_z_local REAL,
 top_area_fraction REAL,mount_bottom_z REAL);
CREATE TABLE support_surfaces(
 item_id INTEGER REFERENCES furniture(id),surface_idx INTEGER,z_local REAL,min_x REAL,min_y REAL,
 max_x REAL,max_y REAL,area_m2 REAL,clearance_above_m REAL,is_top INTEGER,PRIMARY KEY(item_id,surface_idx));
CREATE TABLE item_default_dye(item_id INTEGER PRIMARY KEY REFERENCES furniture(id),dye_name TEXT,source TEXT);
CREATE TABLE item_colors(item_id INTEGER PRIMARY KEY REFERENCES furniture(id),c1_hex TEXT,c1_frac REAL,
 c2_hex TEXT,c2_frac REAL,c3_hex TEXT,c3_frac REAL,hue_name TEXT,mean_h REAL,mean_s REAL,mean_v REAL);
CREATE TABLE build_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE bootstrap_issues(asset_key TEXT,stage TEXT,detail TEXT NOT NULL);
"""
MATERIAL_CATEGORIES = {
    "Wallpaper": "Interior Wall",
    "Flooring": "Flooring",
    "CeilingLight": "Ceiling Light",
    "ExteriorWall": "Exterior Wall",
    "Roof": "Roof",
    "Fence": "Fence",
    "MainDoor": "Door",
    "Window": "Window",
    "RoofDecor": "Roof Decoration",
    "ExteriorWallDecor": "Exterior Wall Decoration",
    "Placard": "Placard",
}
INTERIOR_MATERIALS = {"Wallpaper", "Flooring", "CeilingLight"}
FURNITURE_UI = {
    "Tabletop",
    "Furnishing",
    "Outdoor Furnishing",
    "Wall-mounted",
    "Table",
    "Rug",
    "Miscellany",
}
SURFACE_COLUMNS = (
    "z_local",
    "min_x",
    "min_y",
    "max_x",
    "max_y",
    "area_m2",
    "clearance_above_m",
    "is_top",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compact(value):
    value = re.sub(r"0x([0-9A-Fa-f])[ ]?([0-9A-Fa-f])", lambda m: chr(int(m[1] + m[2], 16)), value)
    return re.sub("[^a-z0-9]", "", unicodedata.normalize("NFKD", value).lower())


def csv_rows(path, required):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(required) <= set(reader.fieldnames or []):
            raise ValueError(f"{path}: expected CSV columns {sorted(required)}")
        rows = list(reader)
        columns = list(reader.fieldnames or [])
        if len(columns) != len(set(columns)) or any(
            None in row or any(row.get(k) is None for k in required) for row in rows
        ):
            raise ValueError(f"{path}: malformed CSV rows or duplicate columns")
        return rows


def read_items(sources):
    categories = {r["#"]: r["Name"] for r in csv_rows(sources["ui_categories_csv"], {"#", "Name"})}
    rows = csv_rows(
        sources["items_csv"],
        {"#", "Name", "ItemUICategory", "DyeCount", "IsUntradable", "ItemSearchCategory"},
    )
    by_name = defaultdict(list)
    seen = set()
    for row in rows:
        if not re.fullmatch("[0-9]+", row["#"] or "") or not row["Name"]:
            continue
        iid = int(row["#"])
        if iid <= 0:
            continue
        if iid in seen:
            raise ValueError(f"Duplicate Item RowId: {iid}")
        seen.add(iid)
        channels = row["DyeCount"]
        if channels and not re.fullmatch("[0-9]+", channels):
            raise ValueError(f"Invalid DyeCount for Item {iid}")
        trade = row["IsUntradable"].lower()
        search = row["ItemSearchCategory"]
        marketable = (
            int(int(search) > 0 and trade == "false")
            if trade in ("true", "false") and re.fullmatch("[0-9]+", search or "")
            else None
        )
        row = dict(
            row,
            item_id=iid,
            ui_name=categories.get(row["ItemUICategory"]),
            channels=int(channels) if channels else None,
            marketable=marketable,
        )
        by_name[compact(row["Name"])].append(row)
    return by_name


def inventory(sources):
    found = {}
    for content_value in sources["furniture_roots"]:
        content = Path(content_value)
        for path in sorted(content.rglob("*.uasset")):
            parts = path.relative_to(content).parts
            if (
                parts[0] not in ("GameAssets", "YardAssets")
                or "Material" in parts
                or compact(path.stem) != compact(path.parent.name)
            ):
                continue
            key = "MakePlace/Content/" + path.parent.relative_to(content).as_posix()
            if not path.with_suffix(".uexp").is_file():
                continue
            value = dict(
                asset_key=key,
                scope="interior" if parts[0] == "GameAssets" else "exterior",
                source_category="/".join(parts[1:-2]) or "Uncategorized",
                resource_name=path.parent.name,
                mesh=str(path.with_suffix(".uexp")),
            )
            if key in found:
                if digest(found[key]["mesh"]) != digest(value["mesh"]) or digest(
                    Path(found[key]["mesh"]).with_suffix(".uasset")
                ) != digest(path):
                    raise ValueError("Conflicting source builds for asset: " + key)
            else:
                found[key] = value
    if not found:
        raise ValueError("No primary native GameAssets/YardAssets packages found")
    return [found[key] for key in sorted(found)]


def measure_asset(job):
    from .geometry import read_static_mesh_bounds
    from .geometry_mesh import read_static_mesh_triangles
    from .placement import measure
    from .design.surfaces import measure_support_surfaces

    asset, item = job
    result: dict[str, Any] = dict(
        asset_key=asset["asset_key"], geometry=None, placement=None, surfaces=[], issues=[]
    )
    try:
        record = read_static_mesh_bounds(Path(asset["mesh"]))
        record["item_id"] = item["item_id"]
        record["asset_key"] = asset["asset_key"]
        record["uasset_sha256"] = digest(Path(asset["mesh"]).with_suffix(".uasset"))
        vertices, faces = read_static_mesh_triangles(record)
        result["geometry"] = record
        row = (
            item["item_id"],
            item["Name"],
            asset["source_category"],
            json.dumps(record),
            record["length_m"],
            record["width_m"],
            record["height_m"],
            record["local_min_m"][2],
        )
        result["placement"] = measure(row, vertices=vertices)
        try:
            result["surfaces"] = measure_support_surfaces(vertices, faces)
        except Exception as error:
            result["issues"].append(("support_surfaces", f"{type(error).__name__}: {error}"))
    except Exception as error:
        result["issues"].append(("geometry_or_placement", f"{type(error).__name__}: {error}"))
        result["geometry"] = None
    return result


def _patches(sources):
    result = {}
    if "patches_csv" in sources:
        for row in csv_rows(sources["patches_csv"], {"item_id", "patch"}):
            if not re.fullmatch("[1-9][0-9]*", row["item_id"]) or not re.fullmatch(
                r"[0-9]+\.[0-9]+", row["patch"]
            ):
                raise ValueError("Invalid literal item_id/patch in patches_csv")
            iid = int(row["item_id"])
            if iid in result:
                raise ValueError("Duplicate item_id in patches_csv")
            result[iid] = row["patch"]
    return result


def _materials(connection, sources, by_name, patches, issues):
    base = Path(sources["materials"]) / "HouseAssets"
    used_ids = set()
    for category, ui_name in MATERIAL_CATEGORIES.items():
        for folder in sorted((base / category).glob("*")):
            if not folder.is_dir() or not any(folder.glob("*.uasset")):
                continue
            key = "MakePlace/Content/HouseAssets/" + category + "/" + folder.name
            candidates = by_name.get(compact(folder.name), [])
            valid = (
                candidates if len(candidates) == 1 and candidates[0]["ui_name"] == ui_name else []
            )
            item = valid[0] if valid else None
            if item and item["item_id"] in used_ids:
                raise ValueError(
                    "Multiple material assets map to one Item ID: " + str(item["item_id"])
                )
            if item:
                used_ids.add(item["item_id"])
            name = item["Name"] if item else re.sub(r"(?<=[a-z])(?=[A-Z])", " ", folder.name)
            if not item:
                issues.append(
                    (
                        key,
                        "material_identity",
                        "No unique matching game UI-category identity; name is folder-derived, ID remains NULL",
                    )
                )
            slot = {"Wallpaper": "wall", "Flooring": "floor", "CeilingLight": "ceiling_light"}.get(
                category, "exterior_" + category.lower()
            )
            channels = item["channels"] if item else None
            connection.execute(
                "INSERT INTO house_materials(asset_key,item_id,category,slot,scope,name,name_source,image_path,visual_description,patch,dyeable,dye_channels,marketable,item_id_evidence) VALUES("
                + ",".join(["?"] * 14)
                + ")",
                (
                    key,
                    item["item_id"] if item else None,
                    category,
                    slot,
                    "interior" if category in INTERIOR_MATERIALS else "exterior",
                    name,
                    "Item.csv Name" if item else "derived from native folder; no verified Item ID",
                    None,
                    None,
                    patches.get(item["item_id"]) if item else None,
                    int(channels > 0) if channels is not None else None,
                    channels,
                    item["marketable"] if item else None,
                    json.dumps(
                        dict(method="unique normalized name plus UI category", source=str(folder))
                    ),
                ),
            )


def build_catalog(
    sources, output, *, workers=1, strict_geometry=False, measure=measure_asset, progress=None
):
    """Publish only a complete staged SQLite file; never replace an existing target."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Refusing to replace an existing catalog: " + str(output))
    if workers < 1:
        raise ValueError("workers must be positive")
    for key, value in sources.items():
        for path in value if isinstance(value, list) else [value]:
            expected_dir = key in ("furniture_roots", "interiors", "houses", "materials")
            if not (Path(path).is_dir() if expected_dir else Path(path).is_file()):
                raise ValueError("Missing local source " + key + ": " + path)
    input_hashes = {
        k: digest(v) for k, v in sources.items() if not isinstance(v, list) and Path(v).is_file()
    }
    for key, suffix in {
        "interiors": "HouseAssets/InteriorStyles",
        "houses": "Maps",
        "materials": "HouseAssets",
    }.items():
        if not (Path(sources[key]) / suffix).is_dir():
            raise ValueError(
                "Source must point to Content containing " + suffix + ": " + sources[key]
            )
    by_name = read_items(sources)
    csv_rows(sources["stains_csv"], {"Name", "Color", "Shade", "IsHousingApplicable", "IsMetallic"})
    item_csv_hash = input_hashes["items_csv"]
    patches = _patches(sources)
    assets = inventory(sources)
    issues = []
    mapped = {}
    for asset in assets:
        candidates = by_name.get(compact(asset["resource_name"]), [])
        if len(candidates) == 1 and candidates[0]["ui_name"] in FURNITURE_UI:
            mapped[asset["asset_key"]] = candidates[0]
        else:
            issues.append(
                (
                    asset["asset_key"],
                    "identity",
                    "missing/ambiguous or non-furniture UI category; ID remains NULL",
                )
            )
    counts = Counter(row["item_id"] for row in mapped.values())
    for key, row in list(mapped.items()):
        if counts[row["item_id"]] != 1:
            issues.append(
                (
                    key,
                    "identity",
                    "multiple native assets map to one Item ID; all conflicting mappings excluded",
                )
            )
            del mapped[key]
    if not mapped:
        raise ValueError(
            "No uniquely identified housing items; use matching English CSVs and native assets"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, stage_name = tempfile.mkstemp(
        prefix="." + output.stem + "-", suffix=".sqlite3", dir=output.parent
    )
    os.close(handle)
    stage = Path(stage_name)
    try:
        with FurnitureDB(stage) as database:
            c = database.connection
            c.executescript(SCHEMA)
            with c:
                for asset in assets:
                    item = mapped.get(asset["asset_key"])
                    iid = item["item_id"] if item else None
                    channels = item["channels"] if item else None
                    if item:
                        c.execute(
                            "INSERT INTO furniture(id,name,description,scope,patch,marketable,dyeable,dye_channels) VALUES(?,?,?,?,?,?,?,?)",
                            (
                                iid,
                                item["Name"],
                                item.get("Description") or "",
                                asset["scope"],
                                patches.get(iid),
                                item["marketable"],
                                int(channels > 0) if channels is not None else None,
                                channels,
                            ),
                        )
                    c.execute(
                        "INSERT INTO candidate_assets VALUES(" + ",".join(["?"] * 12) + ")",
                        (
                            asset["asset_key"],
                            iid,
                            item["Name"] if item else asset["resource_name"],
                            asset["source_category"],
                            asset["scope"],
                            None,
                            None,
                            json.dumps(
                                dict(
                                    method="unique normalized native-folder name + housing UI category",
                                    item_csv_sha256=item_csv_hash,
                                    source=asset["mesh"],
                                    candidates=[
                                        dict(
                                            item_id=x["item_id"],
                                            name=x["Name"],
                                            ui_category=x["ui_name"],
                                        )
                                        for x in by_name.get(compact(asset["resource_name"]), [])
                                    ],
                                )
                            ),
                            "identified; geometry pending" if item else "unresolved identity",
                            None,
                            None,
                            None,
                        ),
                    )
                    if item:
                        for category, name in [
                            ("function", asset["source_category"]),
                            ("scope", asset["scope"]),
                        ]:
                            c.execute(
                                "INSERT OR IGNORE INTO tags(category,name) VALUES(?,?)",
                                (category, name),
                            )
                            tag = c.execute(
                                "SELECT id FROM tags WHERE category=? AND name=?", (category, name)
                            ).fetchone()[0]
                            c.execute(
                                "INSERT INTO furniture_tags VALUES(?,?,?,NULL)",
                                (iid, tag, "native-asset-path"),
                            )
                _materials(c, sources, by_name, patches, issues)
            jobs = [(a, mapped[a["asset_key"]]) for a in assets if a["asset_key"] in mapped]
            pool = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
            try:
                results = pool.map(measure, jobs) if pool else map(measure, jobs)
                for index, result in enumerate(results, 1):
                    key = result["asset_key"]
                    issues.extend(
                        (key, stage_name, detail) for stage_name, detail in result["issues"]
                    )
                    rec = result["geometry"]
                    if rec is not None:
                        iid = mapped[key]["item_id"]
                        c.execute(
                            "INSERT INTO asset_geometry VALUES(" + ",".join(["?"] * 15) + ")",
                            (
                                key,
                                iid,
                                *rec["local_min_m"],
                                *rec["local_max_m"],
                                *[x / 100 for x in rec["origin_cm"]],
                                rec["source"],
                                rec["source_sha256"],
                                rec["method"],
                                json.dumps(rec, sort_keys=True),
                            ),
                        )
                        dims = (rec["length_m"], rec["width_m"], rec["height_m"])
                        c.execute(
                            "UPDATE furniture SET length=?,width=?,height=? WHERE id=?",
                            (*dims, iid),
                        )
                        c.execute(
                            "UPDATE candidate_assets SET length=?,width=?,height=?,metadata_status=? WHERE asset_key=?",
                            (*dims, "native geometry measured; placement front may be prior", key),
                        )
                        c.execute(
                            "INSERT INTO placement_info VALUES(" + ",".join(["?"] * 10) + ")",
                            result["placement"],
                        )
                        for idx, surface in enumerate(result["surfaces"]):
                            c.execute(
                                "INSERT INTO support_surfaces VALUES(" + ",".join(["?"] * 10) + ")",
                                (iid, idx, *[surface[k] for k in SURFACE_COLUMNS]),
                            )
                    if progress and (index % 50 == 0 or index == len(jobs)):
                        progress(index, len(jobs))
                c.commit()
            finally:
                if pool:
                    pool.shutdown(wait=True, cancel_futures=True)
            if strict_geometry and any(
                stage in ("geometry_or_placement", "support_surfaces") for _, stage, _ in issues
            ):
                raise ValueError(
                    "strict-geometry: unsupported native geometry/support measurements; no catalog published"
                )
            for mesh, expected, evidence in c.execute(
                "SELECT source,source_sha256,evidence FROM asset_geometry"
            ):
                header_hash = json.loads(evidence).get("uasset_sha256")
                if digest(mesh) != expected or (
                    header_hash and digest(Path(mesh).with_suffix(".uasset")) != header_hash
                ):
                    raise ValueError("Native source changed during build; no catalog published")
            if any(digest(sources[k]) != value for k, value in input_hashes.items()):
                raise ValueError("Source CSV changed during build; no catalog published")
            geometry_count = c.execute("SELECT COUNT(*) FROM asset_geometry").fetchone()[0]
            if not geometry_count:
                raise ValueError("No measured geometry; refusing an unusable runtime catalog")
            report = dict(
                candidates=len(assets),
                identified_items=len(mapped),
                measured_items=geometry_count,
                materials=c.execute("SELECT COUNT(*) FROM house_materials").fetchone()[0],
                support_surfaces=c.execute("SELECT COUNT(*) FROM support_surfaces").fetchone()[0],
                patch_known=len([v for v in mapped.values() if v["item_id"] in patches]),
                issues=dict(Counter(stage for _, stage, _ in issues)),
                inference=False,
                visual_tags_included=False,
                output=str(output),
            )
            with c:
                c.executemany("INSERT INTO bootstrap_issues VALUES(?,?,?)", issues)
                metadata = dict(
                    bootstrap_version="1",
                    bootstrap_sources=json.dumps(sources, sort_keys=True),
                    bootstrap_summary=json.dumps(report, sort_keys=True),
                    bootstrap_source_hashes=json.dumps(input_hashes, sort_keys=True),
                    bootstrap_builder_sha256=digest(__file__),
                    bootstrap_identity_policy="unique NFKD + escaped-name alphanumeric comparison; English game CSV; no synthetic IDs",
                    description_source="Item.csv Description; not visual/model-generated text",
                )
                c.executemany("INSERT INTO build_metadata VALUES(?,?)", metadata.items())
            if (
                c.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or c.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise ValueError("Staged database integrity or foreign keys failed")
        # Hard-link publication is atomic and fails if a racing creator owns output.
        os.link(stage, output)
        return report
    finally:
        stage.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources", type=Path, required=True, help="operator-provided source paths JSON"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new, nonexistent local SQLite file"
    )
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--strict-geometry", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_catalog(
            load_sources(args.sources),
            args.output,
            workers=args.workers,
            strict_geometry=args.strict_geometry,
            progress=lambda done, total: print(
                f"Geometry {done}/{total}", flush=True, file=__import__("sys").stderr
            ),
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Bootstrap failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
