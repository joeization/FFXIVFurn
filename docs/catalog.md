# Catalog API and semantic search

[Back to README](../README.md). Examples use local test databases only; no distributable furniture dataset is included.

## Data model (three core tables)

| Table | Fields |
|---|---|
| `furniture` | `id`, `name`, `description`, `image_path`, `length`, `width`, `height`, `patch`, `marketable`, `cash_shop`, `dyeable`, `dye_channels` |
| `tags` | `id`, `category`, `name`; category + name is unique |
| `furniture_tags` | Composite primary key: `furniture_id`, `tag_id`; `source`, `confidence` |

- Furniture `id` is the **FFXIV Item sheet RowId**, not a model name, HousingFurniture RowId, or sequential ID. Tag IDs are database-generated.
- Length, width, and height are **meters** in furniture-local coordinates, not JSON world coordinates. Use `NULL` for unknown values, not 0 or thumbnail-based guesses. Model-specific length/width axis calibration is not available at this stage.
- `patch` is text to avoid floating-point changes to version information. CRUD stores it without deciding eligibility; MCP separately filters through `DECO_MAX_PATCH`. All versions may be cataloged, including furniture not yet released on the Taiwan servers.
- `marketable` indicates whether market trading is allowed, not whether an item is currently listed. `cash_shop` describes cash-shop acquisition; the two fields are independent. Python API/JSON values are bool or None/null; SQLite uses 1/0/NULL. Unknown does not mean false and is not inferred from missing tags or images.
- CLI add/update/search accept `--marketable` / `--no-marketable` and `--cash-shop` / `--no-cash-shop`. Omitted search filters are unrestricted; explicit false excludes unknowns. Updates can restore unknown with `--clear marketable` / `--clear cash_shop`.
- `category` is unrestricted text, such as `style`, `material`, `color`, `function`, `placement`, or `theme`, not an enum. Names/categories are trimmed but uniqueness uses case-sensitive exact values; standardize vocabulary before import.
- `source` may be `manual`, `game_data`, or the actual model name. `confidence` is 0–1 or `NULL`; **a model's self-reported confidence is not calibrated accuracy**.
- A furniture/tag pair has one association. Attaching again overwrites source/confidence; this is **not review history**. A future Qwen importer should check existing manual associations before overwriting human-confirmed information.
- `dyeable` is bool or NULL; `dye_channels` is a nonnegative integer or NULL. Zero means confirmed no channels; NULL means unknown. Neither field is inferred from the other or from thumbnails. Both are supported by API add/update. CLI flags are `--dyeable` / `--no-dyeable` and `--dye-channels 2`; `--clear dyeable --clear dye_channels` restores unknown. Production dye eligibility/channel counts come from game data. MCP `dye` accepts only furniture with `dyeable=1`.
- SQLite foreign_keys is enabled. Deleting furniture or a tag removes its associations without deleting the other endpoint. `PRAGMA user_version=4` covers the core schema; production catalogs also contain geometry, support surfaces, house materials, vectors, etc. (see [WORKSPACE.md](../WORKSPACE.md)). Older versions gain missing columns on open while preserving data, with new columns defaulting to NULL. Unknown future versions are rejected.

## Python API

```python
from ffxiv_furniture import FurnitureDB

with FurnitureDB("data/test.sqlite3") as db:
    # Method examples: duplicate IDs/category+name pairs fail rather than overwrite.
    item = db.add_furniture(
        13075, "Oriental Round Table", description="An oriental round table",
        image_path="images/13075.png", patch="3.1",
    )
    tag = db.add_tag("style", "Japanese-inspired")
    db.add_furniture_tag(13075, tag["id"], source="manual", confidence=1.0)

    item = db.get_furniture(13075)  # dict with tags/provenance; None if absent
    db.update_furniture(13075, description="A round wooden table", height=None)
    db.update_tag(tag["id"], name="Japanese")
    tags = db.list_tags(category="style")
    tag = db.get_tag(tag["id"])

    results = db.search_furniture(query="Japanese", limit=50, offset=0)
    results = db.search_furniture(tag_ids=[tag["id"]], tag_mode="all")
    db.remove_furniture_tag(13075, tag["id"])
    db.delete_tag(tag["id"])
    db.delete_furniture(13075)
```

