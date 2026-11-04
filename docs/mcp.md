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
3. `render` and inspect the actual image. Use `analyze_layout` for circulation/support diagnostics, then edit and inspect again. FFXIV permits intentional overlaps, embedding, and floating; most spatial checks are advisory, not aesthetic scores.
4. Use `undo`/`redo`/`restore` to recover earlier states. `expected_revision` guards against stale submissions.
5. `export_json` writes UTF-16LE BOM and preserves unknown seed fields. Yard edits preserve the interior payload. It does not overwrite the app Save; validate separately after app import.
6. When a layout is finalized (exported, committed, or delivered), also generate the flat schematic: `python scripts/layout_schematic.py <layout.json>`. It reads the catalog DB read-only and writes one PNG beside the layout; furniture may legally poke through walls, and the drawing never clips it.

## Coordinates and outputs

Units are meters: +X east, +Y north, +Z up. `yaw_deg` rotates counterclockwise about Z, with 0 facing local +Y. The default reference is `bottom_center`; `pivot` means the asset origin. `face` angles are 0 east/90 north/180 west/270 south; do not confuse them with yaw. Use the measured house-specific values from `inspect`, not another design's stair coordinates.

Images share the session's `renders/` directory and include revision/view/settings hash in filenames. Only PNGs are saved by default; `diagnostics=true` adds diagnostic JSON. Session state, explicit snapshots, and exports remain available. `mirror=true` flips the displayed image horizontally without changing coordinates. Materials/lighting are approximate; they do not establish app, game collision, or navigation validation.

Resuming requires the same house size. Opening an existing Small session with a Medium seed fails with HOUSE_MISMATCH without rewriting saved state. Use a new session name to change house size.
