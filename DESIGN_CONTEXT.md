# From a brief to an editable space: a reusable design workflow

> A design method, not a project diary or furniture recipe. Start from people's activities and spatial relationships, then select furniture, resolve construction, and add detail. Technical checks provide evidence; they do not replace the model's or user's design judgment.

Use this for FFXIV interiors, yards, and coordinated indoor/outdoor projects: homes, venues, gardens, displays, role-play sets, and other briefs. It is a **methodological reference, not implemented tooling**: MCP and the renderer do not implement every representation, check, or technique described here. The method is reusable; one project's program, preferences, and construction choices are not defaults for the next.

Sources: Studio Matrx's brief-to-presentation course structure[1], Make it Home's ergonomic and relational representations[2], Holodeck's semantic decomposition and relational placement[3], Architect-Ant's editable representations and separate acceptance checks[4], SceneCritic's traceable object/relationship diagnostics[11], AesthetiQ's relative comparison of rendered outputs (a 2D-layout study, adapted with limits)[12], GenRoom's modern-interior style guide as a style vocabulary example[13], and HGXIV's in-game construction techniques[10]. Section 12 states what each source does and does not support.

## Scope and adaptation

### Four kinds of information

| Kind | How to use it |
|---|---|
| Verified conditions and binding requirements | Current geometry, asset eligibility, authorized budget, required interactions, explicit user constraints. Record source and scope; expose conflicts instead of pretending an impossible request passed. |
| Project choices and preferences | Activities, mood, style, openness, privacy, density, symmetry, floor use, inventory policy. Establish them for this brief; do not inherit them from an earlier project. |
| Conditional heuristics and techniques | Backed seating, axial views, enclosed rooms, layered planting, custom ceilings, zoning cues, style rules of thumb. State what problem each solves, its cost, and when it does not apply. |
| Evidence and uncertainty | What a measurement, image, export, or app test actually establishes. Unknown is neither pass nor fail; a preference is not a measurement. |

Examples explain possible solutions, not extra requirements. Nothing here requires a bedroom, kitchen, counter, greenery, scenic window, concealed stairs, central aisle, particular style, maximum density, or furnishing every floor. Apply a technique only when the current brief gives it a role.

For each requirement or check, record separately: obligation (**required / preferred / optional**), applicability (**applies / not applicable, with reason**), and evidence status. An applicable but untested check stays **unverified**; it cannot be relabeled not applicable to make delivery look complete.

### Scope, purpose, and change mode

| Decision | Adaptation |
|---|---|
| Interior | Survey floors in scope, openings, stairs, ceilings/beams, and cross-floor bodies. Re-read affected geometry after a style change. |
| Yard | Survey plot, gate/approaches, house envelope, exterior fixtures, terrain, perimeter, canopy heights, and relevant neighboring views. A yard is not assumed to be a cottage garden. |
| Coordinated indoor/outdoor | State which scopes may change and which relationships cross the boundary. Track budgets separately; preserve out-of-scope payloads. |
| New design | Fresh brief and concept within the chosen shell; do not reskin another project by default. |
| Revision or constrained reuse | Start from the authorized saved revision. Identify approved elements, allowed edits, inventory, and invariants; do not clear the scene by default. |
| Assessment or proposal only | Diagnose without changing live state. A suggested edit, an exported proposal, and permission to apply it are different things; finding a defect is not authorization to fix it. |
| Venue, home, display, or set | Derive requirements from actual use. A display may prioritize viewing and empty space; a set may prioritize camera positions. Required interactions and claimed walkable areas still need verification. |

These combine (a yard can be a venue; an interior task can be a small revision). A staged delivery names finished and unfinished areas.

### Decision boundaries

- **Policy:** confirm housing/plot type, placement areas, scope, region/client/patch availability, and furnishing/interaction limits, with the policy source. Historical guides, tool defaults, and other regions' capacities are not authorization. Do not move unused capacity between scopes unless the rules allow it.
- **Inventory:** establish whether assets may be bought, substituted, duplicated, or only rearranged. A no-new-items revision preserves an authorized subset of existing instances, not just the same type names. Count concealed/composite pieces in slots; keep fixture rules separate from furnishing counts; track slots, procurement, storage, special interaction limits, and temporary construction tools separately.
- **Protection and authority:** record protected geometry, functions, approved compositions, and unrelated payloads. Establish whether the app save, export, or MCP snapshot is authoritative; timestamps or filenames do not settle conflicts.
- **Function versus appearance:** a piece may only suggest a function; a required seat, door, or teleport needs an actual test. Declare intentionally nonfunctional or inaccessible areas.
- **Proportional effort:** a lamp adjustment needs no new concept; a new organization needs more than moving props.
- **Stay within authorization:** disclose incomplete evidence and use other valid evidence where available. Repairing the renderer, buying assets, changing fixtures, or applying a redesign needs the corresponding task scope.

## Overall sequence

```text
Users, activities, success criteria (program)
  → Actual site/shell, fixed conditions, tool boundaries
  → Organizing concept that changes decisions (parti), then style vocabulary
  → Zones, adjacency, routes (bubble diagram)
  → Distinct spatial frameworks (block plan)
  → Real furniture, activity areas, support relationships (furniture plan)
  → Plan, vertical relationships, boundaries, light together
  → Required uses and experience, then supporting detail
  → Separate diagnosis, inspect actual images, revise the right layer
  → Validate in the target app; deliver an editable design
```

This loop converges iteratively. New furniture dimensions may force rezoning; a sightline problem may need a ceiling change; feedback may overturn the concept. Moving a cup does not require rebuilding the house, and structural or functional failures are not fixed by adding cups.[5][7]

### Keep a flat plan in the loop

Before placing furniture, generate a measured flat plan of the empty or current authorized site, then overlay intended zones, approaches, entrance-to-destination routes, and any required viewing positions. Do not invent service lanes or activities the brief does not need. After each spatial edit batch, regenerate and compare with the previous revision; use plans to catch junction, operating-front, approach, arrival, and path-side problems early. Planning and final images omit furniture inventories unless requested; implementation records still keep instance IDs and budget evidence.

