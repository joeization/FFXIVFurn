# From a brief to an editable space: a reusable design workflow

> This is a design and implementation method, not a project diary or furniture recipe. Start with people's activities and spatial relationships, then select furniture, resolve construction, and add detail. Technical checks provide evidence; they do not replace the model's or user's design judgment.

Use this method for FFXIV interiors, yards, and coordinated indoor/outdoor projects: homes, public venues, gardens, displays, role-play sets, and other spatial briefs. It is a methodological reference, not a claim that MCP or the renderer implements every representation, check, or technique described here. The shared method is reusable; project programs, preferences, capacities, and construction choices are not defaults for the next design.

The workflow follows Studio Matrx's progression from brief to presentation, incorporating Make it Home's ergonomic and relational representations and Holodeck's semantic decomposition, asset selection, and relational placement into the same design steps.[1][2][3]

Architect-Ant contributes editable representations and separate acceptance checks. Its methods and limitations are noted where relevant; this does not mean the tool implements its training or scoring systems.[4]

Section 11 retains HGXIV's in-game construction techniques. Section 12 gathers source adaptations and the parts that cannot be transferred directly.[10]

SceneCritic contributes traceable object/relationship diagnostics and a division of labor between symbolic checks and image feedback.[11] AesthetiQ inspires relative aesthetic comparisons of actual rendered results. Its research concerns 2D graphic layouts, not 3D interiors; Section 9 defines the limits of this adaptation.[12]

## Scope and adaptation: establish what this project needs

Before applying a recommendation, distinguish four kinds of information:

| Kind | How to use it |
|---|---|
| Verified conditions and binding requirements | Current geometry, asset eligibility, authorized budget, required interactions, and the user's explicit constraints. Record source and scope; resolve conflicts rather than pretending an impossible request passed. |
| Project choices and preferences | Activities, mood, openness, privacy, density, symmetry, floor use, and inventory policy. Establish them for this brief; do not inherit them from an earlier cafe, home, or yard. |
| Conditional heuristics and techniques | Backing seats, axial views, enclosed rooms, layered planting, custom ceilings, or time-shared routes. State the problem they solve, their costs, and when they do not apply. |
| Evidence and uncertainty | What a measurement, image, export, or interaction test actually establishes. Unknown is not a failure or a pass; a preference is not a measurement. |

An example explains a possible solution, not an additional requirement. In particular, this method does not require a bedroom, kitchen, service counter, greenery, scenic window, private teleport furnishing, concealed stairs, straight central aisle, or maximum-density layout. Nor does it require every floor to be furnished when the authorized scope excludes it. Apply a technique only when its role follows from the current brief.

### Select the scope, purpose, and change mode separately

| Decision | Adaptation |
|---|---|
| Interior | Survey occupied floors, openings, stairs where present, ceiling/beam conditions, and cross-floor bodies. Re-read affected geometry after a style change. |
| Yard | Survey the actual plot, gate/approaches, house envelope, fixed or replaceable exterior fixtures, terrain, perimeter, relevant canopy heights, and neighboring views where they affect the composition. Check planting, access, and day/night conditions where the brief needs them; do not assume a yard is a cottage garden. |
| Coordinated indoor/outdoor | State which scopes may change and which relationships cross the boundary. Track separate furnishing budgets and preserve out-of-scope payloads. |
| New design | Establish a fresh brief and spatial concept within the chosen shell. Do not reskin another project's arrangement by default. |
| Revision or constrained reuse | Start from the authorized saved revision. Identify approved elements, allowed edits, existing inventory, and invariants before changing anything; do not clear or redesign the whole scene by default. |
| Assessment or proposal only | Inspect and diagnose without changing live state. Distinguish a suggested edit, a separately exported proposal, and permission to apply it to the working design. Finding a defect is not authorization to modify it. |
| Functional venue, home, display, or set | Derive requirements from actual use. A display may prioritize viewing and deliberate empty space; a set may prioritize specified camera positions. Neither automatically needs domestic functions, but required interactions and any claimed walkable areas still need verification. |

These decisions combine: a yard can be a public venue or a photographic set, and an interior can be a small revision rather than a new home. Mark irrelevant checks **not applicable with a reason**; keep relevant but untested checks **unverified**. A staged delivery must name the finished and unfinished areas, not imply the whole house is complete.

For each requirement or diagnostic, record obligation (**required / preferred / optional**), applicability (**applies / not applicable with reason**), and evidence status separately. A preferred aesthetic is not a mandatory technical rule; an applicable but unverified interaction cannot be relabeled not applicable to make delivery look complete.

### Set the project's decision boundaries

- Confirm housing/plot type, permitted placement areas, actual design scope, region/client/patch availability, and the applicable furnishing and interaction limits. Record the policy source; historical guides, tool defaults, and another region's capacities are not authorization for this project. Do not transfer unused capacity between placement scopes unless the applicable rules explicitly permit it.
- Establish whether assets may be purchased, substituted, duplicated, or only removed/rearranged. A no-new-items revision must preserve an authorized inventory subset, not merely reuse the same type names with extra copies. Include concealed/composite pieces in slot costs; keep structural-fixture rules distinct from furnishing counts.
- Track placement slots, procurement/currency costs, owned inventory, storage, special interaction limits, and temporary construction requirements separately where relevant. Count final concealed components in the finished layout; do not mistake a temporary lifting/support tool for a permanent design component or ignore what the construction process needs.
- Record protected geometry, functions, approved compositions, and unrelated payloads. For an existing layout, establish whether the app save, export, or MCP snapshot is authoritative; timestamps or familiar filenames alone do not settle conflicting revisions.
- Separate desired behavior from symbolic appearance: an installation may only suggest a function, whereas a required seat, door, or teleport interaction needs an actual test. State any intentionally nonfunctional or inaccessible areas instead of presenting them as usable.
- Preserve the common principles below while scaling effort to the change. A lamp adjustment does not require a new concept competition; a new organization does require more than moving props.
- Keep diagnosis within authorization. If evidence is incomplete, disclose the gap and use another valid evidence source where available. Repairing a renderer, purchasing assets, changing fixtures, or applying a proposed redesign requires the appropriate task scope; do not silently expand a critique into implementation.

## Overall sequence

```text
Users, activities, and success criteria (program)
  → Understand the actual site/shell, fixed conditions, and tool boundaries
  → Propose an organizing concept that changes decisions (parti)
  → Activity zones, adjacency, and routes (bubble diagram)
  → Compare distinct spatial frameworks (block plan)
  → Bind real furniture, activity areas, and support relationships (furniture plan)
  → Resolve plan, vertical relationships, boundaries, and light together
  → Complete the required uses and experience, then add supporting detail
  → Diagnose separately, inspect actual images, revise the appropriate layer
  → Validate in the target app and deliver an editable design
```

This is an iterative convergence process, not a one-way pipeline. New furniture dimensions may require rezoning; sightline problems may require a ceiling change; user feedback may overturn the concept. Adjusting a cup does not require rebuilding the house, but structural or functional failures cannot be solved by adding cups.[5][7]

### Keep a flat plan in the loop

Generate a measured flat plan of the empty or authorized current site/shell before placing furniture, then mark intended zones, relevant approaches, and entrance-to-destination routes on a planning overlay. Include required viewing positions for displays or sets; do not invent service lanes or domestic activities that the brief does not need. After each spatial edit batch, regenerate the plan and compare it with the previous revision before accepting the layout. Use plans to check junctions, operating fronts, seating approaches, arrival buffers, and path-side objects where applicable; do not wait until final export to discover these relationships. Planning and final images omit furniture inventories unless explicitly requested; implementation records still retain instance identities and budget evidence.

