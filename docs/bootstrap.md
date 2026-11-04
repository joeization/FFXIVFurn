# Local catalog bootstrap without private classification history

[Back to README](../README.md) · [Data policy](distribution.md) · [MCP](mcp.md)

This workflow builds a new database from **native legacy assets and English game CSVs that you supply and have the right to use**. It does not use the maintainer's database, `runs/round1`, frozen vocabulary, old geometry databases, or `outputs/house-layouts/native-bounds.json`. It makes no model calls or downloads and never overwrites an existing database. Databases and extracted assets must still not be distributed with the project; MIT grants no rights to third-party content.

## 1. Prepare sources

You can use legally obtained retoc legacy assets directly. Each root must point to a **Content directory**, not a Paks directory, an individual furniture directory, or a thumbnail-only directory.

| Setting | Contents |
|---|---|
| `furniture_roots` | One or more Content directories containing `GameAssets/` and `YardAssets/` furniture meshes, materials, and textures |
| `interiors` | Content directory containing native interior structures under `HouseAssets/InteriorStyles/` |
| `houses` | Content directory containing house/yard maps under `Maps/` and the `HouseAssets/` referenced by those maps |
| `materials` | Content directory containing `HouseAssets/Wallpaper`, `Flooring`, `CeilingLight`, doors/windows/roofs/exterior walls, etc. |
| `items_csv` | English Item.csv for your data version; required columns: `#`, `Name`, `ItemUICategory`, `DyeCount`, `IsUntradable`, `ItemSearchCategory`; optional `Description` |
| `ui_categories_csv` | English ItemUICategory.csv with `#` and `Name` columns |
| `stains_csv` | Stain.csv with `Name`, `Color`, `Shade`, `IsHousingApplicable`, `IsMetallic` columns |

CSVs must be UTF-8 (BOM allowed), with these column names in the first row. Export older header layouts correctly yourself; the builder does not guess columns. Chinese item-name CSVs cannot be used for unique English native-folder name matching.

### Converting original assets yourself

First confirm that the source and terms permit this, and obtain retoc separately; it is not distributed with the repo. The following Windows Git Bash template uses replaceable paths and a **Paks directory** as input. No keys or encryption bypass are provided. The parser currently supports a bounded UE5.3 legacy format, not every app version.

```bash
RETOC="<your-retoc-executable>"
PAKS="<your-app-Paks-directory>"
"$RETOC" to-legacy --filter /GameAssets/ --no-shaders "$PAKS" data/gameassets-legacy
"$RETOC" to-legacy --filter /YardAssets/ --no-shaders "$PAKS" data/gameassets-legacy
"$RETOC" to-legacy --filter /InteriorStyles/ --no-shaders "$PAKS" data/house-interiors-legacy
"$RETOC" to-legacy --filter /Maps/ --no-shaders "$PAKS" data/house-legacy
"$RETOC" to-legacy --filter /HouseAssets/ --no-shaders "$PAKS" data/house-legacy
"$RETOC" to-legacy --filter /HouseAssets/ --no-shaders "$PAKS" data/house-materials-legacy
```

Preserve `.uasset`, `.uexp`, `.ubulk`, and their original relative paths. `_T` thumbnails alone cannot provide geometry or object dimensions. Existing conversion outputs elsewhere need not be copied; point the settings at their location.

Do not extract only individual roof/wall folders: meshes can reference shared `HouseAssets/Materials/` packages, and those materials can reference textures under another house-size folder. A mesh and thumbnail may load while every material slot renders as a white fallback. Keep the full `/HouseAssets/` conversion above, or resolve the exact native dependency chain. Shared `/Game/Materials/` master packages are outside `/GameAssets/` and `/YardAssets/`; retain them too when preparing material/shader diagnostics. Missing files, unsupported material layouts, and unsupported shader graphs are separate findings. Re-render the same selected asset after restoring dependencies; changing the fixture is not a renderer repair.

## 2. Create source settings

Copy the [path template](../examples/local-sources.example.json) to `data/local-sources.json` and enter your actual locations. The template contains paths only, not game data.

- Absolute and relative paths are accepted. Relative paths resolve against **the directory containing the settings JSON**, not the shell's working directory.
- Environment variables and `~` are not expanded; invalid paths are not silently repaired.
- If multiple furniture roots contain different content for the same asset key, the builder refuses to mix source versions.
- If settings/assets move, build a new database. Do not copy someone else's database containing absolute asset paths and assume it is portable.

## 3. Install and build a new database

Run from the project root:

```bash
# Create only if .venv does not exist; do not recreate an existing environment.
python -m venv .venv
PY=.venv/Scripts/python.exe
"$PY" -m pip install -r requirements-render.txt
"$PY" -m ffxiv_furniture.bootstrap --sources data/local-sources.json --output data/local/catalog.sqlite3 --workers 6
```

