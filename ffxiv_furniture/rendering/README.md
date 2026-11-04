# Native GPU renderer

[Back to README](../../README.md) · [Local data](../../docs/local-data.md) · [MCP](../../docs/mcp.md)

Multi-view previews of native triangles/Base textures, not complete Unreal shaders or a reproduction of ReMakePlace output. Install `requirements-render.txt` and supply a complete local catalog/extracted assets. OpenGL 3.3 is required; there is no CPU fallback. Installing packages does not establish GPU availability.

## CLI

Run from the project root in Windows Git Bash. Supply your own complete `data/my-layout.json`; none is included in the repo.

```bash
.venv/Scripts/python.exe -m ffxiv_furniture.rendering --help
.venv/Scripts/python.exe -m ffxiv_furniture.rendering --layout data/my-layout.json --output-dir outputs/previews --image-prefix indoor-a --room-context --rough-room-finish --dye-mode mi
# Yards use a separate scope and read exteriorFurniture/exteriorScale/exteriorFixture.
.venv/Scripts/python.exe -m ffxiv_furniture.rendering --layout data/my-layout.json --output-dir outputs/previews --image-prefix yard-a --scope exterior --dye-mode mi
```

`--cameras cameras.json` supplies 1..8 cameras. `--width`/`--height` control dimensions; `--no-mirror` disables display mirroring without changing world coordinates. `--dye-mode mi` approximates native Tint and instance dyes; `none` uses original Base, while `default` uses database default dyes and does not establish app-correct color. See `--help` for the full CLI.

The Python entry point is `ffxiv_furniture.rendering.pipeline.run_pipeline(layout, output_dir, ...)`. Layout may be a path or dict; pass `scope='exterior'` explicitly for yards. It returns metadata without requiring a temporary JSON file.

## PNG-only output and diagnostics

Normal operation writes only requested PNGs, such as `indoor-a-01.png`. Use different prefixes in the same output-dir rather than creating a subdirectory for every render. Existing filenames are rejected by default.

- `--labels` writes the numbered version only, without a duplicate unnumbered image.
- `--debug-buffers` explicitly requests IDs PNG and depth NPY outputs.
- `--artifacts` explicitly requests prefixed layout, manifest, and review-request JSON files in the same directory.
- MCP filenames automatically include revision/view/settings hash, all under the session's `renders/`. Diagnostic JSON requires `diagnostics=true`. The metadata cache holds at most 64 entries and can be recomputed after restart without requiring a manifest.
- PNG-only policy does not delete or move state, snapshots, `export_json` outputs, or old renders.

## House types and yards

Interior MCP supports Small ground floor/basement, Medium ground/upper floors, and single-floor Apartments. Medium basements and Large interiors are not fully supported. A successful PNG does not establish complete floors or finishes.

S/M/L yards use native exterior-map component positions, rotations, and separate parts. `set_exterior` replaces walls, roofs, fences, doors, windows, roof decorations, wall decorations, and placards; first query exact names/IDs with `search_materials`. Walls/roofs are filtered by Cottage/House/Mansion size. Fences preserve straight, corner, and entrance components. The yard region is the ground projection minus the house projection, not character collision or game navigation.

Unknown IDs/component schemas, missing native models, or unsupported structures are not replaced with fake boxes. Material parsing failures may use an explicit fallback; inspect metadata warnings. A catalog renderable flag does not establish complete shader reconstruction.

For white-model defects, inspect `native_material_diagnostics` by `furniture`, `structure`, and (indoors) `fixtures`, including each entry's `notes` and per-slot `warning`. Legacy top-level slot totals cover furniture only. A failed section/material-table parse may report zero counted slots, so a high textured-slot ratio alone is not a clean bill of health. Room wallpaper/floor texture overrides can supersede native placeholders; raw decode coverage is not effective shader coverage.

Resolve missing native package references before changing parsers or selecting a different fixture. House meshes may depend on shared `HouseAssets/Materials/` and textures in other size folders; see [source preparation](../../docs/bootstrap.md). A file that exists but uses a master water/glass shader is a different issue from a missing Base texture: a static albedo or thumbnail is not a substitute for transparency, refraction, flow, or reflections. Regression `tests/test_highland_roof.py` checks all five real Highland Wood roof slots when that local mesh is available; it skips when proprietary source data is absent.

## Bounded patches and visual review (advanced)

Generate diagnostics with `--artifacts` first. Older file-based review tools may require unprefixed `manifest.json`/`layout.json` in a separate diagnostic directory. Do not run manifest-dependent legacy tools on ordinary MCP PNGs.

`--patch` reads changes bound to the source hash: at most 10 items, 2m movement per edit, and yaw increments within ±180°. It edits existing instances only, without changing IDs or item count. These are bounded edits and geometry checks, not design-quality scores.

`scripts/iterate_render.py` and `scripts/refine_design.py` are optional model workflows. Check actual endpoints/models and whether execution performs inference or incurs charges. Ordinary MCP/CLI rendering does not require them. A model suggestion or successful response is not visual acceptance.

## Remaining limitations

- Base/Tint, alpha clipping, and approximate ambient lighting do not reproduce complete parent-material graphs.
- Material effects now covered approximately: slots bound directly to `M_MasterGlass`/`M_Rain` draw as a pale translucent pane in a blended pass (colour only; the ID/depth buffers keep what is behind; no refraction or reflection). `M_MasterEmissive*` slots carry their own emissive colour (whole-slot masters at full strength, masked variants at 0.6 because the mask channel is not decoded), so a lamp's bulb/shade glows and its body does not; objects without an emissive slot keep the name-based glow. `M_MasterOpacityMaskTwoSided` and `M_FoliageVertexColor` are alpha-cut like other foliage. Tint-family MIs that omit `Tint` use the master's default, decoded from the extracted master material (`Content/Materials/M_MasterTint*.uasset`, `DT_MasterMats/M_bgColorChange`; extract them with `retoc to-legacy --filter /Materials/<name>`). An MI whose property layout is unsupported falls back to its single `_d` texture import, with a `guessed` warning. Phasmascapes show their scene layer statically (no scroll/overlay).
- Still missing: water/particles, masked-emissive masks, reflections, and game sunlight/shadows (ReMakePlace is the reference for lighting).
- Wallpaper/ceiling/basement application has gaps for some house types. Check each house/style rather than assuming uniform support.
- Native local transforms, geometry projections, and support/circulation diagnostics do not verify app import, character collision, sitting, floating persistence after re-entry, or plot world coordinates.
- User app screenshots are ground truth for a particular design. Old prototype test counts/timings are not current performance guarantees.

Rendering must not overwrite original assets, app Saves, or production databases. Do not distribute databases, extracted assets, or local outputs with source releases; see the [policy](../../docs/distribution.md).