Pair spatial plan reviews with an overview and relevant occupied eye-level or intended camera views: crowns/branches, fixture heights, occlusion, and material behavior cannot be verified from footprints alone. Cover the full scope with enough views to expose its boundaries and actual arrivals; a yard review includes its gate and perimeter, with inward and reverse entrance views where access matters. When a selected fixture family is a coupled set (such as gate, straight, and corner fence components), evaluate and change the set together, not just the visible fragment. Establish whether the coupling is a verified game/tool constraint or a requirement of this brief; aesthetic matching alone does not prove technical coupling. Check every required use face and route against the complete bodies of nearby objects, not just their pivots. A light beside a path, storage beside equipment, or seating near an arrival may work in many arrangements; choose by use, height, sightlines, and the brief rather than imposing a fixed furnishing recipe. Intentional embedding and planting overlap remain legal.

## 1. Turn a theme into a use and experience brief

"Cafe," "conservatory," "modern home," and "sculpture garden" describe types only. Identify who does what, when, with whom, and which activities conflict before deciding the space's shape. Viewing, photography, role-play, contemplation, and deliberately unoccupied space can be legitimate purposes too; a themed scene need not simulate a complete household. Programming establishes requirements first; it should not begin by choosing partitions and furniture forms.[5]

### Record the brief

| Item | Questions to answer |
|---|---|
| Users and activities | Solitude, conversation, gatherings, reading, service, display, gardening, or staging? Which visitors, characters, and cameras are relevant? How do they enter, stay, use/view, and leave? |
| Essential/supporting/atmospheric | Which functions are indispensable? Which support them? Which can be reduced? |
| Simultaneous use | Will staff, waiting guests, people pulling chairs out, and passersby occupy the same area at once? |
| Success criteria | From which positions and use scenarios will requirements be verified? |
| Boundaries | Site/shell and scope, change mode, floors/areas in use, region/patch, budgets, inventory, protected elements, exclusions, confirmed and unconfirmed assumptions. |

Translate adjectives into observable conditions for this project. "Open" might mean legible destinations and uninterrupted views; "intimate" might mean screened seating; "ceremonial" might mean a strong axis; "overgrown" might mean controlled visual enclosure with required access retained. These are options, not universal furniture-count or empty-area targets. Record priorities and acceptable tradeoffs when goals conflict. Ask only when the answer materially changes the design; otherwise record a revisable assumption.

**Example:** "Support quick ordering, two-person conversation, and extended reading; service routes must not cross quiet seating; avoid orienting all seats in one direction." This guides tradeoffs better than "a white-and-wood cafe."

## 2. Understand the site/shell and evidence before selecting furniture

First obtain the dimensions and fixed conditions of the actual design area. For interiors, inspect wall thicknesses, floor heights, columns/beams, doors/windows/sills, floor openings, stairs, and arrival areas on floors in scope. For yards, inspect plot boundaries/terrain, the house footprint and vertical envelope, the actual gate, exterior fixtures, and required approaches. Distinguish immutable conditions, replaceable styles, parts that furniture can cover, and unverified conditions. Apply only the relevant survey checks below. Real architecture courses also examine plumbing, wet areas, and electricity; that does not justify inventing nonexistent plumbing restrictions for FFXIV.[5]

- The stair entrance, stair body, final step, and arrival/turning area are separate objects. Re-read them after changing the interior style rather than relying on the previous design.
- The stairs' XY projection is not automatically an exclusion zone. Check headroom, access, and in-game placeability before using the space beneath.
- Different interior styles of the same house type can have entirely different stair landings and under-stair spaces. Some enclose the whole area beneath the stairs and upper landing with walls, leaving no usable space; others have open stairs. Re-read arrival points, usable floor, and enclosed regions from native meshes in **the same design session after selecting the style**. Do not copy coordinates from a survey session, old plan comments, or another style.
- Read native openings and exterior fixtures first. Do not assume they are freely movable: distinguish fixed transforms from supported style replacements. Do not import Holodeck's assumption of freely generated shells/openings.[3]
- Confirm MCP house type, seed, revision, furniture policy, and renderer gaps. An image missing the entrance door or railings is not a valid design basis.
- Check image completeness before judging: are the required entrance, stairs, fixtures, and scenic textures actually rendered? Does a plan/top view mix in other floors or ceiling components, or mistake walled-off floor for empty space? If a renderer repair is authorized, fix and verify that defect; otherwise use independent valid evidence or leave the affected judgment unresolved. Do not change the design to disguise a rendering failure. An apparent obstruction or open area can be an image error rather than a design error.
- Closing off a floor is an option based on this brief, not a default inherited from another design. Every floor in use must remain reachable.

**Keep:** shell-condition diagrams/notes, fixed and editable elements, required circulation, measurement sources, and uncertainties. Pixel placement without dimensions/coordinate evidence is not completed measurement.

## 3. Use an organizing concept for decisions and style for expression

A parti is an organizing strategy that changes zoning, sections, light, and materials. "Minimal," "woodland," or "retro" are expressive vocabularies. If removing the concept changes no decisions, it is merely a label.[8]

For example, "a progression from brief social stops to quiet reading" suggests service near the front, no waiting queue in the transition, and a stable background with local lighting at the reading end. Wood tones, greens, and furniture silhouettes express that concept; they are not the concept itself.

Record a short concept, the decisions it changes, and the hierarchy of materials, brightness, silhouettes, and decoration, without imposing a fixed color count. Separate an atmosphere reference board from a real material/furniture board: the first conveys intent, while the second requires checking available assets, dyeable regions, undersides/backs, and preview support.[8]

| Intended feeling | Spatial choices to revise |
|---|---|
| Quiet | Reduce routes through activity areas; provide backing/moderate screening; separate long and short stays |
| Lightness | Continuous but unsealed boundaries, permeable sightlines, lower foregrounds, and a clear background hierarchy |
| Warmth | Material/color differences, task lighting, and layers of occupation, not just warm bulbs |
| A reading environment | Desks, seats, book access, and light working together, not just bookcases |

If retaining a distinctive furniture piece, state whether it is foreground or background. Do not give every zone an unrelated set of carvings, gold ornament, or textures.

## 4. Arrange functional relationships, activity space, and routes first

### 4.1 A relationship diagram is not a miniature floor plan

Choose relationship axes relevant to the program: public/private, active/quiet, use/service, performer/audience, view/foreground, or planted/occupied areas. List pairs that must adjoin, should be near, should be separated, or have no required relationship. A bubble diagram represents relationships; fit it into the actual site/shell afterward.[6]

For example, a venue with service and quiet reading could use:

```text
Entrance → Orient/pause → Distribute
                         ├─ Order/collect/brief conversation
                         └─ Quiet reading/extended work
Service entry → Operate/restock/tidy (without crossing guests' activity core)
```

### 4.2 Furniture needs space for use as well as its own footprint

Make it Home separately represents accessible sides, fronts that must be visible, parent-child support, and paired furniture relationships. Studio Matrx likewise combines furniture footprints with human activity areas rather than merely fitting boxes.[2][6]

| Spatial layer | What to check |
|---|---|
| Physical footprint/volume | Furniture body, protruding bases/handles, visible and embedded parts. |
| Operating area | Pulling chairs, sitting, standing, opening doors/drawers, reaching, working, and placing objects. |
| Connecting routes | Entrance-to-zone routes and access from a route to every actual use face. |
| Sightlines/legibility | Where a display face, window view, or directional cue is seen from; which obstructions are intentional. |