Linux/macOS typically use `.venv/bin/python`, but native/GPU execution has not been verified on those platforms.

**The target file must not exist. Do not run init on it first.** Existing files are rejected; there is no `--force`. Use a new filename to rebuild. The workflow first creates a staging SQLite database in the same directory. After measurements, integrity/foreign-key checks, and input-change checks pass, it publishes through an atomic hard link that cannot overwrite the target. The filesystem must support hard links. Unsupported filesystems fail explicitly rather than falling back to a potentially overwriting operation. Failure cleans up the workflow's own staging file; staging files left by a forcibly killed process are not completed databases.

`--workers` must be a positive integer; use 1 on smaller machines. `--strict-geometry` refuses publication if geometry/support-surface parsing fails for any identified furniture. By default, metadata and explicit failure records are retained, and only successfully measured furniture enters `furniture_bounds` for MCP use.

## 4. Inspect results and select the new database

Normal stdout is summary JSON; geometry progress goes to stderr. Do not rely on exit 0 alone: read `identified_items`, `measured_items`, and `issues` to understand usable coverage. In SQL, `bootstrap_issues` records individual failures; `build_metadata` stores source paths, CSV hashes, builder code hash, and methods.

```bash
export FFXIVFURN_SOURCES="$PWD/data/local-sources.json"
export FFXIVFURN_DB="$PWD/data/local/catalog.sqlite3"
"$PY" -m ffxiv_furniture search --query "sofa"
# Requires your own complete layout; none is supplied with the repo.
"$PY" -m ffxiv_furniture.doctor --render --gpu --seed data/my-layout.json
export DECO_SEED="$PWD/data/my-layout.json"
export DECO_SESSION=my-bootstrap-room
export DECO_SCOPE=interior
"$PY" scripts/deco_mcp_client.py interactive
```

In PowerShell, use `$env:FFXIVFURN_SOURCES`/`$env:FFXIVFURN_DB` with absolute file paths. Explicit catalog paths supplied through `--db` or the Python API take precedence over defaults; MCP uses `FFXIVFURN_DB`. `FFXIVFURN_SOURCES` also selects native maps, interiors/exteriors, textures, and stains; the client forwards it to the server it starts. **Restart the server after changing settings or rebuilding data. Do not hot-swap sources on a connection with warm caches.**

Without these environment variables, the original project `data/` paths remain in use; your production database is not replaced. The render CLI accepts `--db`, but native assets/stains still follow the sources settings.

## 5. What the new database includes and excludes

Included:
- **Unique name plus housing UI category matching** between normalized asset names and English game tables. Folder numbers or sequential IDs never replace Item RowIds.
- Interior/exterior scope, game names/original Description, and determinable market/dye fields.
- Bounds/pivots measured from native meshes, placement metadata, and support surfaces. Facing or mounting-height priors/heuristics retain explicit methods; they are not all claimed as game facts.
- A house-material catalog, required runtime tables/views, provenance, and failure records.

Excluded:
- Private classification, visual descriptions, style vocabulary, human review, approximate color data, or model-generated tags.
- Precomputed E5 vectors. Ordinary text search, MCP edits, and rendering do not require them. To use semantic indexing, follow the [Catalog API](catalog.md) explicitly; that may download a model and compute embeddings.
- Guessed cash_shop values, patches, game placement legality, or shader reconstruction. Missing sources yield NULL, not dimensions guessed from thumbnails, substitute boxes, or claims of complete materials.

Name matching is a traceable identity association, not complete ItemData binary parsing or app-import acceptance. Missing/ambiguous mappings, or multiple assets competing for one Item ID, remain NULL rather than being chosen arbitrarily. Unparseable native assets may retain metadata but are not presented as renderable furniture.

### Game patch is a separate, optional explicit source

The Item.csv data version, folder version, or app version does not establish an individual furniture item's patch. `patch` defaults to NULL. If you have a reliable Item RowId-to-patch table, add `patches_csv` to the sources JSON, with CSV columns `item_id,patch`. IDs must be positive integers; patches are preserved as decimal version text, such as 7.21, without semver conversion or guessing.

**A NULL patch does not mean "eligible for 7.2".** Existing MCP `DECO_MAX_PATCH` filtering does not automatically reject unknown patches. If strict eligibility is required, supply complete, reliable patch data before use; a successful build is insufficient.

## 6. Verification boundaries

The workflow has been tested with real local inputs in a source-only copy initially containing no data/runs/outputs, followed by MCP/GPU execution using the new database. Synthetic tests verify atomic publication, schema, ambiguity, and error handling; they are not native conversion results. Actual coverage depends on your sources and parser version. Successful rendering does not verify water, glass, particles, character collision, or game import.

Keep databases, source settings, game CSVs, extracted assets, and generated images in local ignored areas, not release attachments. Original code and documentation are MIT-licensed.
