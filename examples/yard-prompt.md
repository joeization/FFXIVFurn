# Yard Adaptation Brief — Sunset Woodland Retreat

This is a summary of the yard extension's design requirements and subsequent human feedback, not a verbatim transcript of a single prompt. The original interior brief is [prompt.md](prompt.md).

## Design objective

Extend the Small-house interior's warm, rustic woodland-cottage atmosphere into a usable residential garden. Retain natural wood, stone, layered greenery and quiet seating without copying another design.

## Constraints and refinement requirements

- Use no more than **20 outdoor furnishing instances**, following the maintainer's current Taiwan-server limit. The final simplification must use only a subset of the existing furnishings, with no new types or extra copies.
- Retain the private Miniature Aetheryte and a usable gate-to-door route.
- Keep the tea seating, garden bench and well accessible. Do not put firewood across the well's approach or seating on entrance circulation.
- Keep low lamps and tree branches away from junctions and passages; use tall edge lighting where appropriate.
- Treat the gate, straight fence sections and corners as one matching exterior fixture set.
- Replace the oversized curved roof with a more restrained cottage roof, checking actual textures rather than hiding render failures by switching assets.
- Preserve the original interior. Use furniture available in the local catalog and restrict it to patch <=7.2.
- Use flat plans before placement and after spatial edits, alongside full-estate, entrance/reverse and occupied eye-level views. Include the actual gate in overview framing.
- Do not append furniture inventories to the plan images.

## Process and image provenance

The yard was developed with GPT-6.1 (Sol) driving the MCP tools over multiple refinement rounds with human feedback. It follows [DESIGN_CONTEXT.md](../DESIGN_CONTEXT.md), a methodological reference rather than a description of implemented tooling.

[yard_layout.png](yard_layout.png) is a flat measured-footprint schematic of the 20-item layout, not game art or a 3D render.

[yard_gpt_edited.png](yard_gpt_edited.png) is based on the maintainer's FFXIV screenshot. **GPT was used to remove the background, but it also redrew the image.** Details may therefore differ from the original in-game screenshot. It is an edited illustration, not an unaltered game screenshot, a ReMakePlace screenshot, or native-renderer output; do not use it as exact visual validation of placement or furnishing counts.

The game-derived illustration is not covered by the repository's code/documentation MIT grant. See the [distribution policy](../docs/distribution.md).