Operating areas may overlap at different times, but the use scenario must be stated. Simultaneous queuing, work, and passage cannot share space merely because static outlines do not intersect. Where uninterrupted conversation or work is a goal, prefer routes around its activity core. Promenades, processional routes, exhibits, and stages may deliberately put movement at the center; check their intended relationships rather than treating every empty area as a corridor.[6]

Dimensions in real-world courses are references tied to human bodies and particular regulations, not hard FFXIV rules. State character scale, comfort goals, and test conditions. Check "can pass," "convenient to operate," and "feels open" separately rather than reducing all three to one corridor width.[6]

### 4.3 Separate arrival, staying, and working

At arrivals that need orientation or distribution, provide room to stand, turn, and choose a direction before conflicting activity begins. Verify simultaneous waiting, seating, work, and passage rather than assuming they can share a buffer. An immediate reveal, screened transition, or direct arrival into an activity can also be intentional if the brief supports it and required access works. Wall displays are one possible cue, not a requirement for bookcases or plants.

Test the relationship between arrivals, seating, destinations, and focal views. If a group blocks a required route or presents an unwanted wall of seat backs, adjust its position, approach, orientation, height, or surrounding route. Axial seating, freestanding sofas, ceremonial symmetry, and winding paths can be valid; neither wall-backed seating nor a straight focal aisle is universal. For private functions, choose separation through distance, screening, level, orientation, or an enclosure according to the brief. A bedroom may need a working door and concealed arrival view, or may intentionally be an open studio or display; do not impose one domestic arrangement on every project.

**Emptiness does not establish good circulation, and it is not automatically a missing function.** Negative space may serve orientation, gathering, performance, views, composition, or deliberate restraint. If an essential activity or intended spatial layer is missing, address that role with a coherent arrangement rather than scattered fillers. If the empty area already serves the brief, retain it instead of adding another seating group or automatically centering a table.

**Keep:** activity/adjacency diagrams, primary/secondary routes, arrival areas, principal operating faces, and expected sightlines. Furniture selection need not be complete yet.

## 5. Turn relationships into comparable spatial frameworks

Fit required activity/viewing areas into actual site/shell dimensions, fixed structures, and openings to form a scaled block plan, then test real furniture and activity areas. For major organizational decisions, compare meaningfully different alternatives instead of decorating the first arrangement that fits; two or three may suffice, but their number is not a quota.[7]

Alternatives must change organization: wall-side versus central service, or reading deeper on one floor versus distributed across floors. Color changes alone are not spatial alternatives. A local correction does not require three complete houses each time.

| Comparison | Question |
|---|---|
| Functional completeness | Does every essential activity have a place, or was openness achieved by deleting functions? |
| Use conflicts | Do routes cross seating, operating, or queue areas? Can people choose a direction on arrival? |
| Scale/proportion | With actual dimensions, do activity areas, vertical space, and backgrounds still work? |
| Concept/sightlines | Do entrance and use positions support the concept, rather than only looking attractive in overview? |
| Cost/adaptability | Are item slots, masking pieces, construction difficulty, and later modification worth the result? |

Small spaces can combine functions through furniture/level-based zoning, storage boundaries, vertical use, and time-sharing. This does not mean deleting functions or using partitions everywhere. Transformable furniture requires checking alternate states and storage; do not invent mechanisms absent from the tool/game.[7]

When alternatives conflict, revisit zoning, furniture dimensions, or essential content. Do not contort routes into unnatural zigzags merely to achieve "no intersections." **Keep:** reasons for selection, principal problems in rejected alternatives, and remaining asset-dimension checks.

## 6. Define furniture roles and relationships before binding real assets

### 6.1 Search for a purpose, not just a theme name

Identify the missing role first: low background, work surface, shared focus, support, or masking. Then retrieve candidates. Holodeck combines semantic descriptions, appearance, and dimensions for asset retrieval; its object hierarchy distinguishes floor, wall, tabletop, and ceiling objects.[3]

Check Item ID, scope, regional/patch eligibility, acquisition or inventory policy, real dimensions, and pivot. Inspect thumbnails and both sides of the native mesh, transparent/open regions, dyeable areas, and support surfaces. If no candidate fits, choose another within authorization, revisit zoning, or expose a requirement conflict; do not silently buy a substitute, add a copy, or drop an essential function. Similar names/embeddings do not establish equivalent shape or use.

### 6.2 Make design intent inspectable and editable

| Record | Examples and purpose |
|---|---|
| Object and role | Entrance cue, short-stay seating, bar work surface, framing/screening component. |
| Semantic relationship | Against a wall, beside another object, aligned, facing, near/separated; identify the target explicitly. |
| Use relationship | Which seat/table edge a chair serves, rather than angling every chair toward the whole table's center; where a cabinet's access face points. |
| Support/dependency | Which table and actual surface supports a cup; whether a light has support; which children move with a parent. |
| Intentional overlap | Which components overlap for embedding/composition and which faces must remain visible; do not exempt every intersection in the group. |
| Uncertainty | Whether facing is visually confirmed or guessed, a surface is a candidate or native-mesh sample, or an effect requires the app. |

Planning/operation records should retain this information. This does not claim that MCP implements a complete scene graph or automatic relational solver. Make it Home's support hierarchy and paired distance/orientation, and Holodeck's relational constraints, motivate separating these records.[2][3]

Organize groups around anchor furniture before adding dependent objects. Preserve relative relationships when moving/rotating a group. Confirm forward directions visually; neither "the side nearest the wall is the back" nor "the nearest table is the target" is universal. Place props on native support surfaces, not on base plates or narrow edges mistaken for tabletops.

### 6.3 Preserve geometry when translating semantics into coordinates

Holodeck asks a model for relationships before solving positions; Architect-Ant outputs an editable coordinate DSL after specific training. Neither proves that models must never output coordinates or that untrained base models already guess reliable coordinates.[3][4]

Here, the model decides layout intent, facing, density, and legal combinations, then uses actual geometry to perform and verify MCP edits. Track asset-local, room-local, house-world, export scale, and screen mirroring conventions. A paper's top-left-origin/downward-Y rectangles are not house coordinates. Do not flip exports merely to make screenshots match left and right.[4]

Real furniture cannot be stretched like arbitrary rectangles. Preserve unit scale and asset dimensions; replace unsuitable furniture or change zoning. Coarse rectangles are for early planning only. Recheck recesses, angled shapes, cross-floor volumes, and floating relationships with appropriate native geometry and height information.

**Keep:** stable instance IDs, roles/groups/dependencies, source assets, positions/facing/heights, and reversible operations. Visually test one representative unit before extending it. Repetition can establish formal order, planting rhythm, or repeated audience seating; vary or repeat groups according to the program, not an automatic ban on identical arrangements.

## 7. Resolve plan, vertical relationships, boundaries, and light together

Fitting footprints does not establish a successful three-dimensional space. Elevations resolve openings, cabinetry, facades, and background proportions; sections resolve headroom, levels, sightlines, and hidden volumes. For interiors, coordinate the ceiling with zoning, beams, and lighting.[8] For yards, coordinate the house envelope, perimeter, planting/canopy layers, open sky, and foregrounds; a custom ceiling or enclosed boundary is not a missing component outdoors. Check only the constructions the design actually uses.

- **Plan:** relationships between activities and circulation, not just furniture boxes.
- **Vertical:** do heights, overhead elements, and foreground/background layers support the intended scale and sightlines? A low, open composition can be deliberate; height variation is not mandatory decoration.
- **Backgrounds/backs:** do cabinet backs, false walls, and scenic surfaces look constructed from other zones too?
- **Junctions:** walls, beams, cabinets, frames, and openings need plausible beginnings/endings, compatible seams, material directions, and thicknesses.
- **Hidden volumes:** embedded or cross-floor bodies must not intrude unintentionally elsewhere. Legal overlaps still require checking finished faces.

