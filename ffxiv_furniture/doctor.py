"""Read-only local setup diagnostic. Standard library only unless --gpu is used."""

from contextlib import closing
from importlib import metadata
import argparse
import json
import os
from pathlib import Path
import sqlite3

from .config import load_seed_layout, load_sources, catalog_path

ROOT = Path(__file__).resolve().parents[1]


def diagnose(db, *, seed=None, render=False, gpu=False):
    checks = []

    def add(name, ok, detail):
        checks.append(dict(name=name, ok=bool(ok), detail=str(detail)))

    db = Path(db).resolve()
    try:
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as connection:
            names = {
                r[0]
                for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                )
            }
            required = {"furniture", "tags", "furniture_tags"}
            if render or gpu:
                required |= {
                    "candidate_assets",
                    "asset_geometry",
                    "furniture_bounds",
                    "house_materials",
                    "placement_info",
                    "support_surfaces",
                    "item_colors",
                    "item_default_dye",
                }
            missing = sorted(required - names)
            add(
                "catalog",
                not missing,
                (
                    "missing schema: " + ", ".join(missing)
                    if missing
                    else "required tables/views present; row coverage not audited"
                ),
            )
    except sqlite3.Error as error:
        add(
            "catalog",
            False,
            f"{error}; supply your own local database, init is only a basic empty catalog",
        )

    if render or gpu:
        for package in ("numpy", "Pillow", "shapely", "moderngl", "mcp"):
            try:
                add(package, True, metadata.version(package))
            except metadata.PackageNotFoundError:
                add(package, False, "install requirements-render.txt")
        try:
            sources = load_sources()
        except (OSError, ValueError) as error:
            add("sources", False, error)
            sources = {}
        for folder in ("interiors", "houses", "materials"):
            if folder not in sources:
                continue
            path = Path(sources[folder])
            add(
                folder,
                path.is_dir(),
                f"{path}; resource-root presence only, not per-asset validation",
            )
        if not seed:
            add("seed", False, "supply --seed or DECO_SEED with a complete local layout")
        else:
            try:
                load_seed_layout(seed)
                add("seed", True, "layout shape and scales valid; app compatibility unverified")
            except (OSError, ValueError, UnicodeError) as error:
                add("seed", False, error)
    if gpu:
        try:
            import moderngl

            context = moderngl.create_standalone_context(require=330)
            try:
                add("OpenGL", True, context.info.get("GL_RENDERER", "context created"))
            finally:
                context.release()
        except Exception as error:
            add("OpenGL", False, error)
    return dict(
        ok=all(c["ok"] for c in checks),
        read_only=True,
        checks=checks,
        note="No downloads, inference, DB writes or extraction. This does not bootstrap missing copyrighted data.",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=catalog_path())
    parser.add_argument("--seed", default=os.environ.get("DECO_SEED"))
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--gpu", action="store_true", help="also test a real OpenGL 3.3 context")
    args = parser.parse_args(argv)
    result = diagnose(args.db, seed=args.seed, render=args.render, gpu=args.gpu)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