Pair plans with an overview and relevant eye-level or camera views: canopies, fixture heights, occlusion, and materials cannot be judged from footprints. Cover the whole scope, including actual arrivals (for yards: gate, perimeter, inward and reverse entrance views where access matters). Check required use faces and routes against complete object bodies, not pivots. Treat coupled fixture sets (gate, straight, and corner fences) together, and distinguish a verified game/tool coupling from an aesthetic preference. Intentional embedding and planting overlap remain legal.

## 1. Turn a theme into a use and experience brief

"Cafe," "conservatory," or "sculpture garden" names a type. Identify who does what, when, with whom, and which activities conflict before deciding form. Viewing, photography, role-play, contemplation, and deliberate emptiness are legitimate purposes; a themed scene need not simulate a household.[5]

| Item | Questions |
|---|---|
| Users and activities | Who (visitors, characters, cameras) does what? How do they enter, stay, use or view, and leave? |
| Essential / supporting / atmospheric | What is indispensable, what supports it, what can be reduced? |
| Simultaneous use | Do staff, waiting guests, chair pull-out, and passersby occupy the same area at once? |
| Success criteria | From which positions and scenarios will requirements be checked? |
| Boundaries | Scope, change mode, floors/areas, region/patch, budgets, inventory, protected elements, exclusions, assumptions. |

Translate adjectives into observable conditions for this project ("intimate" might mean screened seating; "ceremonial" a strong axis; "modern" might mean clean silhouettes and uncluttered surfaces), not universal counts. Record priorities and tradeoffs. Ask only when the answer materially changes the design; otherwise record a revisable assumption.

**Example:** "Quick ordering, two-person conversation, and long reading; service routes must not cross quiet seating." This guides tradeoffs better than "a white-and-wood cafe."

## 2. Understand the site/shell before selecting furniture

Obtain actual dimensions and fixed conditions. Interiors: wall thickness, floor heights, columns/beams, doors/windows/sills, floor openings, stairs, arrivals. Yards: plot/terrain, house envelope, actual gate, exterior fixtures, required approaches. Classify each as immutable, replaceable, coverable, or unverified. Do not invent real-world constraints (plumbing, wiring) that FFXIV lacks.[5]

- Stair entrance, stair body, final step, and arrival area are separate objects. The stairs' XY projection is not automatically excluded; check headroom, access, and placeability.
- Interior styles of the same house type can differ completely: some enclose everything under the stairs, others leave it open. Re-read arrivals, usable floor, and enclosed regions from native meshes **in the same session, after selecting the style**; never copy coordinates from another style or session.
- Read native openings and fixtures first; distinguish fixed transforms from supported style replacements. Holodeck's freely generated shells do not apply.[3]
- Confirm MCP house type, seed, revision, furniture policy, and renderer gaps. Check image completeness (entrance, stairs, fixtures, scenic textures; no other floors or ceilings mixed into a plan) before judging. An apparent problem may be a rendering error; do not redesign to hide it. Fix the renderer only if authorized; otherwise use other evidence or leave the judgment open.
- Closing off a floor is a brief-specific choice. Every floor in use must remain reachable.

**Keep:** shell notes, fixed and editable elements, required circulation, measurement sources, uncertainties. Pixel placement without coordinate evidence is not measurement.

## 3. Use a concept for decisions and style for expression

A parti is an organizing strategy that changes zoning, sections, light, and materials; "minimal," "woodland," or "modern" are vocabularies. If removing the concept changes no decision, it is a label.[8] Example: "a progression from brief social stops to quiet reading" puts service near the front, keeps queues out of the transition, and gives the reading end a calm background with local light.

Record a short concept, the decisions it changes, and a hierarchy of materials, brightness, silhouettes, and decoration (no fixed color count). Keep an atmosphere board separate from a real asset board that checks availability, dyeable regions, undersides/backs, and preview support.[8]

| Intended feeling | Spatial choices to consider |
|---|---|
| Quiet | Fewer routes through activity areas; backing or moderate screening; separate long and short stays |
| Lightness | Continuous but unsealed boundaries, permeable sightlines, lower foregrounds, clear background hierarchy |
| Warmth | Material/color differences, task light, layers of occupation, not just warm bulbs |
| Reading | Desk, seat, book access, and light working together, not just bookcases |

State whether a distinctive piece is foreground or background. Do not give every zone its own unrelated ornament set.

### Reference: style guides as vocabulary

When the brief names a style, a style guide can supply vocabulary and starting heuristics. It does not replace the brief, and its rules are real-world conventions, not FFXIV requirements. GenRoom's modern-interior guide is one example; its main ideas, read as options:[13]

| Idea in the guide | Possible FFXIV reading |
|---|---|
| Clean lines and geometric silhouettes; proportion and repetition instead of ornament | Prefer assets with simple silhouettes; let rhythm come from spacing and alignment |
| Negative space as a design element; uncluttered surfaces | Consistent with Section 4.3: emptiness can be purposeful |
| Light treated as a material | Native windows and light placement as primary decisions (11.5, 11.7) |
| Form follows function; every object earns its place | Section 8's role-based completeness; decoration should have a reason |
| Neutral base with a few deliberate accents | A material/color hierarchy for the concept; the guide's 60-30-10 split is a rule of thumb, not a target |
| Shared materials across an open plan; consistent ceiling language | Continuity between zones (4.4) |
| "Edit": step back and remove a few things | One option when a result reads crowded (9.3) |

Its distinction between *modern* (a fixed historical vocabulary) and *contemporary* (whatever is current) is useful when interpreting a user's word. Its numeric figures (surface-clearance percentages, objects per surface, sofa offsets, rug sizes, style-mixing ratios), product and paint lists, prices, budget tiers, and trend forecasts do not transfer; FFXIV assets and scales differ. The guide calls its principles requirements; here they remain one style's vocabulary, applied only when that style is chosen.

## 4. Arrange relationships, activity space, and routes first

### 4.1 A relationship diagram is not a miniature plan