### Conditional technique: integrate scenic surfaces into constructed openings

When a scenic surface is meant to read as a window or skylight, establish the relevant wall/column junctions, ceiling, framing, and recessed opening first. Install the scenic surface afterward and conceal unwanted thick edges/backing. Foreground framing is optional and should serve the view, not require plants or grilles. Raising a Phasmascape or dyeing it a similar color can still leave a hanging box. Inspect from relevant use positions and upward views rather than hiding it with clipping.[10] A deliberate freestanding screen or visibly framed exhibit has a different intent; it need not masquerade as an architectural opening.

Ceilings affect headroom, native pendant lights, hidden lighting, and cameras. Lowering them may define a zone or feel oppressive; it is not a default for every design. Test representative components, distinguish front/back materials and dye coverage, then extend the order.[8][10]

For the recessed-window/skylight technique, the scenic surface appears **behind a constructed opening**, with the appropriate depth and finishing. Conceal its body/frame where that is needed for the illusion. A scene pasted onto a wall or a pillar-supported box may read as an attached panel instead. One construction sequence is:
1. Define the visible opening. Build a false wall with a doorway, arch, or window grid in front of the original wall. Recess the scene behind it and conceal all thick edges/frame.
2. Add a railing or sill within the opening, with side lights/plants to form foreground, middle ground, and distance.
3. For a skylight intended to belong to the native ceiling order, use its beam/bay structure to integrate the opening. If the scenic panel fits a bay, embed it there and test frame/material matching. An intentionally independent structure needs its own resolved junctions rather than arbitrary supporting pillars added to disguise an exposed box.
4. Hide frame/body from entrance, close, and upward views. If it still reads as a flat panel, add depth through recession, sidewalls, or subdivisions rather than more decoration.

**Keep:** coarse placement, major elevation/section relationships, representative normal-eye views, and unresolved junctions. Formal CAD is not required for every design, but three-dimensional thinking is.

## 8. Complete required uses and experience before finishing detail

Walk through each zone's use/viewing scenario against the brief: where people arrive, stand/sit, face, reach, and leave, and what happens when others pass simultaneously. A stage or display needs its intended views and occupied areas, not every domestic activity listed below. Check essential, supporting, and atmospheric objects separately. Plan lighting with the concept and construction; this stage verifies its actual sources and effects rather than postponing all lighting decisions until furnishing is complete. More pieces do not establish completeness.

| Zone | Check more than presence |
|---|---|
| Reading/work | Accessible seats, usable surfaces, book/object access, and light; decoration must not occupy the whole desk. |
| Service/bar | Separate guest/work faces, operation/restocking, collection/waiting; provide staff access. |
| Rest/conversation | Shared focus, conversational distance, seat orientation, and backing, rather than pushing all furniture to distant walls. |
| Display | Unobstructed fronts/view cones, room to pause, and no blocked circulation. |
| Storage/doors | Accessible faces, opening/retrieval areas, and operating positions, not just entries in a list. |
| Yard/landscape | Required gate-to-destination access, usable outdoor groups, equipment/plant access where requested, canopy/view relationships, and exterior fixture continuity. |
| Stage/display/installation | Intended camera/view cones, audience or performer positions where required, foreground/background depth, and declared nonfunctional or off-camera areas. |

Choose lighting roles from the brief: orientation, tasks, accents, uniform display light, darkness, silhouette, or theatrical contrast. Not every project needs every layer. Distinguish visible fixtures from actual sources and test the surfaces and positions that produce the intended effect. A dark scene still needs any required passage and interactions tested under its intended conditions. Approximate renderer highlights cannot verify actual game sunlight, shadows, or reflections.[8][10]

Backgrounds, use layers, and detail should support the chosen hierarchy. Where used, planting should have a spatial role, props should have intentional support, and working surfaces should retain the space required by the activity. Missing required functions need coherent arrangements; they are not solved by scattered fillers. Bare backgrounds, open sky, sparse planting, and prop-free surfaces may be complete choices, not omissions to fill.

**Keep:** status/evidence for essential functions in each zone and the distinction between symbolic use and actual game interaction. A decorative coffee machine can express service without brewing in-game; sitting or clicking a door needs separate interaction tests.

## 9. Verify by layer, diagnose causes, and revise the appropriate level

### 9.1 Separate technical, activity, and visual checks

| Layer | Checks | What it cannot establish |
|---|---|---|
| Technical/geometry | Identity/scope/patch/budget, transforms, support, unintended collisions, openings, connectivity, use faces. | No warnings/intersections means good design; render meshes equal game collision. |
| Activity completeness/usability | Essential functions, paired relationships, access/operation, simultaneous use, cross-zone conflicts. | Complete names/lists establish real usability; not visible means absent. |
| Spatial/visual | Concept, layers, hierarchy, density rhythm, third dimension, entrance/arrival experience, junctions. | Attractive top views establish eye-level comfort, or attractive lighting excuses a bad plan. |

Architect-Ant's LRS covers encoded geometry/function rules only. Its raw score starts at 10 and deducts penalties, potentially going negative; 10 does not establish an ideal layout or complete 3D usability.[4] This workflow uses **separate reasons and evidence**, not fixed quality scores, pass thresholds, or "high score means no revision." The model and user still judge the whole.

Numerical checks must state subjects and conditions: furniture body or activity area, route width/height range, excluded chairs/rugs/wall objects, inclusion of native stairs, bounding boxes or exact triangle projections. A few tested routes cannot establish whole-house usability.

Research geometry proxies also have purposes and limits. Architect-Ant Appendix C's narrow-passage proxy is not comfortable circulation, and some furniture is excluded as an obstacle. Its thresholds are not building regulations or FFXIV character tests.[4] AABB intersections are preliminary screening only. Distinguish height and purpose for legal embedding, passage under rugs, support, and decorative composition; do not impose a blanket overlap ban.[2][4]

#### Object-level diagnostics and image feedback (SceneCritic)

SceneCritic uses SceneOnto priors for dimensions, support, co-occurrence, and facing to check semantics, orientation, and overlap, reporting successes/violations for specific objects/relationships. Semantic checks include scale, co-occurrence, plausibility, proximity, and inventory completeness; these still do not cover full activity usability.[11]

Borrow its traceable diagnostic format without total-score gates. For each issue, record stable IDs, roles/relationships, obligation and applicability, geometry/image evidence, known versus inferred status, and whether revision resolves, retains, or introduces it. Complete inventories still require checking required seats, operating faces, and simultaneous activities. Unknown categories/facing must not pass by default.

- **Reproducibility is not correctness.** Dataset dimensions, co-occurrence, back-to-wall, and face-room-center priors are not requirements for FFXIV scenery. Wall placement and target seats follow this design's intent and the actual asset's forward direction. Common pairings do not justify adding or scaling furniture automatically.
- **A check's name does not establish precision.** SceneCritic Appendix B's True Overlap uses 2D OBBs and SAT, not exact triangles or full 3D game collision. Its orientation aggregation uses any-pass: one applicable subcheck passing does not verify every specified relationship.[11] Retain individual evidence, vertical ranges, intentional compositions, and untested relationships rather than hiding them under one total.
- **Scoring and proposing are different jobs.** The paper found VLM scores sensitive to views/retesting while image feedback still helped correct semantics and facing.[11] Use readable geometry for known facts, and multiple views/model judgment to identify spatial/compositional problems and propose revisions. Unstable image scores do not justify skipping image inspection; a model's orientation complaint does not justify blindly rotating furniture.
- **Check side effects each round.** Compare before/after diagnostics for the same IDs. Fixing one issue must not break support, other seats, openings, or routes. Separate observations, causal hypotheses, and proposed changes.

