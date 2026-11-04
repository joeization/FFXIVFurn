# Code and documentation guide

[Back to README](README.md). This is a stable entry point, not a log of private design progress or fixed dataset counts.

## Module responsibilities

| Path | Responsibility |
|---|---|
| `bootstrap.py`, `placement.py` | Build a new catalog from your own native assets/game CSVs; shared geometry measurements without private classification history |
| `config.py`, `doctor.py` | Explicit model settings, shared seed validation, read-only environment diagnostics |
| `ffxiv_furniture/database.py`, `__main__.py` | Standard-library SQLite CRUD/CLI |
| `semantic.py`, `material_semantic.py` | Optional E5/sqlite-vec search |
| `deco/core.py`, `deco/server.py` | Sessions, editing, validation, stdio MCP |
| `deco/exterior.py` | Separate outdoor catalog/session; preserves interior data |
| `interiors.py`, `exteriors.py`, `house_profiles.py` | Structures, house profiles, native actors |
| `geometry.py`, `geometry_mesh.py` | Native meshes and geometry |
| `rendering/` | Native resources, materials, GPU renderer, CLI |
| `layout.py`, `housing.py` | Layout export, identity, budgets |
| `classification/` | Separate image classification, vocabulary, scheduling; does not automatically publish to the production catalog |
| `design/` | Model planning, placement, visual feedback; not required for MCP |
| `tests/` | Basic tests and integration tests requiring local resources |

## Script categories (filenames retained to preserve references)

- **Normal entry points:** `python -m ffxiv_furniture`, `python -m ffxiv_furniture.rendering`, `python -m ffxiv_furniture.deco.server`.
- **Script inventory and risks:** see [scripts/README.md](scripts/README.md).
- **Persistent MCP client:** `scripts/deco_mcp_client.py interactive`; `list` lists tools, and `call` makes a one-shot call. Uses the Python interpreter that launched the client; see the MCP guide for platform verification limits.
- **Staged plans:** `scripts/deco_offline.py`; commits changes. Do not replay committed furniture-creation steps.
- **Read-only diagnostics/audits:** `audit_mcp_interiors.py`, `audit_mcp_interior_geometry.py`, `verify_interior_switching.py`, `scan_missing_textures.py`, `layout_schematic.py` (flat finalized-layout plan; writes only a PNG into the layout's `renders/`). Check arguments and output locations first.
- **Catalog maintenance/database writes:** `build_real_db.py`, `fill_*.py`, `import_material_tags.py`, `index_materials.py`. Most depend on local historical artifacts. The historical build_real_db script is not a fresh-clone entry point; new users should use `python -m ffxiv_furniture.bootstrap`. Back up data first.
- **Models/potential charges:** `design_room.py`, `refine_design.py`, `iterate_render.py`, `review_*.py`, `run_opus_design.py`, and others. Check endpoints/models before running; do not invoke these during installation or setup tests.
- **Historical/one-off experiments:** other build/test/probe and design-specific scripts remain for provenance, not as recommended entry points. Further reorganization and portability work remain pending.

## Local directories (excluded from Git/releases)

`data/` stores databases, extracted assets, seeds, CSVs, and model caches; `outputs/` stores sessions, renders, exports, and evidence; `runs/` stores classification history; `tools/` stores local tools. `spikes/`, `tasks/`, and `HANDOFF.md` contain private experiments and handoffs. Git does not back up these files. Back them up separately; do not delete them merely because they are ignored.

## Documentation index

- [Installation and quick start](README.md)
- [Local data preparation](docs/local-data.md) / [Reproducible bootstrap](docs/bootstrap.md)
- [MCP usage](docs/mcp.md)
- [Catalog API](docs/catalog.md)
- [Rendering](ffxiv_furniture/rendering/README.md)
- [Classification](ffxiv_furniture/classification/README.md) / [Scheduling](ffxiv_furniture/classification/SCHEDULER.md)
- [Distribution policy](docs/distribution.md)
- [Remaining work and verification](docs/development.md)
- [Design method](DESIGN_CONTEXT.md): advanced methodological reference; not every method is implemented by the tools. External sources retain their own rights.