Pick relationship axes relevant to the program (public/private, active/quiet, use/service, performer/audience, view/foreground, planted/occupied). List pairs that must adjoin, should be near, should be separated, or are unrelated. Fit the diagram into the real shell afterward.[6]

```text
Entrance → Orient/pause → Distribute
                          ├─ Order/collect/brief conversation
                          └─ Quiet reading/extended work
Service entry → Operate/restock/tidy (without crossing guests' activity core)
```

### 4.2 Furniture needs room to be used

Make it Home and Studio Matrx both treat furniture as footprint plus human activity area, with accessible sides, visible fronts, support, and pairing.[2][6]

| Layer | Check |
|---|---|
| Footprint/volume | Body, protruding bases/handles, visible and embedded parts |
| Operating area | Pulling chairs, sitting, opening doors/drawers, reaching, working |
| Routes | Entrance-to-zone routes and access to every actual use face |
| Sightlines | Where display faces, views, and cues are seen from; which obstructions are intentional |

Operating areas may overlap at different times if the scenario says so; simultaneous queuing, work, and passage cannot share space just because outlines do not intersect. Where undisturbed conversation or work matters, route around its core; promenades, exhibits, and stages may put movement at the center deliberately. Real-world dimensions are references, not FFXIV rules: check "can pass," "convenient to operate," and "feels open" separately.[6]

### 4.3 Arrival, staying, and working

Where arrivals need orientation, leave room to stand, turn, and choose before conflicting activity begins; an immediate reveal or screened transition can also be intentional. If a group blocks a route or shows an unwanted wall of seat backs, adjust position, orientation, height, or route. Wall-backed seating, floating sofas, symmetry, winding paths, and focal aisles are all options, none universal. Separate private functions by distance, screening, level, orientation, or enclosure according to the brief.

**Emptiness is neither proof of good circulation nor a missing function.** Negative space can serve orientation, gathering, performance, views, or restraint. Add a coherent arrangement only for a missing role; keep empty space that already serves the brief.

### 4.4 Reference: reading zones without full partitions

A reference lens for open or shared areas, not a procedure or required pattern. Use it when several activities share a space and the result reads as scattered; skip it otherwise. Placing each activity's furniture is not always the same as forming a recognizable place: in the schematic below, similar pieces read differently once floor extents, groups, and facing agree, without adding a wall.

```text
Furniture only (scattered)        Grouped into zones (no added partition)
+--------------------------+      +--------------------------+
|  [====]        [|]       |      | .- Living -------------. |
|                          |      | :  [sofa]      [chair] : |
|      [===]               |      | :      [low table]     : |
|                  ( )     |      | '----------.-----------' |
|  [===]                   |      |            : transition  |
|                          |      | .- Dining/kitchen -----. |
|                          |      | : [cab]  [] []         : |
|                          |      | : [cab]  [  table  ]   : |
+--------------------------+      | '----------------------' |
                                  +--------------------------+
```

One possible outcome, not a target. The left plan is not wrong by definition; a gallery, a loose arrangement, or a one-activity room may be better without zones.

| Aspect | Question to consider | Examples, not a list to apply |
|---|---|---|
| Anchor | What, if anything, gives this area its identity? | An activity, a furniture group, or a focal point such as a window, fireplace, counter, or stage |
| Boundary | What hints at where it begins and ends? | Rug extent, furniture orientation and backs, low storage, an island or counter, ceiling bay/beam, platform, lighting pool, partial screen, column pair, arch. Outdoors: paving, planting edge, pergola, level change, canopy |
| Transition | How does it relate to neighbors, visually and for movement? | A threshold, route, or shared sightline; a soft blend can be intentional |

- Cues that agree on one edge (a rug, an inward-facing group, a light above) often read more clearly than one cue alone; cues implying different edges blur a zone. Whether clarity is wanted depends on the brief.
- Shared materials, colors, proportions, or details keep zones reading as one interior (Section 3). Sources differ on how far to go: a ceiling change can mark a zone, while a modern style guide prefers one consistent ceiling across an open plan.[13] The brief and style decide.
- Full-height partitions are one option, often most useful for privacy, concealment, or a specific concept. In FFXIV they cost slots and can affect cameras, selection, and light (11.5, 11.9).
- Native interior flooring usually covers a whole floor, so a floor change typically relies on rugs or floor-surface furniture; ceilings and platforms carry the costs in 11.10 and 11.12.
- If zones are intended, plan and eye-level views show whether they are recognizable without walls.

The model and user decide whether, where, and how to zone; this supplies vocabulary, not a checklist.

**Keep:** activity/adjacency diagrams, primary/secondary routes, arrival areas, operating faces, expected sightlines. Furniture selection need not be complete yet.

## 5. Compare spatial frameworks

Fit required activity and viewing areas into the real shell to form a scaled block plan, then test real furniture. For major organizational decisions, compare meaningfully different alternatives (wall-side versus central service; reading concentrated on one floor versus distributed); two or three may suffice, and color changes are not alternatives. Local corrections do not need new alternatives.[7]

| Comparison | Question |
|---|---|
| Completeness | Does every essential activity have a place, or was openness bought by deleting functions? |
| Conflicts | Do routes cross seating, operating, or queue areas? Can people choose a direction on arrival? |
| Scale | With real dimensions, do activity areas, heights, and backgrounds still work? |
| Concept/sightlines | Do entrance and use positions support the concept, not just the overview? |
| Cost/adaptability | Are slots, masking pieces, construction difficulty, and later changes worth it? |

Small spaces can combine functions through furniture, levels, storage boundaries, vertical use, and time-sharing, without deleting functions or partitioning everything; wall-mounted pieces and continuous floor surfaces can also make a small floor read larger.[13] Transformable furniture needs its alternate states checked; do not invent mechanisms the game lacks.[7] When alternatives conflict, revisit zoning, dimensions, or content rather than contorting routes to avoid every intersection.

**Keep:** selection reasons, main problems of rejected options, pending asset-dimension checks.

## 6. Define furniture roles and relationships before binding assets