### 9.2 Choose views according to the question

| View | What to inspect |
|---|---|
| Each in-scope area's overview/diagnostic plan | Zones, density, primary/secondary routes, required functions or views, purposeful and unexplained empty areas. |
| Entrance eye level and looking back at the entrance | First impression, turning, orientation, door use, pressure from tall objects. A camera on the threshold cannot see the door itself; pair it with a reverse view and a plan containing the door. |
| Seated/operating/viewing positions | Tables/chairs, work surfaces, backing, sightlines, actual visible content. |
| Final steps, arrival, and after turning | The transition from walking to staying/choosing a route, not just a screenshot of empty floor. |
| Upward, elevations, zone boundaries | Thick skylight frames, beam/wall junctions, cabinet backs, cross-floor intrusions, finishing. |
| Yard perimeter, gate approaches, and house-facing views | Actual entry alignment, fixture-set continuity, planting/canopy occlusion, and required outdoor use faces. |
| Specified stage/display cameras and off-axis checks | Intended composition, viewing access, declared camera-dependent illusions, and any usable areas outside the hero shot. |

Choose applicable views from this table; a single-floor set has no stair-arrival test, while a yard overview cannot replace a required gate-level view. Normal eye-level interior views retain the actual ceiling. Top-view clipping is for diagnostics only and must be labeled. After structural edits, check that cameras are not inside walls. Mirrored display does not change house coordinates; separate missing materials/permanent structures from design faults first. A deliberately camera-dependent illusion can be reviewed from its specified position, but do not claim that one view verifies unrestricted use or every other angle.

Provide access to the sides and faces required by the specified use, not automatically to every side of every object. If a narrow approach defeats that use, verify the asset, character/interaction, and viewing conditions, then reorganize the affected relationship rather than defending a tiny coordinate nudge. A decorative bed, accessible working cabinet, and staged tabletop have different requirements; neither illustrative clearance numbers nor bounding-box paths prove game usability.

### 9.3 Turn feedback into falsifiable revision hypotheses

| Feedback | Diagnose first | Revision level |
|---|---|---|
| Too empty | Is a required function, spatial layer, or focal relationship missing, or is the sparseness intentional? | Recheck the brief; add coherent groups only for missing roles, or retain purposeful emptiness. |
| Too crowded | Activity conflicts, poorly fitting assets, blocked required views, or enclosure inconsistent with the intended density? | Reorganize, replace within policy, or deliberately remove lower-priority content; do not stretch native furniture or delete essential functions. |
| Messy/monotonous | Too many focal pieces, fragmentation, conflicting materials/silhouettes, or rhythm-less repetition/heights? | Groups, backgrounds, distinct uses, material hierarchy. |
| Fake | Unsupported objects, wrong facing, surface-only construction, thick exposed frames, or distorted materials/structures in rendering? | Geometry, use relationships, construction, or tool verification. |
| Jarring/pasted on | Does a feature intended as integrated construction expose unintended frames, seams, or supports, or is it meant to be a freestanding exhibit? | Resolve the intended boundary/depth/junctions; use recessed openings only when an architectural illusion is the goal. |
| Passable but inconvenient | Detours, queues/chair pull-out intrusion, arrival directly into work faces? | Reorganize groups/routes instead of continuing to snake around furniture. |

Make it Home's local translations/rotations and larger swaps inspire layered corrections: decide whether organization or fine adjustment is needed, rather than endlessly nudging coordinates.[2] Record the issue, causal hypothesis, expected improvement, actual evidence, and retain/revert decision. A successful operation is not a reason to defend a failed design.

### 9.4 Comparison and interpretation discipline

For formal layout comparisons, hold the site/shell, cameras, and evaluation conditions fixed. If assets/materials/light positions also change, describe a comparison of complete proposals rather than attributing differences only to layout. Anonymous A/B and reversed ordering can reduce bias; allow no clear preference or insufficient evidence. This does not require automatic calls to additional paid models.[3][4]

Use "usable / problematic / unidentified / insufficient evidence" for applicable use checks, and "not applicable" with a reason for excluded checks. Track visual preference separately. Distinguish unseen from absent. Describe visible evidence without guessing exact dimensions or hidden equipment from images. Architect-Ant Appendix H explicitly limits its visual evaluation to automated image preference, not human research or geometric-validity testing. Different shells and selected samples also affect comparisons.[4]

### 9.5 Aesthetic comparison of actual outputs (limited AesthetiQ adaptation)

For 2D graphic layouts, AesthetiQ compares rendered candidate pairs to obtain relative aesthetic preferences, then uses AAPA/DPO-style preference training. Its training data is additionally screened for alignment and overlap quality. This differs from reproducing one reference coordinate answer or assigning every image an absolute aesthetic score.[12]

Borrow the comparison method, not the model or reward directly. Under the same requirements and comparable views, ask the model which candidate better expresses the concept, whether focal points/groups are clear, whether proportions/materials work together, and whether negative space has a purpose. These 3D review criteria are this workflow's adaptation, not interior-design abilities established by the paper.

1. List known technical issues and uncertainties before comparing spatial expression. One attractive image does not excuse blocked doors, missing functions, or failed support.
2. Compare actual furniture and finished faces, not just abstract boxes. Multiple valid solutions may exist; deviation from reference coordinates is not itself an error.
3. State the scope if views, exposure, materials, or assets differ. Do not cherry-pick one favorable angle. Give relative reasons rather than invented percentages, and retain no-clear-preference/cannot-judge outcomes.
4. Alignment/low-overlap heuristics for 2D graphics cannot become a rule banning 3D furniture overlaps. Check embedding, parallax, framed views, and support according to construction intent.[12]
5. AesthetiQ judge preferences, mIoU, and training results do not establish this user's preferences or 3D comfort.[12] Do not claim to reproduce its results or launch training/additional paid image judging merely because a reference was added.

## 10. Validate before delivery and leave an editable design

Completion does not mean using every slot or placing every candidate. Delivery should explain the problem, organizing concept, plan/third-dimension solution, and remaining evidence gaps, not merely provide attractive images.[9]

### Design works

- [ ] Every required use and experience in the brief has a corresponding arrangement; no unrelated household/venue functions were added by default and no essential ones were silently deleted.
- [ ] Required arrivals, routes, use/viewing positions, and departure work for their intended scenarios; any deliberately shared movement/activity areas are justified and tested.
- [ ] The concept changes decisions; groups share a language while supporting distinct uses.
- [ ] Applicable plan, vertical, background, boundary, lighting, and detail relationships support the concept; constructed junctions are resolved without requiring ceilings, scenery, or greenery everywhere.
- [ ] Negative space has a purpose and dense areas retain operating space; item counts/scores do not replace judgment.

### Implementation is trustworthy

- [ ] Real MCP state and export match item by item. Check identity, scope, regional/patch eligibility, inventory policy, unit scale, finite transforms, and separate applicable budgets.
- [ ] Recheck activity areas, support, and facing after binding actual assets, not just early rectangles.
- [ ] Preserve snapshots/stable IDs. Use revision-guarded atomic batches each round. After timeouts, read back first rather than replaying committed additions.
- [ ] List preview limitations, intentional overlaps/floating, and untested items explicitly. Compare protected elements and out-of-scope payloads with the authorized baseline; do not alter unrelated zones/designs.
- [ ] Test required entrance/door selection, characters/cameras, stairs where present, sitting/use or teleport interactions where required, floating persistence after re-entry, and relevant lighting in the target app. Distinguish not applicable from unverified; untested is not passed.

