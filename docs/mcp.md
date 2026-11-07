# MCP usage guide

[Back to README](../README.md) · [Data prerequisites](local-data.md) · [Renderer](../ffxiv_furniture/rendering/README.md)

## Use a database you built yourself

Follow [bootstrap](bootstrap.md), then set `FFXIVFURN_SOURCES` (source JSON) and `FFXIVFURN_DB` (new SQLite database) before launch. The Python client forwards them to the server. Interior/exterior lookups and furniture use the new database/sources without replacing the production database. Restart the connection when switching sources.

## Before launch

Install `requirements-render.txt` and prepare a complete catalog, assets, and seed. Set `DECO_SEED` explicitly; the program no longer silently reads private historical outputs. Missing/incomplete seeds are rejected. Check setup first with `python -m ffxiv_furniture.doctor --render --gpu --seed <your-layout>`. Run only one server at a time per session.

Windows Git Bash (the seed below is your own file):

```bash
export DECO_SESSION=my-room
export DECO_SCOPE=interior
export DECO_SEED=data/my-layout.json
export DECO_MAX_PATCH=7.2
# Set only to import existing furniture on first creation: export DECO_FROM_LAYOUT=1
.venv/Scripts/python.exe scripts/deco_mcp_client.py interactive
```

Equivalent PowerShell settings:

```powershell
$env:DECO_SESSION = "my-room"
$env:DECO_SCOPE = "interior"
$env:DECO_SEED = "data/my-layout.json"
$env:DECO_MAX_PATCH = "7.2"
.\.venv\Scripts\python.exe scripts/deco_mcp_client.py interactive
```

Once the interactive client starts, send one JSON object per line, retaining the same connection and warm caches:

```json
{"id":"s1","tool":"status","arguments":{}}
{"id":"i1","tool":"inspect","arguments":{"include_geometry":true}}
{"id":"r1","tool":"render","arguments":{"view":"overview","width":960,"height":640}}
```

Close gracefully with `quit`, `exit`, `{"close":true}`, or EOF. Do not restart after placing each item. `list` lists tools; `call <tool> '<JSON>'` makes a one-shot call. The helper uses its launching `sys.executable`, not a hardcoded Windows venv in the repo; the ready message reports the interpreter. Complete execution on non-Windows systems remains unverified.

### Keep intermediate files bounded

Send request JSON lines directly to the persistent client's stdin and read correlated response lines from stdout. Do not create one `request-N.json` and `response-N.json` per call or a new file-queue bridge for each design round; the existing interactive client already provides the transport. Keep responses, inventories, schemas and transient analysis in the controller's memory. If a durable call trace is needed, append to one JSONL journal per run, retaining exact failed responses too; do not save base64 image payloads in that journal.

Keep the saved session/history, deliberate recovery snapshots, current exported layout/instance map, one concise verification summary, and the plan/render images actually used for spatial review. Generate plans at planning/spatial-change checkpoints, but do not write a redundant export, inspection dump or schema copy for every status/search/render call. Keep renderer diagnostics opt-in; normal views need JPEGs, not accompanying manifests/layout snapshots/review requests. The two views of one revision are distinct evidence; duplicated images or repeated metadata are not.

This is a policy for new work, not permission to delete historical files. Consolidating old journals requires a verified lossless archive; preserve final layouts, session recovery data and source assets.

For other MCP applications, set `command` to the absolute virtual-environment Python path, `args` to `-m ffxiv_furniture.deco.server`, `cwd` to the project root, and pass the environment variables above. No particular agent's global registration is required. stdout is reserved for the protocol; logs go to stderr.

## Settings

| Variable | Meaning |
|---|---|
| `DECO_SESSION` | Name; reusing it resumes `outputs/deco-sessions/<name>/state.json` |
| `DECO_SCOPE` | `interior` (default) or `exterior`; use different names for each |
| `DECO_SEED` | Complete layout of the correct house size; keep explicitly set even when resuming |
| `DECO_FROM_LAYOUT` | `1` imports that scope's furniture on first creation only; default is empty furniture |
| `DECO_STYLE` | Style for a new interior session; existing sessions retain their persisted value |
| `DECO_MAX_PATCH` | For example, `7.2`; filters search and rejects newer furniture/materials. Unknown patches are not confirmed eligible |

## Support and workflow