### 6.1 Search for a role, not a theme name

Name the missing role first (low background, work surface, shared focus, support, masking), then retrieve candidates by meaning, appearance, and dimensions.[3] Check Item ID, scope, region/patch eligibility, acquisition/inventory policy, real dimensions, pivot, thumbnails, both sides of the native mesh, transparent regions, dyeable areas, and support surfaces. If nothing fits, pick another authorized candidate, revisit zoning, or expose the conflict; do not silently buy, duplicate, or drop an essential function. Similar names or embeddings do not mean equivalent shape or use.

### 6.2 Keep design intent inspectable

| Record | Purpose |
|---|---|
| Object and role | Entrance cue, short-stay seat, bar work surface, screening component |
| Semantic relationship | Against, beside, aligned, facing, near/separated, with an explicit target |
| Use relationship | Which table edge a chair serves (not every chair aimed at the table center); where a cabinet opens |
| Support/dependency | Which surface holds a cup; which children move with a parent |
| Intentional overlap | Which parts embed on purpose and which faces must stay visible; not a blanket exemption |
| Uncertainty | Facing confirmed or guessed; surface sampled or assumed; effect needing the app |

This motivates records, not a claim that MCP has a scene graph or relational solver.[2][3] Build groups around anchors before dependents, preserve relative relationships when moving groups, confirm facing visually (the wall side is not always the back), and place props on native support surfaces, not base plates or narrow edges.

### 6.3 Translate semantics into coordinates carefully

Holodeck solves positions from relationships; Architect-Ant outputs coordinates after specific training. Neither proves models must avoid coordinates or that base models guess them reliably.[3][4] Here the model decides intent, facing, density, and legal combinations, then uses real geometry to make and verify MCP edits. Track asset-local, room-local, house-world, export scale, and screen mirroring; do not flip exports to match screenshots.[4]

Furniture cannot be stretched: keep unit scale; replace the asset or change zoning. Coarse rectangles are for early planning only; recheck recesses, angles, cross-floor volumes, and floating with native geometry.

**Keep:** stable instance IDs, roles/groups/dependencies, source assets, positions/facing/heights, reversible operations. Test one representative unit before repeating it; repetition is valid when the program calls for rhythm or order.

## 7. Resolve plan, vertical relationships, boundaries, and light together

Fitting footprints does not make a three-dimensional space. Elevations resolve openings, cabinetry, and backgrounds; sections resolve headroom, levels, sightlines, and hidden volumes. Indoors, coordinate ceilings with zoning, beams, and lighting.[8] Outdoors, coordinate the house envelope, perimeter, planting/canopy layers, open sky, and foreground; no ceiling is not a missing component. Check only constructions the design uses.

- **Plan:** activity and circulation relationships, not just boxes.
- **Vertical:** do heights, overhead elements, and layers support scale and sightlines? Low and open can be deliberate.
- **Zone boundaries (if zoning is intended):** overhead, floor, and lighting cues that agree tend to read more clearly (4.4).
- **Backs:** do cabinet backs, false walls, and scenic surfaces look constructed from other zones?
- **Junctions:** walls, beams, cabinets, frames, and openings need plausible ends, seams, grain directions, and thicknesses.
- **Hidden volumes:** embedded or cross-floor bodies must not intrude elsewhere; legal overlaps still need finished faces.

Ceilings affect headroom, native pendants, hidden lights, and cameras; lowering one may define a zone or feel oppressive. Test a representative component (front/back material, dye coverage) before extending it.[8][10]

### Conditional technique: scenic surfaces in constructed openings

When a scenic surface should read as a window or skylight, build the opening first, then recess the scene behind it:

1. Define the visible opening (false wall with doorway, arch, or window grid in front of the original wall); recess the scene and conceal thick edges.
2. Optionally add a sill or railing and side lights/plants for foreground, middle, and distance.
3. For skylights, embed the panel in the native ceiling's beam/bay order where possible; an independent structure needs its own resolved junctions, not arbitrary support pillars.
4. Check entrance, close, and upward views. If it still reads as a flat panel, add depth (recession, side returns, subdivisions), not decoration.

A scene pasted on a wall or raised and dyed to match can still read as a hanging box.[10] A deliberately freestanding screen or framed exhibit has a different intent.

**Keep:** coarse placement, key elevation/section relationships, representative eye-level views, unresolved junctions.

## 8. Complete required uses before finishing detail

Walk each zone's scenario: where people arrive, stand or sit, face, reach, and leave, and what happens when others pass. Check essential, supporting, and atmospheric objects separately. More pieces do not mean completeness.

| Zone | Check more than presence |
|---|---|
| Reading/work | Accessible seat, usable surface, book/object access, light; decor does not fill the desk |
| Service/bar | Separate guest and work faces, restocking, collection/waiting, staff access |
| Rest/conversation | Shared focus, conversational distance, seat orientation, backing |
| Display | Clear fronts and view cones, room to pause, unblocked circulation |
| Storage/doors | Accessible faces, opening and retrieval space |
| Yard | Gate-to-destination access, usable outdoor groups, plant/equipment access if requested, canopy/view relationships, fixture continuity |
| Stage/set | Intended camera cones, performer/audience positions if required, depth, declared off-camera areas |

Choose lighting roles from the brief (orientation, task, accent, uniform display light, darkness, silhouette, contrast); not every project needs every layer. Distinguish visible fixtures from actual sources. Dark scenes still need required passage and interactions tested. The renderer cannot verify real sunlight, shadows, or reflections.[8][10]

Planting needs a spatial role, props need support, work surfaces keep their working space. Bare backgrounds, open sky, and empty surfaces can be complete choices.

**Keep:** per-zone status of essential functions, and symbolic use versus tested interaction (a decorative coffee machine expresses service; sitting and door use need tests).

## 9. Verify by layer, diagnose causes, revise the right level

### 9.1 Separate technical, activity, and visual checks