### Delivery supports continuation and presentation

Retain a concise brief, proposal tradeoffs, editable object/group dependencies, dimension/facing evidence, representative plans and relevant eye-level/camera images, necessary vertical/construction notes, and material references. Label each image's purpose, clipped content, orientation, and provenance. Distinguish native previews, flat schematics, in-game screenshots, and AI-edited illustrations; a redrawn image is not evidence of exact placements. An approximate perspective is not a scaled construction drawing.[9] Keep one working note and the necessary revision evidence rather than generating a separate document or request/response file for every worksheet row or edit.

List technical evidence separately: text/schema validity, native-mesh/static-material visibility, specified geometry tests, and app behavior tests. Updating this method does not make old layouts pass new checks automatically. Unretested historical results retain their original scope.

The following is an optional library of in-game construction techniques selected by the problem. Not every design needs them, and they are not newly implemented tool APIs.

## 11. HGXIV construction techniques and design adaptation

This section organizes useful content from the full guide, not one project's history or a requirement to use every trick. Establish purpose/composition before choosing techniques, then assess construction, item slots, and app verifiability. Instructions for concealing frames, mannequin bodies, or source objects apply when creating that particular illusion; an intentionally exposed exhibit or stage structure has a different goal. Required viewing conditions come from the brief, while hidden bodies still need checks for unintended effects on other usable areas.

### 11.1 Operations, previews, storage, and material risks
- Distinguish moving, rotating, returning to inventory, and storage. The guide notes additional contents or retrieval restrictions for paintings, aquariums, wallpaper, consumables, etc. Back up risky changes, confirm current rules, and do not assume removal is lossless.
- In-game furniture previews help test scale before purchase, but may not cover cash-shop/event items or interior materials. Cross-check database thumbnails, native meshes, and actual previews.
- Storage placement can bypass some normal snapping/boundary restrictions, not allow unlimited wall penetration. Orange center points, pivots, and visible geometry centers need not coincide. In-game center-point measurements do not replace mesh bounds/pivots.
- Furniture slots, storage capacity, and special interactive-object limits are different budgets. Do not substitute historical guide capacities for current project policy. Hidden lights, masking pieces, and camera-collision layers consume slots too.

### 11.2 Grid Snap, alignment, textures, and construction identification
- Grids help standardize lines, beam spacing, and openings. Use fine offsets for seams, curved windows, and z-fighting. Manual game grids depend on characters/cameras and residential districts; they are not necessarily MCP world coordinates.
- Coplanar overlaps can z-fight; excessive offsets create steps. Establish required overlap relationships, then check gaps, texture directions, front/back faces, and finishing from normal views.
- Group complex compositions and temporarily dye components different colors. Preserve snapshots/stable instance IDs; do not accidentally save displaced unrelated furniture while clearing construction space.

### 11.3 Tabletop/wall floating versus floor-furniture lifting
- Floating tabletop/wall items and incrementally lifting floor furniture are different in-game construction paths. Riviera Wall Shelf, Wooden Loft, Stage Panel, and Wooden Beam are tools, not necessarily components that remain in the final design.
- Disabling surface snapping can detach tabletop items. False walls/beams can reorient or carry wall objects. Stage Panel and certain cabinet backs have different snapping behavior; not all partitions are equivalent walls.
- Floor furniture has item-specific lifting increments, minimum float heights, and lock/re-entry checks. Approximate Loft units in the guide are not universal meter values. MCP storing coordinates does not guarantee persistence after game re-entry.
- Final work still needs intelligible support/embedding. Permission to float does not justify cups hanging without reason below shelves. Candidate support surfaces may be base plates, narrow edges, or decoration; confirm with native-mesh sampling and images.

### 11.4 Hangers, cross-floor work, and under-stair construction
- Wooden Beam hangers/extended hangers help move wall/tabletop objects upward or downward, useful for exposing a small part as a handle, frame, or trim. Do not assume every floor item can sink indefinitely by the same method.
- World Markers, window bottoms, or Mounted Box Shelf can reference cross-floor alignment. /doze and first-person views help inspect interstitial spaces in-game; they are not MCP placement commands.
- Record bodies hidden above/below and check intrusion into other floors' usable space. Small under-stair voids/placeability differ from Medium. A geometric gap is not verified usable space.
- Build in MCP with explicit world coordinates, dependency groups, and versioned ops. Do not imitate manual glitches with meaningless moves. Verify import/re-entry and construction feasibility separately.

### 11.5 Lighting: separate visible fixtures from actual sources
- Set base brightness first, then task, accent, and hidden fill lighting. The guide notes that custom ceilings can block native pendant lights; fixture count alone is insufficient.
- Hidden sources can sit above ceilings, in corners, or behind scenery; visible fixtures support use/composition. Use light to support the brief's orientation, tasks, and focal emphasis where required. Uniform illumination, deep shadow, or silhouette may instead be intentional; layered brightness is not a universal style rule.
- Light/dark surfaces, material reflectance, and source placement jointly affect atmosphere. White walls alone are not completion, and dimness does not require dark wood on every surface.
- HGXIV suggests Metal Work Lantern for white ambient fill, Alchemical Lantern/Assorted Candles for warmth, and Queen's Rest for strong spotlighting. Treat these as candidates to test, not permanently optimal rules; recheck acquisition/version availability.
- Custom pendants can combine candle holders/lanterns; Factory Wall Lamp can be partly embedded; Hingan Chochin Lantern can support slit-light forms. Establish fixture shape and hidden-source positions before testing illumination goals.

### 11.6 Dynamic light, shadows, water light, and platform limits
- For a coherent starry-sky illusion, test dark backgrounds, moon surfaces/small lights, and varied flickering objects with the nearby windows' day/night settings. Contradictory skies or illumination may be deliberate in a surreal/theatrical brief; identify the intended effect instead of treating every mismatch as a defect.
- Shadow-window scenes need occluders, backgrounds, and hidden sources. Water light depends on water sources, time, Glare, and platform/client settings. The guide describes PC/platform differences, not universal client guarantees.
- This renderer still lacks real shadows, reflections, GI, and complete emissive/animated materials. Adding lights or water objects does not reproduce the guide's effects. Verify shape, static texture visibility, and native game lighting separately.

### 11.7 Native windows, sunlight, and custom windows
- Check native openings and replaceable styles before adding imitation windows. Time, direction, and front/back faces affect bright surfaces and sun rays. The guide distinguishes north-window brightness from rays and notes some stained-glass day/night behavior; confirm in the current app.
- Reversing windows may remove protruding shutters but change snapping, selection, or sunlight. Preserve required front-face lighting and conceal unwanted frames in construction, rather than only turning until the renderer looks flat.
- For bay/bow windows, build the upper frame first, then openings, side frames, and lower edges. Allow recession depth and side returns. Do not start with a flat window and try to disguise it with thick furniture afterward.
- Recessed scenes, sills, subdivisions, backgrounds, and limited foreground establish layers. Cabinetry, bookcases, or thin partitions can provide frames, but check exposed bodies/backboards from the sides.

