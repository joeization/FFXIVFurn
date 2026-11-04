# FFXIVFurn

A Python/SQLite furniture catalog and tools for editing, previewing, and exporting ReMakePlace layouts through MCP. Interiors and yards use separate sessions. The MCP server does not run an LLM; your client supplies the model.

> **Code and documentation only; no database or game assets are included.** Do not distribute databases, extracted meshes/textures/thumbnails, model caches, or local outputs in this project's releases, attachments, or packages. Those materials belong to their respective rights holders; see the [distribution policy](docs/distribution.md). Native previews are not game or app screenshots.

## Where to start

| Task | Prerequisites | Documentation |
|---|---|---|
| CRUD, tags, text search | Python; a new empty database is sufficient | Quick start below, [Catalog API](docs/catalog.md) |
| Semantic search | Your own descriptions and optional dependencies | [Catalog API](docs/catalog.md) |
| Interior/yard MCP | Complete local catalog, assets, layout seed, OpenGL | [MCP guide](docs/mcp.md) |
| Layout rendering | Same as above; no LLM required | [Renderer](ffxiv_furniture/rendering/README.md) |
| Image classification/vocabulary | Your own image manifest and model endpoint | [Classification](ffxiv_furniture/classification/README.md) |
| Development and script selection | Distinguish supported entry points from historical scripts | [Code guide](WORKSPACE.md) |

**A fresh clone can run empty-database CRUD, but cannot render immediately.** `init` does not create a complete furniture catalog, geometry, house materials, or support surfaces. Data is not available as a separate release download. Follow the [local bootstrap guide](docs/bootstrap.md) with your own assets and English game CSVs. Private classification history is not required; visual tags and vectors are not generated automatically.

## Installation

Python 3.12 is recommended. CRUD uses only the standard library; install other dependencies as needed. All three requirements files have been installed in a fresh Windows Python 3.12 venv and verified with dependency checks, GPU tests, and real MCP calls. Local data is still required. See [development status](docs/development.md). Run from the project root; these examples use **Windows Git Bash**:

```bash
# Create only if .venv does not exist; do not overwrite an existing environment.
python -m venv .venv
PY=.venv/Scripts/python.exe
"$PY" -m ffxiv_furniture --help

# Required only for MCP/GPU rendering.
"$PY" -m pip install -r requirements-render.txt
# Required only for semantic search; the first use downloads a model.
# "$PY" -m pip install -r requirements-semantic.txt
# Required only for classification.
# "$PY" -m pip install -r requirements-classification.txt
```

In PowerShell, use `.\.venv\Scripts\python.exe`; see the [MCP guide](docs/mcp.md) for environment variables. Linux/macOS typically use `.venv/bin/python`. The Python MCP client uses the interpreter that launched it, but Linux/macOS have not been verified on real systems.

## Quick start: no game assets required

Write only to a test database, not the production database. Adding the same ID twice fails; choose a new test database filename when repeating the example.

```bash
PY=.venv/Scripts/python.exe
DB=data/quickstart.sqlite3
"$PY" -m ffxiv_furniture --db "$DB" init
"$PY" -m ffxiv_furniture --db "$DB" furniture-add --id 28639 --name "Leather Sofa" --description "A dark leather sofa" --scope interior
"$PY" -m ffxiv_furniture --db "$DB" search --query "sofa"
"$PY" -m ffxiv_furniture --db "$DB" furniture-get 28639
```

Place `--db` before the subcommand. Omitting it selects `data/furniture.sqlite3`; **always specify a test database explicitly for trial writes**. Image paths are recorded only; images are not downloaded automatically. See the [Catalog API](docs/catalog.md) for more CLI and Python examples.

## Build your own local catalog

Prepare assets and source settings using the [bootstrap guide](docs/bootstrap.md). The output database must not exist; do not run init on it first:

```bash
"$PY" -m ffxiv_furniture.bootstrap --sources data/local-sources.json --output data/local/catalog.sqlite3 --workers 6
export FFXIVFURN_SOURCES="$PWD/data/local-sources.json"
export FFXIVFURN_DB="$PWD/data/local/catalog.sqlite3"
```

Identified items whose geometry cannot be parsed are recorded explicitly, not presented as renderable furniture. Patch values remain unknown without a reliable source. See the guide for coverage and limitations.

## Setup checks (read-only; no downloads or model calls)

```bash
# Basic catalog checks.
"$PY" -m ffxiv_furniture.doctor
# Requires complete local data; also tests a real OpenGL context.
"$PY" -m ffxiv_furniture.doctor --render --gpu --seed data/my-layout.json
```

Missing data or schema produces a nonzero exit status. The command does not manufacture databases, assets, or vectors.

## Decorating and rendering

Once data is ready, configure a session and seed using the [MCP guide](docs/mcp.md). Keep one persistent connection per design, with separate names for interior and yard sessions. Registration in a particular agent application is not required.

- Interiors: Small (ground floor and basement), Medium (ground and upper floors), Apartment (single floor). Large interior MCP is unsupported; Medium basements are not fully supported.
- Yards: S/M/L; outdoor furniture, exterior walls, roofs, fences, doors/windows, roof/wall decorations, and placards. Select styles with `search_materials`/`set_exterior`.
- Start with `status`/`inspect`. After editing, render and inspect the image before continuing. Numerical diagnostics are not aesthetic scores or proof of game collision behavior.
- Normal renders save only PNGs in one `renders/` directory, with revisions distinguished by filename. JSON diagnostics require explicit opt-in. Session state, snapshots, and exports are unaffected.
- OpenGL 3.3 is required; there is no CPU fallback. Water, transparent glass, native emission/particles, and game shadows remain limited; finishes are not guaranteed complete for every house type. Export success is not app-import acceptance.

## Example

<!-- To be filled in by the maintainer. Check image/layout distribution rights first; do not attach databases or extracted assets. -->

To be added.

## Development and pre-distribution checks

```bash
python -m unittest discover -s tests -p 'test_catalog.py' -q
python -m unittest discover -s tests -p 'test_distribution.py' -q
python scripts/check_distribution.py
# The full suite also requires local data, optional dependencies, and a GPU.
# .venv/Scripts/python.exe -m unittest discover -s tests -q
```

Do not ZIP the entire working directory for a release. `.gitignore` does not untrack existing files or protect manual attachments; see the [distribution guide](docs/distribution.md). Code and original project documentation use the [MIT License](LICENSE). The project does not publish releases automatically or include databases. MIT does not cover databases, game/ReMakePlace assets, model weights, or other third-party content, and grants no distribution rights to them.