| Layer | Checks | Cannot establish |
|---|---|---|
| Technical/geometry | Identity, scope, patch, budget, transforms, support, unintended collisions, openings, connectivity, use faces | Good design; render meshes equal game collision |
| Activity/usability | Essential functions, pairings, access, simultaneous use, cross-zone conflicts | That complete lists mean real usability; that unseen means absent |
| Spatial/visual | Concept, layers, hierarchy, rhythm, third dimension, arrival, junctions | Eye-level comfort from a nice top view; a bad plan excused by lighting |

Use **separate reasons and evidence**, not quality scores or pass thresholds. Architect-Ant's LRS (starts at 10, deducts, can go negative) covers only encoded rules; 10 is not an ideal layout.[4] State conditions for every numeric check: body or activity area, width/height range, excluded objects, whether native stairs count, bounding boxes or exact projections. A few routes do not establish whole-house usability. Research proxies such as Architect-Ant's narrow-passage test are not comfort, building codes, or FFXIV character tests; AABB intersection is preliminary screening, and there is no blanket overlap ban.[2][4]

**Object-level diagnostics (adapted from SceneCritic).** SceneCritic reports per-object/relationship successes and violations for scale, co-occurrence, support, facing, and overlap.[11] Borrow the format, not the gates: for each issue record stable IDs, roles/relationships, obligation and applicability, evidence, known versus inferred, and whether a revision resolves, keeps, or introduces it. Unknown facing or category does not pass by default.

- Dataset priors (back-to-wall, face-room-center, co-occurrence) are not FFXIV requirements and do not justify adding or scaling furniture.
- Check names overstate precision: its True Overlap uses 2D OBBs, not mesh collision, and its orientation check passes if any subcheck passes.[11] Keep individual evidence rather than one total.
- VLM scores are unstable across views, yet image feedback still helps find semantic and facing errors.[11] Use geometry for known facts and multiple views plus judgment for composition; do not rotate furniture blindly on one complaint.
- Compare before/after diagnostics for the same IDs; one fix must not break support, seats, openings, or routes.

### 9.2 Choose views for the question

| View | Inspect |
|---|---|
| Overview/diagnostic plan per area | Zones, density, routes, required functions or views, purposeful versus unexplained emptiness |
| Entrance eye level and reverse | First impression, turning, door use, pressure from tall objects (a threshold camera cannot see its own door; pair it with a reverse view and plan) |
| Seated/operating/viewing positions | Tables/chairs, work surfaces, backing, visible content |
| Stair arrival and after turning | Transition from walking to staying or choosing |
| Upward, elevations, boundaries | Skylight frames, beam/wall junctions, cabinet backs, cross-floor intrusion |
| Yard perimeter, gate, house-facing | Entry alignment, fixture continuity, canopy occlusion, outdoor use faces |
| Specified stage/display cameras plus off-axis | Intended composition, viewing access, declared camera-only illusions |

Use only applicable views. Eye-level interior views keep the real ceiling; top-view clipping is diagnostic and labeled. After structural edits, check cameras are not inside walls. Mirrored display does not change house coordinates. A camera-dependent illusion can be reviewed from its position, but one view does not verify other angles. Provide access to faces the use requires, not every side of every object; if an approach defeats the use, reorganize rather than nudging coordinates.

### 9.3 Turn feedback into revision hypotheses

| Feedback | Diagnose first | Revision level |
|---|---|---|
| Too empty | Missing function, layer, or focus, or intentional sparseness? | Add coherent groups only for missing roles, or keep the emptiness |
| Too crowded | Activity conflicts, ill-fitting assets, blocked views, unintended enclosure, unedited accumulation? | Reorganize, replace within policy, or remove lower-priority content; never stretch furniture or drop essentials |
| Messy/monotonous | Too many focal pieces, fragmentation, clashing materials, rhythmless repetition? | Groups, backgrounds, distinct uses, material hierarchy |
| Scattered/zones unclear | Were distinct areas intended? If so, pieces placed individually, or cues disagreeing? | Possibly regroup or adjust cues (4.4); props or partitions are not the only option |
| Fake | Unsupported objects, wrong facing, surface-only construction, exposed frames, render distortion? | Geometry, use relationships, construction, or tool verification |
| Pasted on | Unintended frames, seams, supports, or meant as a freestanding exhibit? | Resolve boundary, depth, junctions; recess only for an architectural illusion |
| Passable but inconvenient | Detours, chair pull-out intrusion, arrival into work faces? | Reorganize groups/routes instead of snaking around furniture |

Decide whether organization or fine adjustment is needed instead of endlessly nudging.[2] Record issue, hypothesis, expected improvement, evidence, and keep/revert. A successful operation does not justify a failed design.

### 9.4 Comparison discipline

For layout comparisons, hold shell, cameras, and evaluation conditions fixed; if assets or lights also differ, call it a comparison of whole proposals. Anonymous A/B and reversed order reduce bias; "no clear preference" and "insufficient evidence" are valid outcomes. No extra paid model calls are required.[3][4] Rate applicable use checks as **usable / problematic / unidentified / insufficient evidence**, mark excluded checks not applicable with a reason, and track visual preference separately. Do not guess dimensions or hidden equipment from images. Architect-Ant limits its visual evaluation to automated image preference, not geometric validity.[4]

### 9.5 Relative aesthetic comparison (limited AesthetiQ adaptation)

AesthetiQ trains on relative preferences between rendered 2D graphic layouts rather than one reference answer or absolute scores.[12] Borrow only the comparison habit: under the same requirements and comparable views, ask which candidate better expresses the concept, has clearer focus and groups, coherent proportions and materials, and purposeful negative space. These 3D criteria are this workflow's adaptation.

1. List technical issues first; an attractive image does not excuse a blocked door or failed support.
2. Compare real furniture and finished faces, not boxes. Deviation from a reference is not an error.
3. State differences in views, exposure, or assets; do not cherry-pick; give reasons, not invented percentages.
4. 2D alignment/low-overlap heuristics do not ban 3D overlap.
5. Its judge results do not establish this user's taste or 3D comfort; adding the reference does not launch training or paid judging.[12]

## 10. Validate and deliver an editable design