### 11.8 Special window scenes and Phasmascapes
- Rain scenes may combine recessed frames, dark backgrounds, and hidden shower streams. Conceal shower heads and splash side effects. Dark windows may use colored backing, glass, or aquarium glow; sea scenes can separate sky, water, and shore with justified foregrounds.
- **A Phasmascape is a scenic surface with thickness, upper/lower lips, and curvature, not a ready-made window opening.** Define the visible opening/recession first and conceal thick edges with frames/walls/ceilings. The scene sits behind; plants/grilles are foreground only. Hide inappropriate body exposure from every viewing angle.
- Test angles when combining glass grids with curved Phasmascapes; flat placement does not guarantee no intersections. Phasmascapes also affect collision/selection. Visual transparency does not imply click-through or passage.
- Outdoor views must suit the floor, theme, and user settings. Do not force a garden/night sky into a basement bar merely to use new furniture. A visible sky texture does not establish a coherent atmosphere or architectural relationship.
- Inspect the actual scenic material slot, not only the frame. A missing principal image is not a finished exterior view. Database use tags, embedding retrieval, and renderer support are separate concerns.

### 11.9 Entrances, false doors, selection, and cameras
- Spawn-to-door distance depends on house type/district. Preserve orientation, turning, departure, and controller space in front of doors. Do not require mouse users to click through a narrow slit.
- Distinguish functioning doors from decorative false doors. Check whether foreground pieces block selection of interactive doors. The guide explicitly warns that Stage Panel, full partitions, and Phasmascapes are not transparent click-through layers.
- **Visual transparency, character passage, mouse/controller selection, and camera passage are four independent questions.** Two-column collision tables can become misordered in text export; do not infer capabilities from one flattened list.
- Custom walls/ceilings may not block cameras. The guide's bed/wall meta addresses a separate construction layer. Do not automatically fill spaces with hidden beds as a universal patch: check need, slot cost, cross-floor intrusion, and current behavior.

### 11.10 Ceilings, beams, coffers, and skylights
- Flooring Mat/Combed Wool Rug undersides, some tiles, and table undersides can create flat or concrete-like ceilings. Compare undersides, not just front thumbnails. **Dyeability does not mean the underside dyes too.** Compare the required orientation: white dye may leave pronounced wood grain underneath. Choose another component for smooth light surfaces instead of repeatedly applying white dye. Maintain height and grain direction; adjust seams rather than hiding them with z-fighting.
- Coffered ceilings use regular recesses and thick beam lines for depth; tray ceilings have one raised center. Beams can join walls, columns, or existing moldings. Adjust corners/edge bays without arbitrary height changes in every bay.
- White Rectangular Partition, Wooden/Factory/Natural Wooden Beam, furniture undersides, and partially embedded components can form construction. Large-area coverage saves slots but unused bodies may intrude into other floors; retain complete geometry awareness.
- **Build continuous ceilings and recesses before framing visible skylight scenes.** Edges must read as architectural finishing. Add crossbeams/subdivisions or join sidewalls where necessary so the skylight belongs to an activity zone or the whole ceiling order. An isolated thick hanging box, even raised slightly, is not a completed skylight.
- Reserve space for native pendants, hidden fill, and cameras before building ceilings. Do not hide awkwardness by clipping ceilings from renders. Inspect the same revision from entrances, seats, and upward views.

### 11.11 Walls, color, and composite components
- Color affects apparent scale: light/cool surfaces often feel open, dark ceilings may seem lower, and dark back walls may contain oversized rooms. These are testable hypotheses, not formulas for every house.
- Neutral interiors still need focus and texture. An accent wall may be a window seat, fireplace/low-cabinet group, storage composition, or textured wall rather than a bright plane. Consider adjacent wall colors; painting everything white is not completion.
- Wainscoting, shiplap, panel grids, and partial wallpaper can use cabinet backs, Wooden Slat Partition, or furniture fragments. Compare texture, junctions, and exposed doors, not names alone.
- The guide uses Cheese Collection/Disordered Wardrobe, bookcase backs, upper cabinet sections, bread racks, barrel racks, and others as components. Before adopting them, inspect native front/back faces, thickness, dye coverage, and how unused bodies are concealed rather than copying the list.
- Overlapping parts are legal compositions but require completed fronts, sides, and backs. Connect zones with compatible materials and clear hierarchy, not unrelated full-height cabinets as filler.

### 11.12 False floors, raised areas, and stair arrivals
- Raised areas can distinguish activities and add layers, not solve every shortage of floor area. Check the hardest large item to float, remaining furniture/headroom, perceived edge safety, and subsequent access first.
- Smooth, dyeable, embeddable furniture such as Hingan Bookshelf can make platforms. Existing stairs/railings may provide construction references; this does not mean every design should seal stairs or cover floor openings.
- Align steps/platforms against reliable references. Landings must accommodate standing, turning, distribution, and door interaction. The final step must not lead directly into a door, bar stool, or queue.
- Intermediate landings/material turns can keep stairs from reading as a solid wall. Curved stairs, false treads, and hidden railings still need clearance, character, and camera tests. One nonintersecting XY line does not verify arrival experience.

### 11.13 Mannequins, special displays, and personal detail
- Mannequins are interactive objects with equipment, poses, race-dependent scale, names, and other state, not ordinary static statues. Check current count limits, support/floating, and whether tools preserve those fields.
- If weapon, clothing, or prop displays are meant to conceal their mannequin supports, hide unwanted bodies, hair/ears/tails, and names, and resolve mounts/recesses. A visibly posed mannequin or exposed display system may be intentional; check it against that goal rather than automatically hiding it.
- Props can describe activities or personal habits. If the tool cannot reconstruct the required appearance, do not use invented empty models or composite images as evidence of completion.

### 11.14 Execution and acceptance: turn techniques into testable proposals
1. Identify the missing spatial role, then choose a technique. Record display faces, hidden volumes, construction references, and dependencies.
2. Test one representative composition's front/back, seams, scenic surface, and light. Resolve frame/ceiling/wall construction before extending it.
3. Work in rounds from shell to props and high to low. Preserve snapshots, full-body slot costs, and cross-floor impacts. Do not replay committed addition batches.
4. Verify appearance, character passage, arrival/route choice, door interaction, cameras, support, and re-entry separately. Check low light, day/night, and use positions as the scenario requires.
5. List unsupported shadows, sunlight, dynamics, water light, floating persistence, and selection collision as app tests pending. Guide experience is not this tool's test output.
6. Delivery should state concrete lessons implemented and remaining unverified behavior, not merely list techniques read or report item counts/scores.

### Source and applicability

