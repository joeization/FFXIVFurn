"""Exterior scene assembly using decoded native actor transforms and selected fixtures."""

from pathlib import Path
from ..config import catalog_path
from contextlib import closing
import json, sqlite3, hashlib, math, time, re
import numpy as np
from ..exteriors import ExteriorProfile
from ..geometry import read_static_mesh_bounds
from ..interiors import transform_points
from ..housing import validate_layout_budget
from .assets import Assets
from .raster import render

ROOT = Path(__file__).resolve().parents[2]


def render_exterior(
    layout,
    out,
    *,
    data,
    input_path,
    source_hash,
    db_path=None,
    cameras=None,
    size=(960, 640),
    mirror_view=True,
    dye_mode="mi",
    display_gamma=0.7,
    lighting=None,
    labels=False,
    debug_buffers=False,
    artifacts=False,
    image_prefix=None,
    overwrite=False,
    view_names=None,
):
    from .pipeline import _RESOURCE_CACHE, quaternion_matrix, _mesh_flat

    start = time.perf_counter()
    out = Path(out)
    budget = validate_layout_budget(layout)
    scale = layout.get("exteriorScale")
    if (
        isinstance(scale, bool)
        or not isinstance(scale, (float, int))
        or not math.isfinite(scale)
        or scale <= 0
    ):
        raise ValueError("Invalid exteriorScale")
    profile = ExteriorProfile(
        layout["houseSize"], layout.get("exteriorFixture", []), db_path=db_path
    )
    actors = profile.scene()
    items = layout.get("exteriorFurniture", [])
    dbpath = Path(db_path or catalog_path()).resolve()
    with closing(sqlite3.connect(dbpath.as_uri() + "?mode=ro", uri=True)) as db:
        ids = sorted({i["itemId"] for i in items})
        records = [
            json.loads(r[0])
            for r in db.execute(
                "SELECT evidence FROM asset_geometry WHERE item_id IN (%s)"
                % ",".join("?" for _ in ids),
                ids,
            )
        ]
        for r in records:
            r["item_id"] = int(r["item_id"])
        fallback = {
            i: h
            for i, h in db.execute(
                "SELECT item_id,c1_hex FROM item_colors WHERE c1_hex IS NOT NULL"
            )
        }
        assets = Assets(
            records,
            ROOT / "outputs/render-pipeline/cache",
            mi_tint=dye_mode == "mi",
            fallback_colours=fallback,
            resource_cache=_RESOURCE_CACHE,
        )
        meshes = []
        objects = {}

        def submit(asset, vertices, oid, role, item_id=None):
            for group in asset["groups"]:
                mat = (
                    asset["materials"][group["material_index"]]
                    if group["material_index"] >= 0
                    else None
                )
                a = group["first_triangle"]
                n = group["triangle_count"]
                flat = _mesh_flat(mat, fallback.get(item_id))
                meshes.append(
                    dict(
                        id=oid,
                        vertices=vertices,
                        triangles=asset["triangles"][a : a + n],
                        uv=asset["uv"],
                        material=mat,
                        role=role,
                        **({"flat_color": flat} if flat else {}),
                    )
                )

        for index, item in enumerate(items, 1):
            identity = db.execute(
                "SELECT name,scope FROM furniture WHERE id=?", (item["itemId"],)
            ).fetchone()
            if not identity or tuple(identity) != (item["name"], "exterior"):
                raise ValueError("Unmapped identity, conflicting name or non-exterior item")
            if item.get("attachments"):
                raise ValueError("Exterior attachments require an explicit transform policy")
            t = item["transform"]
            if t.get("scale", [1, 1, 1]) != [1, 1, 1]:
                raise ValueError("Non-unit furnishing scale is unsupported")
            color = (item.get("properties") or {}).get("color")
            rgb = (
                tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
                if color and len(color) >= 6
                else None
            )
            asset = assets.load(item["itemId"], rgb if dye_mode == "mi" else None)
            position = np.asarray(t["location"], float) / scale
            if position.shape != (3,) or not np.isfinite(position).all():
                raise ValueError("Invalid exterior location")
            world = asset["vertices"] @ quaternion_matrix(t["rotation"]).T + position
            submit(asset, world, index, "furniture", item["itemId"])
            objects[str(index)] = dict(
                instance_id=f"furniture-{index:04d}",
                item_id=item["itemId"],
                name=item["name"],
                position_m=position.tolist(),
                rotation=t["rotation"],
            )
    structural = Assets(
        [], ROOT / "outputs/render-pipeline/cache", mi_tint=True, resource_cache=_RESOURCE_CACHE
    )
    for index, actor in enumerate(actors, len(items) + 1):
        key = actor["mesh"]
        record = read_static_mesh_bounds(Path(key))
        record["item_id"] = key
        structural.records[key] = record
        color = actor.get("color")
        rgb = (
            tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
            if color and len(color) >= 6
            else None
        )
        asset = structural.load(key, rgb)
        world = transform_points(asset["vertices"], actor)
        submit(
            asset, world, index, "ground" if actor["category"] == "Ground" else "exterior_structure"
        )
        objects[str(index)] = dict(
            instance_id="exterior-" + actor["name"],
            name=actor.get("fixture_name", actor["name"]),
            category=actor["category"],
            source=actor["mesh"],
            source_sha256=record["source_sha256"],
            decoded_actor_transform=actor,
            world_bounds_m=[world.min(0).tolist(), world.max(0).tolist()],
            app_verified=False,
        )
    ground = next(x for x in meshes if x["role"] == "ground")["vertices"]
    lo = ground.min(0)
    hi = ground.max(0)
    center = (lo + hi) / 2
    r = float(max(hi - lo))
    cx, cy = float(center[0]), float(center[1])
    door = next(a for a in actors if a["category"] == "MainDoor")["translation_m"]
    if cameras is None:
        cameras = [
            dict(
                name="overview",
                position=[cx + r * 0.85, cy + r * 0.9, r * 0.8],
                target=[cx, cy, 2.0],
                fov=65,
            ),
            dict(
                name="entry",
                position=[cx, float(hi[1]) + 4, 2.5],
                target=[door[0], door[1], 1.8],
                fov=85,
            ),
            dict(name="top", position=[cx + 0.01, cy, r * 1.6], target=[cx, cy, 0], fov=45),
        ]
    if view_names:
        cameras = [c for c in cameras if c.get("name") in view_names]
    if not 1 <= len(cameras) <= 8:
        raise ValueError("Need 1..8 bounded exterior cameras")
    if lighting:
        moods = {
            "day": ([0.45, 0.44, 0.42], [0.75, 0.78, 0.85], 1.3),
            "dusk": ([0.10, 0.09, 0.10], [0.22, 0.22, 0.28], 1.25),
            "night": ([0.04, 0.04, 0.07], [0.08, 0.09, 0.15], 1.4),
        }
        if lighting not in moods:
            raise ValueError("Unknown exterior lighting mood")
        alo, ahi, exposure = moods[lighting]
        lights = []
        for mesh in meshes:
            ob = objects[str(mesh["id"])]
            if mesh["role"] == "furniture" and re.search(
                r"lamp|lantern|torch|fire|light", ob["name"], re.I
            ):
                mesh["emissive"] = (0.8, 0.624, 0.4)
                if not any(l["id"] == mesh["id"] for l in lights):
                    vv = mesh["vertices"]
                    p = (vv.min(0) + vv.max(0)) / 2
                    lights.append(
                        dict(
                            id=mesh["id"],
                            pos=p.tolist(),
                            color=[1.0, 0.78, 0.5],
                            intensity=1.3,
                            radius=2.0,
                        )
                    )
        cfg = dict(ambient_lo=alo, ambient_hi=ahi, exposure=exposure, lights=lights[:64])
        cameras = [dict(c, lighting=cfg) for c in cameras]
    if mirror_view:
        cameras = [dict(c, mirror_x=True) for c in cameras]
    stem = image_prefix if image_prefix is not None else "view"
    prefix = image_prefix + "-" if image_prefix else ""
    paths = [out / f"{stem}-{i+1:02d}.png" for i in range(len(cameras))]
    if not overwrite:
        for path in paths:
            candidates = [path.with_name(path.stem + "-labeled.png") if labels else path]
            if debug_buffers:
                candidates.extend(
                    [
                        path.with_name(path.stem + "-ids.png"),
                        path.with_name(path.stem + "-depth.npy"),
                    ]
                )
            if any(p.exists() for p in candidates):
                raise ValueError("Render image already exists; choose a different image_prefix")
    out.mkdir(parents=True, exist_ok=True)
    views = [
        render(
            meshes,
            c,
            path,
            size=size,
            display_gamma=1.0 if lighting else display_gamma,
            labels=labels,
            debug_buffers=debug_buffers,
        )
        for c, path in zip(cameras, paths)
    ]
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    snapshot_data = (json.dumps(layout, ensure_ascii=False, indent=2) + "\n").encode(encoding)
    snapshot = out / (prefix + "layout.json")
    manifest_path = out / (prefix + "manifest.json")
    request_path = out / (prefix + "review-request.json")
    diagnostics = {}
    for category, loader in [("furniture", assets), ("structure", structural)]:
        diagnostics[category] = dict(
            decoded_entries=len(loader.coverage),
            material_slots=sum(r["material_slots"] for r in loader.coverage),
            textured_slots=sum(r["textured_slots"] for r in loader.coverage),
            coverage=loader.coverage,
        )
    result = dict(
        scope="exterior",
        input_layout=str(input_path.resolve()) if input_path else None,
        input_layout_sha256=source_hash,
        rendered_layout=str(snapshot.resolve()) if artifacts else None,
        rendered_layout_sha256=hashlib.sha256(snapshot_data).hexdigest(),
        views=views,
        objects=objects,
        budget=budget,
        geometry_assets=len(assets.coverage),
        material_slots=diagnostics["furniture"]["material_slots"],
        textured_slots=diagnostics["furniture"]["textured_slots"],
        untextured_slots=diagnostics["furniture"]["material_slots"]
        - diagnostics["furniture"]["textured_slots"],
        asset_coverage=assets.coverage,
        native_material_diagnostics=diagnostics,
        exterior_profile=profile.summary(),
        interior_profile=None,
        warnings=profile.summary()["limitations"]
        + (
            ["Approximate ambient/name-based lamps only; no game sunlight or shadows."]
            if lighting
            else []
        ),
        elapsed_seconds=time.perf_counter() - start,
        outside_floor_projection=[],
        stair_keepout_hits=[],
        app_equivalence_verified=False,
        physical_lighting_verified=False,
        parent_material_graphs_reconstructed=False,
        model_calls=0,
        patch=None,
        room_context=False,
        approximate_tint_enabled=False,
    )
    if artifacts:
        result["artifacts"] = dict(
            layout=str(snapshot.resolve()),
            manifest=str(manifest_path.resolve()),
            review_request=str(request_path.resolve()),
        )
        snapshot.write_bytes(snapshot_data)
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        request_path.write_text(
            json.dumps(
                dict(
                    scope="exterior",
                    views=[v["image"] for v in views],
                    objects=objects,
                    warnings=result["warnings"],
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return result