Completion does not mean using every slot. Delivery explains the problem, concept, plan and vertical solution, and remaining evidence gaps.[9]

**Design works**

- [ ] Every required use has an arrangement; no unrequested functions added by default, no essential ones silently dropped.
- [ ] Required arrivals, routes, use/viewing positions, and departures work; deliberately shared areas are justified and tested.
- [ ] The concept changes decisions; groups share a language while serving distinct uses.
- [ ] Applicable plan, vertical, boundary, lighting, and detail relationships support the concept; junctions are resolved.
- [ ] Negative space has a purpose; dense areas keep operating space.

**Implementation is trustworthy**

- [ ] MCP state matches the export item by item: identity, scope, patch eligibility, inventory policy, unit scale, finite transforms, separate budgets.
- [ ] Activity areas, support, and facing rechecked after binding real assets.
- [ ] Snapshots and stable IDs preserved; revision-guarded atomic batches; after a timeout, read back before replaying.
- [ ] Preview limits, intentional overlaps/floating, and untested items listed; protected elements and out-of-scope payloads match the baseline.
- [ ] Required doors, characters/cameras, stairs, sitting/teleport interactions, floating persistence after re-entry, and lighting tested in the target app where applicable. Untested is not passed.

**Delivery supports continuation**

Keep a concise brief, tradeoffs, editable groups and dependencies, dimension/facing evidence, representative plans and views, construction notes, and material references in one working note. Label each image's purpose, clipping, orientation, and provenance: native renderer previews, flat schematics, in-game screenshots, and AI-edited illustrations are different things, and a redrawn image is not placement evidence.[9] List technical evidence separately (schema validity, mesh/material visibility, geometry tests, app tests). Updating this method does not make old layouts pass new checks.

## 11. HGXIV construction techniques (optional library)

Useful content from the HGXIV guide[10], organized by problem. Choose purpose first, then technique, then assess construction, slots, and verifiability. These are not tool APIs. Concealment instructions apply only when that illusion is the goal; hidden bodies still must not affect other usable areas.

### 11.1 Operations, previews, storage, materials
- Moving, rotating, returning to inventory, and storing differ; paintings, aquariums, wallpaper, and consumables can have extra retrieval rules. Back up risky changes; removal is not assumed lossless.
- In-game previews may not cover cash-shop/event items or interior materials; cross-check thumbnails, native meshes, and previews.
- Storage placement bypasses some snapping/boundary limits, not all. Orange center points, pivots, and geometry centers can differ.
- Slots, storage capacity, and special interactive limits are separate budgets; hidden lights and masking pieces cost slots. Use current policy, not historical guide capacities.

### 11.2 Grid snap, alignment, construction identification
- Grids standardize lines, beam spacing, and openings; fine offsets handle seams and z-fighting. Game grids are not MCP world coordinates.
- Coplanar overlap z-fights; large offsets create steps. Check gaps, texture direction, and faces from normal views.
- Temporarily dye complex groups distinct colors; preserve snapshots so cleared construction space does not save displaced furniture.

### 11.3 Floating tabletop/wall items versus lifting floor furniture
- These are different paths. Riviera Wall Shelf, Wooden Loft, Stage Panel, and Wooden Beam are tools, not necessarily final components.
- Disabling surface snap detaches tabletop items; false walls/beams can carry wall items; Stage Panel and some cabinet backs snap differently.
- Floor furniture has item-specific lift increments and minimum heights; guide "Loft units" are not meters. MCP coordinates do not guarantee persistence after re-entry.
- Floating still needs intelligible support; confirm support surfaces by mesh sampling and images.

### 11.4 Hangers, cross-floor work, under-stair construction
- Wooden Beam hangers move wall/tabletop items up or down to expose a part as a handle, frame, or trim; not every item sinks the same way.
- World Markers, window bottoms, or Mounted Box Shelf can align across floors; /doze and first-person views inspect gaps in-game.
- Record hidden bodies and check intrusion into other floors. A geometric gap is not verified usable space; small and medium under-stair spaces differ.
- In MCP, build with explicit coordinates, dependency groups, and versioned ops; verify import and re-entry separately.

### 11.5 Lighting: visible fixtures versus actual sources
- Set base brightness, then task, accent, and hidden fill. Custom ceilings can block native pendants.
- Hidden sources go above ceilings, in corners, or behind scenery; visible fixtures serve use and composition. Uniform light, deep shadow, or silhouette may be intended.
- Surface lightness, reflectance, and source placement shape atmosphere together.
- Candidates to test (not fixed rules; recheck availability): Metal Work Lantern for white fill, Alchemical Lantern/Assorted Candles for warmth, Queen's Rest for strong spot light. Custom pendants from candle holders/lanterns; partly embedded Factory Wall Lamp; Hingan Chochin Lantern for slit light.

### 11.6 Dynamic light, shadow, water light, platform limits
- Starry-sky illusions combine dark backgrounds, moon surfaces/small lights, and flicker with matching window day/night settings; contradictions can be deliberate in surreal briefs.
- Shadow windows need occluders, backgrounds, and hidden sources; water light depends on source, time, Glare, and platform settings.
- The renderer lacks real shadows, reflections, GI, and full emissive/animated materials; verify those in-game.

### 11.7 Native windows, sunlight, custom windows
- Check native openings and replaceable styles before imitation windows. Time, direction, and face orientation affect bright surfaces and rays; some stained glass changes by day/night.
- Reversing a window may remove shutters but change snapping, selection, or sunlight; conceal frames by construction, not by rotating until the renderer looks flat.
- Bay/bow windows: upper frame, then openings, side frames, lower edges, with recession depth and side returns.
- Cabinets, bookcases, or partitions can frame openings; check exposed backs from the sides.

### 11.8 Special window scenes and Phasmascapes
- Rain: recessed frame, dark background, hidden shower streams (conceal heads and splashes). Dark windows: colored backing, glass, aquarium glow. Sea: separate sky, water, shore.
- **A Phasmascape is a thick, curved scenic surface with lips, not a ready-made window.** Define the opening first, hide its edges with frames/walls/ceilings, and check every viewing angle.
- Glass grids over curved Phasmascapes need angle testing. Phasmascapes affect collision and selection; visual transparency is not click-through.
- Views must suit the floor and theme; inspect the actual scenic material, not just the frame. A missing scene image is not a finished view.