Primary reference: [HGXIV Housing Glitch Guide / How-to Design Guide](https://docs.google.com/document/d/1zYM0oTl-skbdc7xL7mNsFPE18SwGciicdV7Jtkm2i6A), with contributors including Ashen Bride, Synt Slap, Dividus Yliaster, and the HGXIV community. This section summarizes practical information across the guide and adapts it into operations, rather than translating it paragraph by paragraph. The guide includes post-2018 technique history, 6.58/7.0 collision tables, and historical capacities that may change with game version/platform. Current project budgets, database identities, native geometry, and app tests take precedence. Do not turn historical lists into hard restrictions.

## 12. How sources are used and where they stop applying

Distinguish source claims from this workflow's adaptations. Using design knowledge does not mean downloading models, training, changing the control architecture, or implementing a new solver.

| Source/reading scope | Incorporated here | Not transferred directly |
|---|---|---|
| Studio Matrx: course overview and five complete units | Brief, fixed/editable shell, concept versus style, bubble → block → furniture/activity areas, alternatives, elevations/sections/ceiling, presentation/feedback.[1][5][7] | Indian regulatory context and teaching dimensions are not FFXIV rules. Multifunctional furniture without actual mechanisms remains unverified intent.[6][8][9] |
| Yu et al., **Make it Home**, §3–4 and §7 | Use/visible faces, parent-child support, paired distance/facing, wall relationships, door-to-door paths, local/global revisions.[2] | Bounding surfaces/approximate view cones and limited support levels are not exact native collision. Lighting, acoustics, style/color are not fully solved capabilities.[2] |
| Yang et al., **Holodeck**, §3 and §4.3 | Modular thinking, dimension/appearance-aware retrieval, anchors/relational constraints, candidate proposals; separate correct assets from sensible arrangements.[3] | Freely generated shells, blanket overlap bans, and the paper's DFS candidate selection do not transfer directly to fixed houses/legal composites. This tool gains no automatic constraint solver from the reference.[3] |
| Rodionov et al., **Architect-Ant**, §3 and Appendices C, E–H | Editable object representation, structural input, completeness and separate geometric/functional diagnostics, 2D-to-3D rechecks, evidence discipline for visual comparisons.[4] | SFT/GRPO and results on specific residential types do not establish equivalent untrained-model ability. Its DSL lacks height, arbitrary yaw, and explicit relationships; rendering separately infers orientation/adapts assets. Scaling, LRS rankings, and thresholds are not project policy.[4] |
| Sengupta et al., **SceneCritic**, §3–4, §6–7, Appendix B | Object/relationship diagnostics, rule applicability, geometry/view division of labor, revision traces, side-effect checks.[11] | Dataset priors, size/angle thresholds, totals, and any-pass are not project standards. True Overlap is an OBB proxy, not exact mesh collision. Stable scores do not replace composition/user judgment.[11] |
| Patnaik et al., **AesthetiQ**, §3–5 | Relative preferences over actual outputs rather than one coordinate answer, with reasons; distinguish geometric validity, functional usability, and composition.[12] | The research concerns 2D graphics. AAPA training, alignment/overlap screening, mIoU, and judge win rates do not establish 3D circulation, support, or personal preferences. No training/judge model was added here.[12] |
| **HGXIV Guide**, 14 categories in Section 11 | Techniques for building spatial concepts in-game: floating, embedding, hidden frames, ceilings, lights, cameras, etc.[10] | Historical capacities and version/platform collision/lighting are not tool tests. Feasibility does not make every technique worth using in every design.[10] |

### Do not substitute proxy metrics for final quality

- **Support is not copying:** cases, semantics, and measurements may inform relationships, but case priors must serve current activities, shell, and user. Neither wall-hugging furniture nor center-facing seats are natural laws.
- **Emptier is not better:** low collision, connected routes, and complete inventories answer only part of the problem. Check complete use and spatial experience zone by zone.
- **An image is not validation:** Architect-Ant explicitly separates evaluation geometry from downstream display meshes. A 3D render is not independent verification of predicted geometry.[4] Check final actual placements against final actual exports, not early drafts or attractive replacement assets.
- **Research preferences are not user acceptance:** automated visual evaluations have view, recognition, ordering, and sample-selection limits. Actual user app feedback remains authoritative.[4]
- **Separate cost from capability:** plan intent/relationships completely, batch operations, and review important views together rather than making a model decision for every furniture item. This does not reproduce the papers' speed/quality. Without separate authorization, do not start training, bulk paid judging, or new system implementation.

## Project-start and iteration-review template

This is a task-note format, not an MCP API or a requirement for fixed room/furniture counts. Keep only applicable fields and record why a significant check is not applicable. For a small authorized revision, reuse the existing brief and update the affected relationships, invariants, and evidence rather than filling out an entire new project dossier.

```markdown
# Spatial design working notes

## Scope and authority
- Interior / yard / coordinated scopes; home / venue / display / set / other purpose:
- New design / revision / constrained reuse / staged delivery / assessment only:
- Authoritative baseline (app save / export / MCP snapshot), seed and revision:
- Areas and fixture classes allowed to change; protected elements and payloads:
- Read-only diagnosis / exported proposal / authorized live application; tool-repair authorization:
- Applicable checks / not applicable with reason / relevant but unverified:
- Requirement obligation (required / preferred / optional), applicability, and evidence status:

## Program
- Users/characters/cameras, activities or viewing experience, duration, simultaneous use:
- Essential/supporting/atmospheric functions; exclusions:
- Success criteria and required evidence:
- Confirmed requirements / provisional assumptions / questions that matter:
- Priorities and acceptable tradeoffs; criteria for retaining or rejecting a revision:

## Site/shell and constraints
- House/plot type, style, region/client/patch, floors/areas in scope:
- Interior if relevant: openings, stair arrivals, columns/beams, headroom, cross-floor impacts:
- This style's stair landing and enclosed/usable under-stair areas (re-read affected geometry after style selection):
- Yard if relevant: plot/terrain, house envelope, gate/approaches, perimeter/fixture set, canopy heights, neighboring views:
- Render completeness: required structures/materials, hidden or mixed floors, clipping and known gaps:
- Fixed / replaceable / coverable / unverified:
- Separate applicable furnishing/interaction budgets, policy source, scope and tool limitations:
- Acquisition/inventory rule: new types, extra copies, substitutions, or existing-instance subset only:
- Procurement/currency, storage, and temporary construction requirements separate from final placement slots:

## Parti and expression
- One-sentence organizing concept:
- Zoning, sections/sightlines, lighting, and material decisions it actually changes:
- Atmosphere references and available material/furniture boards:

## Relationships and alternative frameworks
- Activity zones; must adjoin / preferably near / separated:
- Required routes, arrivals, operating/viewing positions; service/audience routes only where needed:
- Major A/B alternatives (more if needed), differences, costs, selection reasons:

## Furniture and activity relationship worksheet
- Requirement → zone → group/stable instance ID → usability evidence:
- Anchors, real assets/Item IDs, dimensions, pivots, facing/confidence:
- Use/operating areas, visible faces, target seats:
- Support parent/surface/children; dependencies for group moves:
- Legal overlap/embedding pairs, purpose, finished faces, cross-floor bodies:
- World coordinates/heights, export scale, display mirroring:
- Requirement or preference → chosen relationship/technique → applicability reason → evidence:

## This iteration's hypotheses and operations
- View/use scenario exposing the issue:
- Suspected cause; brief / zones / groups / construction / detail / tool layer to revise:
- Expected improvement and relationships to preserve:
- Snapshot, expected revision, committed operations; read back after timeouts:
- Observed/measured change; retain / revert / unresolved:
- Same-ID diagnostics: resolved / persistent / new; side effects on other relationships:

## Separate acceptance checks
- Technical: identity, regional/patch eligibility, inventory, separate budgets, transforms, support/unintended collision:
- Required use: each applicable zone = usable / problematic / unidentified / insufficient evidence:
- Activity: arrival, operation, simultaneous use, departure; not just centerlines:
- Visual: concept, groups, backgrounds, applicable boundaries/vertical layers, hierarchy, junctions:
- Geometry test conditions: width/height, obstacles/exclusions, relevant native structures, scope:
- Views: normal-eye / overview / clipped diagnostic purposes; uncertainties/render gaps:
- If A/B: which shell/cameras/assets/lighting are fixed or different:
- Aesthetic preference with reasons / no clear preference / cannot judge; no inference of 3D function:
- Not applicable with reason versus relevant but untested; protected-state comparison:

## Delivery and continuation
- Final state/export revisions and item-by-item read-back evidence:
- Verified / unverified / requiring app interaction or re-entry:
- Whole scope versus stage; finished and unfinished areas; declared camera-only or nonfunctional content:
- Main tradeoffs, representative images, recoverable revisions, remaining issues:
- Actual model/resource use and per-design MCP shutdown evidence where applicable:
```

**Core sequence: establish this brief's uses, experience, boundaries, and relationships; bind real assets and resolve the three-dimensional space; use detail to reinforce the intended whole. Verify applicable claims with appropriate evidence, without turning one project's solution into the next project's rule.**

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