Each write method is one transaction; there is no atomic transaction spanning multiple methods. API results are dict/list values directly serializable as MCP JSON. Use a separate `FurnitureDB` instance per thread/request, never a shared connection across threads. Exiting `with` closes the connection.

### Search rules

- `query` matches a substring in name **or** description **or** tag name/category.
- `name` and `description` target individual fields and combine with other conditions using **AND**.
- `tag_ids=[1, 2]` defaults to `tag_mode="all"`, requiring all tags; `"any"` requires at least one.
- `query="Japanese wood"` searches that entire string; **it does not tokenize it into two tags**. For exact multiple-tag filtering, obtain IDs with `list_tags()`, then pass `tag_ids`.
- `%`, `_`, and backslash are literal characters, not wildcards. Values use parameter binding and fields use an allowlist.
- SQLite's default LIKE is case-insensitive for ASCII. No additional tokenization/Unicode normalization is performed for other languages.
- Results are stably ordered by furniture ID. `limit` is 1–1000; `offset` is nonnegative. Results contain no total-count field.
- The initial implementation uses LIKE rather than FTS5: Chinese substring searches remain simple and predictable without default-tokenizer segmentation differences. An indexing strategy can be added if large-dataset performance requires it.

## Complete CLI operations

```bash
python -m ffxiv_furniture --help
python -m ffxiv_furniture --db data/test.sqlite3 furniture-get 28639
python -m ffxiv_furniture --db data/test.sqlite3 furniture-update 28639 --description "Updated description" --height 1.2
python -m ffxiv_furniture --db data/test.sqlite3 furniture-update 28639 --clear height
python -m ffxiv_furniture --db data/test.sqlite3 furniture-update 28639 --description ""
python -m ffxiv_furniture --db data/test.sqlite3 furniture-delete 28639
python -m ffxiv_furniture --db data/test.sqlite3 tag-list --category style
python -m ffxiv_furniture --db data/test.sqlite3 tag-update 1 --name "Minimalist" --category style
python -m ffxiv_furniture --db data/test.sqlite3 tag-detach 28639 1
python -m ffxiv_furniture --db data/test.sqlite3 tag-delete 1
python -m ffxiv_furniture --db data/test.sqlite3 search --name "table" --description "wood" --limit 20
python -m ffxiv_furniture --db data/test.sqlite3 search --tag-id 1 --tag-id 2 --tag-mode any
```

Successful results are JSON on stdout. Errors are JSON on stderr with exit code 1. argparse reports malformed arguments with exit code 2. Missing get/update targets are errors; repeated deletion/detachment returns false.

## Description-based semantic search (optional)

### Installation and CLI

Windows Git Bash example (activation is unnecessary; do not recreate an existing `.venv`):

```bash
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-semantic.txt
./.venv/Scripts/python.exe -m ffxiv_furniture --db data/test.sqlite3 embed-index --batch-size 32 --model-cache data/model-cache
./.venv/Scripts/python.exe -m ffxiv_furniture --db data/test.sqlite3 semantic-search --query "dark ornate classical cabinet" --top-k 10 --marketable --no-cash-shop --model-cache data/model-cache
./.venv/Scripts/python.exe -m ffxiv_furniture --db data/test.sqlite3 semantic-search --query "pink low-backed sofa" --tag-id 1 --tag-id 2 --tag-mode all --top-k 5 --local-files-only
```

If `py -3.12` is unavailable, use `uv python install 3.12` and `uv venv --python 3.12 .venv`. Basic CRUD does not require these dependencies. Place `--db` before the subcommand, and `--model-cache`, `--local-files-only`, and `--model` after the semantic subcommand. Currently `--model` accepts only `intfloat/multilingual-e5-small`; it never silently changes models/dimensions.