### 11.9 Entrances, false doors, selection, cameras
- Keep orientation, turning, and controller space at doors; do not require clicking through a narrow slit.
- Distinguish working doors from false ones; Stage Panel, full partitions, and Phasmascapes are not click-through.
- **Visual transparency, character passage, selection, and camera passage are four separate questions.** Do not infer them from one flattened table.
- Custom walls/ceilings may not block cameras; the hidden-bed camera trick is not a universal patch (check need, slots, intrusion, current behavior).

### 11.10 Ceilings, beams, coffers, skylights
- Undersides of Flooring Mat, Combed Wool Rug, some tiles, and tables can form ceilings. **Dyeable does not mean the underside dyes**; white dye may leave wood grain, so choose another component for smooth light ceilings. Keep heights and grain consistent.
- Coffers use regular recesses and beam lines; tray ceilings raise one center. Join beams to walls, columns, or moldings; adjust edge bays without random height changes.
- White Rectangular Partition, wooden/factory beams, and embedded furniture undersides work as components; large pieces save slots but may intrude on other floors.
- **Build the continuous ceiling before framing skylights,** and integrate them with a zone or the whole ceiling order. Reserve space for pendants, hidden fill, and cameras; inspect from entrances, seats, and upward.

### 11.11 Walls, color, composite components
- Light/cool surfaces often feel open, dark ceilings lower, dark back walls contain large rooms: testable hypotheses, not formulas.
- Neutral interiors still need focus and texture; an accent can be a window seat, fireplace group, storage wall, or textured surface rather than a bright plane.
- Wainscoting, shiplap, and panel grids can come from cabinet backs, Wooden Slat Partition, or furniture fragments; the guide also uses Cheese Collection, Disordered Wardrobe, bookcase backs, and racks. Inspect faces, thickness, dye coverage, and hidden bodies before copying.
- Overlap is legal but needs finished fronts, sides, and backs.

### 11.12 False floors, platforms, stair arrivals
- Platforms can separate activities and add layers; check the hardest item to float, headroom, edge perception, and access first. Smooth dyeable pieces such as Hingan Bookshelf work well.
- Landings must allow standing, turning, distribution, and door use; the final step should not lead straight into a door, stool, or queue.
- Intermediate landings and material changes keep stairs from reading as a solid wall; curved stairs and false treads still need clearance and camera tests.

### 11.13 Mannequins, special displays, personal detail
- Mannequins carry equipment, poses, race-dependent scale, and names; check count limits and whether tools preserve those fields.
- When a display should hide its mannequin, conceal bodies, hair, and names; a visible posed mannequin can be intentional.
- Props can describe habits; do not present invented models or composites as completion evidence.

### 11.14 Turning techniques into testable proposals
1. Identify the missing spatial role, then the technique; record display faces, hidden volumes, references, and dependencies.
2. Test one representative composition (faces, seams, scene, light) before extending.
3. Work shell-to-props, high-to-low; keep snapshots, full slot costs, and cross-floor impacts; never replay committed batches.
4. Verify appearance, passage, arrival, doors, cameras, support, and re-entry separately.
5. List shadows, sunlight, dynamics, water light, floating persistence, and selection as pending app tests.
6. Report lessons applied and behavior still unverified, not technique lists or counts.

