# Local data preparation

[Back to README](../README.md). This project provides no database/game-resource downloads. Source code alone is insufficient for complete rendering.

## Features and required inputs

| Feature | Local inputs |
|---|---|
| Basic CRUD | Your own empty SQLite database created with `init` |
| Semantic search | Your own descriptions, model cache, optional dependencies |
| MCP/rendering | Complete enriched schema in `data/furniture.sqlite3`, native meshes/materials, house maps, complete seed layout |
| Image classification | Your own images/manifest; configure the model endpoint separately |

Expected default resource directories include `data/gameassets-legacy/`, `geometry-legacy/`, `house-legacy/`, and `house-materials-legacy/`; stain data uses `data/external/Stain.csv`. Internal asset paths and extraction versions must match the parser. Arbitrarily reorganizing directories or supplying a different version may fail. Creating empty directories is not sufficient.

## Reproducible bootstrap entry point

Use the [local bootstrap guide](bootstrap.md) and `python -m ffxiv_furniture.bootstrap`, explicitly specifying native-source JSON, English game CSVs, and a new output database. It does not read private runs, old databases, or old inventories. It creates required runtime schema, identity mappings, native geometry/placement/support surfaces, and house materials without model inference or invented tags.

## A catalog requires more than init

The basic `FurnitureDB` schema supports CRUD. MCP/rendering additionally query `candidate_assets`, `asset_geometry`/`furniture_bounds`, `placement_info`, support surfaces, `house_materials`, and other data. An empty database lacks this coverage; do not fill it with nulls or fake geometry to imitate success.

`scripts/build_real_db.py` depends on historical local artifacts: frozen classification vocabulary, final predictions, Item ID matching, existing test geometry, etc. It is not a one-click builder for new users. Use bootstrap instead to create a runtime catalog without private visual classification. Do not trial-run `fill_*`/import scripts against the production database; back up first and check inputs.

## Seeds and sessions

Prepare complete JSON from a layout you have the right to use. Preserve `houseSize`, interior/exterior scene scales, fixtures, metadata, and unknown fields. Point `DECO_SEED` at it explicitly; the repo includes no seed. Merely relabeling a Medium seed does not produce a calibrated Small seed.

`DECO_FROM_LAYOUT=1` imports furniture for the selected scope only on first creation. Without it, furniture starts empty while structural fields still come from the seed. Reusing a session name resumes it rather than rebuilding it; use a new name for a new design.

## Data protection

`data/`, `outputs/`, and `runs/` are excluded from Git; back them up yourself. Do not attach databases or extracted assets to releases. If data preparation fails, report the missing sources and actual errors instead of substituting fake API, mesh, or vector responses.

## Read-only diagnostics

`python -m ffxiv_furniture.doctor --render --gpu --seed <layout.json>` checks required schema, resource roots, dependencies, seed shape/scales, and a real OpenGL context. It does not download, extract, infer, or write to the database; missing data produces a nonzero exit status. MCP can select a new database with `FFXIVFURN_DB` and source roots/CSVs with `FFXIVFURN_SOURCES`; `--db` overrides only the database for that CLI operation. Maintenance scripts that need private inputs read them from `DECO_SEED` (complete layout), `FFXIVFURN_LARGE_SEED`, and `FFXIVFURN_INSPECTION_DIR` (your retoc inspection output) and stop with a message when unset; no personal paths are built in. Existing roots do not establish complete per-asset or row coverage.