The first model use downloads official ONNX/tokenizer files. The default cache is the **absolute project path `data/model-cache`**, overridable by `FASTEMBED_CACHE_PATH` or `--model-cache` (CLI takes precedence). `--local-files-only` prohibits downloads and fails on incomplete caches. Empty databases/no valid candidates do not load the model. Caches are excluded from version control. FastEmbed/sqlite-vec are optional and imported/loaded only for semantic features.

On Windows, disabled SQLite extension loading, incompatible DLL architecture, or missing runtimes produce stderr JSON and exit code 1, not fake vectors or a hidden Python-distance fallback. Successful stdout remains JSON; downloader progress may appear on stderr.

### Python API

```python
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.semantic import SemanticIndex

with FurnitureDB("data/test.sqlite3") as db:
    index = SemanticIndex(db, cache_dir="data/model-cache", local_files_only=True)
    stats = index.refresh(batch_size=32)
    results = index.search(
        "dark ornate classical cabinet", top_k=10,
        tag_ids=[], tag_mode="all", marketable=True, cash_shop=False,
    )
    # stats: model, dimension, indexed, unchanged, removed, skipped
    # results: [{"distance": 0.12, "similarity": 0.88, "furniture": {...with tags...}}]
    # These scores illustrate the structure only; they are not measured results.
```

`SemanticIndex(db, *, model=MODEL, cache_dir=None, local_files_only=False)` uses the existing connection without closing it. As with CRUD, create one instance per thread/request. Do not call it inside an unfinished external transaction. `search(query, *, top_k=10, tag_ids=(), tag_mode="all", marketable=None, cash_shop=None)` returns list[dict]. Both `top_k` and `batch_size` are 1–1000.

### Index contract and freshness

- **Only original `description` is embedded**, without names, tags, dimensions, or market conditions. `visual_description` has not been added to the schema; model text does not overwrite original descriptions.
- E5 documents receive `passage: ` and queries receive `query: `, with attention-mask mean pooling and L2 normalization. Before storage, vectors are checked again for finite/nonzero values and **384 dimensions**, then stored as little-endian float32. If FastEmbed lacks built-in support, `add_custom_model` registers the official `intfloat/multilingual-e5-small` `onnx/model.onnx`, not generic CLS pooling.
- Vectors persist in `furniture_vectors` (`vec0`, cosine, 384 dimensions), rowid = furniture Item RowId. `furniture_embedding_metadata` records model, dimension, pipeline, and SHA-256 of the original UTF-8 description. The base schema is `PRAGMA user_version=4`; vector tables are independent. New connections can still perform ordinary CRUD without loading the extension.
- Description changes, including whitespace, immediately invalidate the old hash and exclude stale results. Empty/whitespace descriptions are not indexed; deleted furniture does not return residual vectors. `embed-index` removes stale/deleted/orphan entries and recomputes only missing/changed descriptions. Unchanged reruns make no model calls. Name/tag/market changes need no re-embedding.
- Each batch has its own transaction and completed batches survive for resume. If another connection changes/deletes a description during inference, it is skipped (`skipped`); refresh again to fill gaps. Indexing does not lock the database throughout inference.
- SQL first filters valid descriptions, all/any tags, and nullable market/cash-shop conditions. An **exact sqlite-vec `vec_distance_cosine` scan** then sorts candidates and selects top-k. It does not retrieve global top-k first and discard ineligible matches afterward. Cost is linear in candidate count, not claimed ANN performance. Equal distances sort by Item ID.
- `distance` is cosine distance and `similarity=1-distance`, not accuracy or a percentage. Appearance absent from descriptions may remain undiscoverable. Real descriptions and Chinese queries still require separate human quality assessment.

## Verification

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -q
```

Coverage includes CRUD, tags/search, semantic indexing, CLI flows, interior decoration MCP (operations, validation, history, export, dyes, stairs, analysis), structures/rendering for different interiors, and GPU rasterization. Tests use temporary databases/sessions rather than changing production data. GPU tests skip if OpenGL 3.3 is unavailable.