**Source:** [HGXIV Housing Glitch Guide / How-to Design Guide](https://docs.google.com/document/d/1zYM0oTl-skbdc7xL7mNsFPE18SwGciicdV7Jtkm2i6A), contributors including Ashen Bride, Synt Slap, Dividus Yliaster, and the HGXIV community. Summarized and adapted, not translated; it includes historical capacities and 6.58/7.0 collision tables that may change. Current budgets, database identities, native geometry, and app tests take precedence.

## 12. How sources are used and where they stop

Using design knowledge here does not mean downloading models, training, or implementing a new solver.

| Source (scope read) | Incorporated | Not transferred |
|---|---|---|
| Studio Matrx: overview and five units | Brief, fixed/editable shell, concept versus style, bubble → block → furniture plans, alternatives, elevations/sections/ceilings, presentation.[1][5][7] | Indian regulations and teaching dimensions; multifunctional furniture without real mechanisms.[6][8][9] |
| Make it Home, §3–4, §7 | Use/visible faces, support hierarchy, paired distance/facing, wall relationships, paths, local/global revisions.[2] | Approximate view cones and support levels are not native collision; lighting, acoustics, style not solved.[2] |
| Holodeck, §3, §4.3 | Modular thinking, dimension-aware retrieval, anchors and relational constraints, candidate proposals.[3] | Generated shells, blanket overlap bans, its DFS solver; no automatic solver is gained here.[3] |
| Architect-Ant, §3, App. C, E–H | Editable object representation, structured input, separate geometric/functional diagnostics, 2D-to-3D rechecks, visual-evaluation discipline.[4] | SFT/GRPO results, its DSL limits (no height, yaw, or relations), LRS rankings and thresholds.[4] |
| SceneCritic, §3–4, §6–7, App. B | Object/relationship diagnostics, applicability, geometry/view division of labor, revision traces, side-effect checks.[11] | Dataset priors, thresholds, totals, any-pass; OBB overlap is not mesh collision.[11] |
| AesthetiQ, §3–5 | Relative preferences over actual outputs with reasons; separating validity, usability, composition.[12] | 2D-only results, AAPA training, overlap screening, mIoU, judge win rates; no judge model added.[12] |
| GenRoom modern-interior guide (whole article) | One style's vocabulary: clean lines, purposeful negative space, light as material, form follows function, neutral-plus-accent hierarchy, open-plan continuity, editing; modern versus contemporary.[13] | A commercial blog for real homes, not research. Its "requirements," numeric rules (60-30-10, clearance percentages, object counts, offsets, rug sizes, mixing ratios), products, paints, prices, budgets, and trends. It does not make "modern" a default style.[13] |
| HGXIV Guide (Section 11) | In-game construction techniques.[10] | Historical capacities and version/platform behavior are not tool tests; feasible is not always worthwhile.[10] |

### Proxy metrics are not final quality

- **Priors serve the brief.** Wall-hugging furniture and center-facing seats are not natural laws; neither are a style guide's ratios.
- **Emptier is not better.** Low collision, connected routes, and full inventories answer only part of the problem.
- **An image is not validation.** Render meshes differ from evaluation geometry; check final placements against final exports.[4]
- **Research preference is not user acceptance.** The user's in-app feedback is authoritative.[4]
- **Cost is not capability.** Plan relationships fully, batch operations, and review key views together instead of a model call per item; this does not reproduce the papers' results. No training, bulk paid judging, or new systems without authorization.

## Working-notes template

A task-note format, not an MCP API. Keep only applicable fields and note why significant ones are not applicable. For small revisions, update the existing notes instead of starting a new dossier.

```markdown
# Spatial design working notes

## Scope and authority
- Scope (interior / yard / both) and purpose (home / venue / display / set / other):
- Mode: new / revision / constrained reuse / staged / assessment only:
- Authoritative baseline (app save / export / MCP snapshot), seed, revision:
- Changeable areas and fixtures; protected elements and payloads:
- Authorization: read-only / exported proposal / live edits; tool repair allowed?:
- Checks: applicable / not applicable (reason) / applicable but unverified:

## Program
- Users/characters/cameras, activities or views, duration, simultaneous use:
- Essential / supporting / atmospheric; exclusions:
- Success criteria and required evidence:
- Confirmed requirements / assumptions / open questions:
- Priorities, acceptable tradeoffs, keep/reject criteria:

## Site/shell and constraints
- House/plot type, style, region/client/patch, floors/areas in scope:
- Interior: openings, stair arrivals and under-stair areas for this style, beams, headroom, cross-floor impacts:
- Yard: plot/terrain, envelope, gate/approaches, perimeter fixtures, canopy, neighboring views:
- Render completeness and known gaps:
- Fixed / replaceable / coverable / unverified:
- Budgets (slots, interactions, procurement, storage, temporary tools) and policy source:
- Inventory rule: new types / extra copies / substitutions / existing instances only:

## Concept
- One-sentence parti and the decisions it changes:
- Style vocabulary (if any) and which of its conventions are adopted or set aside:
- Atmosphere references; available material/asset board:

## Relationships and alternatives
- Zones; must adjoin / near / separated:
- Routes, arrivals, operating/viewing positions:
- Alternatives compared, costs, selection reasons:

## Furniture worksheet
- Requirement → zone → group / instance ID → usability evidence:
- Anchors, assets/Item IDs, dimensions, pivots, facing (confidence):
- Operating areas, visible faces, target seats; support parents and dependencies:
- Intentional overlaps (purpose, finished faces, cross-floor bodies):
- World coordinates/heights, export scale, mirroring:

## Iteration
- Issue and the view/scenario showing it:
- Hypothesis; layer to revise (brief / zones / groups / construction / detail / tool):
- Expected change; relationships to preserve:
- Snapshot, expected revision, committed ops (read back after timeouts):
- Result: keep / revert / unresolved; same-ID diagnostics resolved / persistent / new:

## Acceptance
- Technical: identity, eligibility, inventory, budgets, transforms, support/collision:
- Use per zone: usable / problematic / unidentified / insufficient evidence:
- Activity: arrival, operation, simultaneous use, departure:
- Visual: concept, groups, layers, hierarchy, junctions:
- Test conditions (geometry, views, A/B fixed vs. varied):
- Aesthetic preference with reasons / no clear preference / cannot judge:

## Delivery
- Final revision and item-by-item read-back:
- Verified / unverified / needs app test:
- Finished vs. unfinished areas; declared camera-only or nonfunctional content:
- Tradeoffs, representative images, recoverable revisions, open issues:
- Model/resource use and MCP shutdown evidence where applicable:
```

**Core sequence: establish this brief's uses, boundaries, and relationships; bind real assets and resolve the three-dimensional space; let detail reinforce the whole. Verify claims with appropriate evidence, and do not turn one project's solution into the next project's rule.**

## Sources

[1] https://www.studiomatrx.org/students/interior-design-studio-2
[2] https://3dvar.com/Yu2011Make.pdf
[3] https://openaccess.thecvf.com/content/CVPR2024/papers/Yang_Holodeck_Language_Guided_Generation_of_3D_Embodied_AI_Environments_CVPR_2024_paper.pdf
[4] https://arxiv.org/pdf/2606.10953
[5] https://www.studiomatrx.org/students/interior-design-studio-2/design-process-and-brief
[6] https://www.studiomatrx.org/students/interior-design-studio-2/space-planning-fundamentals
[7] https://www.studiomatrx.org/students/interior-design-studio-2/developing-the-layout
[8] https://www.studiomatrx.org/students/interior-design-studio-2/concept-and-character
[9] https://www.studiomatrx.org/students/interior-design-studio-2/presenting-the-design
[10] https://docs.google.com/document/d/1zYM0oTl-skbdc7xL7mNsFPE18SwGciicdV7Jtkm2i6A
[11] https://arxiv.org/pdf/2604.13035 — SceneCritic: A Symbolic Evaluator for 3D Indoor Scene Synthesis
[12] https://openaccess.thecvf.com/content/CVPR2025/papers/Patnaik_AesthetiQ_Enhancing_Graphic_Layout_Design_via_Aesthetic-Aware_Preference_Alignment_of_CVPR_2025_paper.pdf — AesthetiQ: Enhancing Graphic Layout Design via Aesthetic-Aware Preference Alignment of Multi-modal Large Language Models
[13] https://genroom.io/blog/modern-interior-design-complete-guide — GenRoom, "Modern Interior Design: The Complete Guide" (commercial style guide, updated October 2026)