Interior support: Small ground floor/basement, 300 items; Medium ground/upper floors, 450 items, with incomplete basement support; Apartment single floor, 150 items. Large interior MCP is unsupported. House size comes from the seed; it is not silently replaced.

For yards, use `DECO_SCOPE=exterior` and another session name. S/M/L budgets are 40/60/80 items respectively. `search_materials` kinds are `wall`, `roof`, `fence`, `door`, `window`, `roof_decor`, `wall_decor`, and `placard`. Pass exact names or Item IDs through the corresponding `set_exterior` parameters, together with `expected_revision`. Roofs/walls are filtered by Cottage/House/Mansion size and retain native actor positions.

1. Use `status`/`inspect` to check structures, stairs, and cameras before searching furniture/materials.
2. Use `place`/`move`/`rotate`/`face`/`dye`, or atomic `batch`; take a `snapshot` before major changes.
3. `render` (or `render_sheet` for several labelled views in one JPEG) and inspect the actual image. Use `analyze_layout` for circulation/support diagnostics (including `wall_gaps`: narrow slits that leak a room meant to be sealed) and `check_routes` for named walking routes (raised platforms such as Tatami Loft are listed as steps, not blockers; `analyze_layout().entrance_tall` lists pieces 2 m+ tall within 1.5 m of the arrival lane), then edit and inspect again. `inspect().surfaces[].center_world` gives each support surface's world centre for `place_on`. From Python, drive one long-lived server with `scripts/deco_driver.py` (`DecoClient`). A yard session can pick up a newer interior export with `refresh_indoor(layout_path)` instead of a new session and replay. `scripts/review_deco.py --staged` runs reviewers in order and stops at the first non-ok run; acceptance still needs every run ok. FFXIV permits intentional overlaps, embedding, and floating; most spatial checks are advisory, not aesthetic scores.
4. Use `undo`/`redo`/`restore` to recover earlier states. `expected_revision` guards against stale submissions.
5. `export_json` writes UTF-16LE BOM and preserves unknown seed fields. Yard edits preserve the interior payload. It does not overwrite the app Save; validate separately after app import.
6. Use flat plans throughout the design process, not only at handoff: inspect the current or empty shell, plan zones and gate/door/stair-to-destination routes before placing furniture, regenerate after each spatial batch, and compare plans before accepting edits. Pair each plan review with a full overview and occupied eye-level render; tree crowns, light heights and occlusion need three-dimensional checks. Yard overviews must frame the actual gate/perimeter, with inward and reverse arrival views. Fence gates, straight and corner sections are one matched fixture set, never independently replaced.
7. Generate the final plan alongside the export. For supported interior plans: `python scripts/layout_schematic.py <layout.json>`. It reads the catalog DB read-only and writes an SVG (vector; `--format jpg` for a raster) to the layout's `renders/` directory. Planning and final images omit furniture inventories by default; `--index` explicitly opts into the interior script's inventory. For exteriors use `python scripts/yard_schematic.py <layout.json> [--limit N] [--max-patch 7.2]` (same SVG/JPEG choice; gate and door from the native exterior actors); the interior script is not a yard renderer. Furniture may legally poke through walls, and plans must not clip it or change layout coordinates.

## Coordinates and outputs

Units are meters: +X east, +Y north, +Z up. `yaw_deg` rotates counterclockwise about Z, with 0 facing local +Y. The default reference is `bottom_center`; `pivot` means the asset origin. `face` angles are 0 east/90 north/180 west/270 south; do not confuse them with yaw. Use the measured house-specific values from `inspect`, not another design's stair coordinates.

Images share the session's `renders/` directory and include revision/view/settings hash in filenames. Only JPEGs are saved by default (the ID/depth debug buffers stay lossless PNG/NPY and are written only with debug_buffers); `diagnostics=true` adds diagnostic JSON. Renders of all but the newest two revisions are pruned automatically; `keep=true` (render or render_sheet) marks a file `-keep` so it survives. `render_sheet` keeps its panels in memory and writes only the composite. `export_json` keeps only the newest export (and map) per export name. `review_deco.py` leaves only `review-reply.json` per round unless `--keep-artifacts` or a reply failed to parse. Session state, explicit snapshots, and exports remain available. `mirror=true` flips the displayed image horizontally without changing coordinates. Materials/lighting are approximate; they do not establish app, game collision, or navigation validation.

Resuming requires the same house size. Opening an existing Small session with a Medium seed fails with HOUSE_MISMATCH without rewriting saved state. Use a new session name to change house size.
