# From initial thinking to a complete interior: a reusable design workflow

> This is a design and implementation method, not a project diary or furniture recipe. Start with people's activities and spatial relationships, then select furniture, resolve construction, and add detail. Technical checks provide evidence; they do not replace the model's or user's design judgment.

The workflow follows Studio Matrx's progression from brief to presentation, incorporating Make it Home's ergonomic and relational representations and Holodeck's semantic decomposition, asset selection, and relational placement into the same design steps.[1][2][3]

Architect-Ant contributes editable representations and separate acceptance checks. Its methods and limitations are noted where relevant; this does not mean the tool implements its training or scoring systems.[4]

Section 11 retains HGXIV's in-game construction techniques. Section 12 gathers source adaptations and the parts that cannot be transferred directly.[10]

SceneCritic contributes traceable object/relationship diagnostics and a division of labor between symbolic checks and image feedback.[11] AesthetiQ inspires relative aesthetic comparisons of actual rendered results. Its research concerns 2D graphic layouts, not 3D interiors; Section 9 defines the limits of this adaptation.[12]

## Overall sequence

```text
Users, activities, and success criteria (program)
  → Understand the actual shell, fixed conditions, and tool boundaries
  → Propose an organizing concept that changes decisions (parti)
  → Activity zones, adjacency, and routes (bubble diagram)
  → Compare distinct spatial frameworks (block plan)
  → Bind real furniture, activity areas, and support relationships (furniture plan)
  → Resolve plan, elevations, sections, ceiling, and light together
  → Complete functions, then add lived-in details
  → Diagnose separately, inspect actual images, revise the appropriate layer
  → Validate in the target app and deliver an editable design
```

This is an iterative convergence process, not a one-way pipeline. New furniture dimensions may require rezoning; sightline problems may require a ceiling change; user feedback may overturn the concept. Adjusting a cup does not require rebuilding the house, but structural or functional failures cannot be solved by adding cups.[5][7]

## 1. Turn a theme into an activity brief

"Cafe," "conservatory," and "modern home" describe types only. Identify who does what, when, with whom, and which activities conflict before deciding the space's shape. Programming establishes requirements first; it should not begin by choosing partitions and furniture forms.[5]

### Record the brief

| Item | Questions to answer |
|---|---|
| Users and activities | Solitude, conversation, gatherings, reading, service, or display? How do people enter, stay, use, and leave? |
| Essential/supporting/atmospheric | Which functions are indispensable? Which support them? Which can be reduced? |
| Simultaneous use | Will staff, waiting guests, people pulling chairs out, and passersby occupy the same area at once? |
| Success criteria | From which positions and use scenarios will requirements be verified? |
| Boundaries | Floors in use, house type, patch, budget, exclusions, confirmed and unconfirmed assumptions. |

Translate "open" into observable conditions: destinations are legible from the entrance, tall objects do not squeeze normal views from both sides, and activity areas remain complete. These are not furniture-count or empty-area targets. Ask only when the answer materially changes the design; otherwise record a revisable assumption.

**Example:** "Support quick ordering, two-person conversation, and extended reading; service routes must not cross quiet seating; avoid orienting all seats in one direction." This guides tradeoffs better than "a white-and-wood cafe."

## 2. Understand the empty shell and evidence before selecting furniture

First obtain shell dimensions, wall thicknesses, floor heights, columns/beams, doors/windows/sills, floor openings, stairs, and arrival areas on each floor. Distinguish immutable conditions, replaceable styles, parts that furniture can cover, and unverified conditions. Real architecture courses also examine plumbing, wet areas, and electricity; that does not justify inventing nonexistent plumbing restrictions for FFXIV.[5]

- The stair entrance, stair body, final step, and arrival/turning area are separate objects. Re-read them after changing the interior style rather than relying on the previous design.
- The stairs' XY projection is not automatically an exclusion zone. Check headroom, access, and in-game placeability before using the space beneath.
- Different interior styles of the same house type can have entirely different stair landings and under-stair spaces. Some enclose the whole area beneath the stairs and upper landing with walls, leaving no usable space; others have open stairs. Re-read arrival points, usable floor, and enclosed regions from native meshes in **the same design session after selecting the style**. Do not copy coordinates from a survey session, old plan comments, or another style.
- Read fixed doors/windows first. Do not move the house's original structure by importing Holodeck's assumption of freely generated shells/openings.[3]
- Confirm MCP house type, seed, revision, furniture policy, and renderer gaps. An image missing the entrance door or railings is not a valid design basis.
- Check image completeness before judging: are the entrance door, stairs, and scenic textures actually rendered? Does a plan/top view mix in other floors or ceiling components, or mistake walled-off floor for empty space? Fix the renderer or change evidence before judging the layout. An apparent obstruction or open area can be an image error rather than a design error.
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

Zone by public/private, active/quiet, and use/service characteristics. List pairs that must adjoin, should be near, should be separated, or have no required relationship. A bubble diagram represents relationships; fit it into the actual shell afterward.[6]

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

Operating areas may overlap at different times, but the use scenario must be stated. Simultaneous queuing, work, and passage cannot share space merely because static outlines do not intersect. Prefer routes around activity groups rather than through conversational centers, without treating every empty area as a corridor.[6]

Dimensions in real-world courses are references tied to human bodies and particular regulations, not hard FFXIV rules. State character scale, comfort goals, and test conditions. Check "can pass," "convenient to operate," and "feels open" separately rather than reducing all three to one corridor width.[6]

### 4.3 Separate arrival, staying, and working

After entering or climbing stairs, provide room to stand, turn, and choose a direction before entering service or seating areas. Waiting guests, bar stools, and restocking routes must not occupy this buffer. Wall displays can provide orientation cues; bookcases and plants are not mandatory in every design.

Do not place seating groups on the entrance axis: a sofa group centered on it reads as a wall of seat backs from the door. Keep a straight route toward a focal view, and face the group's **open side** toward that route. Order private functions by distance **from the actual arrival point**. The first view downstairs should be a focal scene or social area, not a bed. Place the bedroom deepest inside, close it with a real door, and orient the door away from the arrival sightline.

**Emptiness does not establish good circulation.** Negative space should serve orientation, waiting, distribution, access, or breathing room around a focal scene. If large areas have no activity, add complete, distinct functional groups or background layers first, rather than scattering props or automatically centering a table.

**Keep:** activity/adjacency diagrams, primary/secondary routes, arrival areas, principal operating faces, and expected sightlines. Furniture selection need not be complete yet.

## 5. Turn relationships into comparable spatial frameworks

Fit activity areas into actual dimensions, columns/beams, and openings to form a scaled block plan, then test real furniture and activity areas. Compare two or three clearly different alternatives for major structural decisions instead of decorating the first arrangement that fits.[7]

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

Check Item ID, scope, patch, real dimensions, and pivot. Inspect thumbnails and both sides of the native mesh, transparent/open regions, dyeable areas, and support surfaces. If no candidate fits, choose another or revisit zoning; do not silently drop essential functions. Similar names/embeddings do not establish equivalent shape or use.

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

**Keep:** stable instance IDs, roles/groups/dependencies, source assets, positions/facing/heights, and reversible operations. Visually test one representative unit before extending it. Repetition should establish order without copying one seating arrangement throughout the house.

## 7. Resolve plan, elevations, sections, and ceiling together

Fitting the floor plan does not establish a comfortable interior. Elevations resolve openings, cabinetry, and background proportions; sections resolve headroom, levels, sightlines, and hidden volumes. Treat the ceiling as another interface designed with zoning, beams, and lighting.[8]

- **Plan:** relationships between activities and circulation, not just furniture boxes.
- **Vertical:** is everything at floor level or sealed to the ceiling? Check seated and standing sightlines.
- **Backgrounds/backs:** do cabinet backs, false walls, and scenic surfaces look constructed from other zones too?
- **Junctions:** walls, beams, cabinets, frames, and openings need plausible beginnings/endings, compatible seams, material directions, and thicknesses.
- **Hidden volumes:** embedded or cross-floor bodies must not intrude unintentionally elsewhere. Legal overlaps still require checking finished faces.

### Build windows/skylights before adding scenic surfaces

Establish wall/column junctions, continuous ceilings, framing, and recessed openings first. Install the scenic surface afterward and conceal thick edges/backing. A few plants/grilles belong in the foreground. Raising a Phasmascape or dyeing it a similar color can still leave a hanging box. Inspect from the entrance, seats, and upward views rather than hiding it with clipping.[10]

Ceilings affect headroom, native pendant lights, hidden lighting, and cameras. Lowering them may define a zone or feel oppressive; it is not a default for every design. Test representative components, distinguish front/back materials and dye coverage, then extend the order.[8][10]

A shared feature of reference designs is that scenic surfaces appear **behind real openings**, with wall thickness, side returns, sills/railings, and foregrounds. The scene body/frame is concealed behind construction. A scene pasted onto a wall or a pillar-supported box called a skylight reads as an attached panel. Practical sequence:
1. Define the visible opening. Build a false wall with a doorway, arch, or window grid in front of the original wall. Recess the scene behind it and conceal all thick edges/frame.
2. Add a railing or sill within the opening, with side lights/plants to form foreground, middle ground, and distance.
3. Align skylights with native beam grids. If the scenic panel fits a bay, embed it there and dye the frame to match the ceiling so protrusions read as returns. Do not add separate pillars outside the grid.
4. Hide frame/body from entrance, close, and upward views. If it still reads as a flat panel, add depth through recession, sidewalls, or subdivisions rather than more decoration.

**Keep:** coarse placement, major elevation/section relationships, representative normal-eye views, and unresolved junctions. Formal CAD is not required for every design, but three-dimensional thinking is.

## 8. Complete activities before lighting and lived-in detail

Walk through each zone's use scenario against the brief: where people arrive, stand/sit, face, reach, and leave, and what happens when others pass simultaneously. Check essential, supporting, and atmospheric objects separately. More pieces do not establish completeness.

| Zone | Check more than presence |
|---|---|
| Reading/work | Accessible seats, usable surfaces, book/object access, and light; decoration must not occupy the whole desk. |
| Service/bar | Separate guest/work faces, operation/restocking, collection/waiting; provide staff access. |
| Rest/conversation | Shared focus, conversational distance, seat orientation, and backing, rather than pushing all furniture to distant walls. |
| Display | Unobstructed fronts/view cones, room to pause, and no blocked circulation. |
| Storage/doors | Accessible faces, opening/retrieval areas, and operating positions, not just entries in a list. |

Distinguish general orientation lighting, task lighting, and accents; assign separate jobs to hidden sources and visible fixtures. A board's "soft light" must become supported fixtures, surfaces, and source positions. Approximate renderer highlights cannot verify actual game sunlight, shadows, or reflections.[8][10]

Backgrounds stabilize the whole; the use layer supports activities; props describe life. Integrate plants into planting/display structures, support cups/books/lights, and preserve usable counter space. Missing functions need complete groups; missing backgrounds need continuous volumes, not scattered fillers.

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

Borrow its traceable diagnostic format without total-score gates. For each issue, record stable IDs, roles/relationships, rule applicability, geometry/image evidence, known versus inferred status, and whether revision resolves, retains, or introduces it. Complete inventories still require checking usable seats, operating faces, and simultaneous activities. Unknown categories/facing must not pass by default.

- **Reproducibility is not correctness.** Dataset dimensions, co-occurrence, back-to-wall, and face-room-center priors are not requirements for FFXIV scenery. Wall placement and target seats follow this design's intent and the actual asset's forward direction. Common pairings do not justify adding or scaling furniture automatically.
- **A check's name does not establish precision.** SceneCritic Appendix B's True Overlap uses 2D OBBs and SAT, not exact triangles or full 3D game collision. Its orientation aggregation uses any-pass: one applicable subcheck passing does not verify every specified relationship.[11] Retain individual evidence, vertical ranges, intentional compositions, and untested relationships rather than hiding them under one total.
- **Scoring and proposing are different jobs.** The paper found VLM scores sensitive to views/retesting while image feedback still helped correct semantics and facing.[11] Use readable geometry for known facts, and multiple views/model judgment to identify spatial/compositional problems and propose revisions. Unstable image scores do not justify skipping image inspection; a model's orientation complaint does not justify blindly rotating furniture.
- **Check side effects each round.** Compare before/after diagnostics for the same IDs. Fixing one issue must not break support, other seats, openings, or routes. Separate observations, causal hypotheses, and proposed changes.

### 9.2 Choose views according to the question

| View | What to inspect |
|---|---|
| Each floor's overview/diagnostic plan | Zones, density, primary/secondary routes, missing functions, unused areas. |
| Entrance eye level and looking back at the entrance | First impression, turning, orientation, door use, pressure from tall objects. A camera on the threshold cannot see the door itself; pair it with a reverse view and a plan containing the door. |
| Seated/operating/viewing positions | Tables/chairs, work surfaces, backing, sightlines, actual visible content. |
| Final steps, arrival, and after turning | The transition from walking to staying/choosing a route, not just a screenshot of empty floor. |
| Upward, elevations, zone boundaries | Thick skylight frames, beam/wall junctions, cabinet backs, cross-floor intrusions, finishing. |

Normal eye-level views retain the actual ceiling. Top-view clipping is for floor diagnostics only. After structural edits, check that cameras are not inside walls. Mirrored display does not change house coordinates; separate missing materials/permanent structures from design faults first.

Furniture needs access on both sides where its use requires it. Partitions or neighboring pieces must not reduce bed/table/cabinet use faces to slits (9 cm beside a bed or 0.57 m in front of a dressing table are unusable). After an unreachable-object list exposes this, reorganize the whole group rather than nudging it a few centimeters.

### 9.3 Turn feedback into falsifiable revision hypotheses

| Feedback | Diagnose first | Revision level |
|---|---|---|
| Too empty | Missing essential functions, background/vertical layers, group boundaries, or purposeful negative space? | Brief, zones, volumes/groups; not scattered props first. |
| Too crowded | Activity conflicts, oversized objects, blocked sightlines, or oppressive tall boundaries? | Rearrange relationships, change scale/boundaries; not just delete items. |
| Messy/monotonous | Too many focal pieces, fragmentation, conflicting materials/silhouettes, or rhythm-less repetition/heights? | Groups, backgrounds, distinct uses, material hierarchy. |
| Fake | Unsupported objects, wrong facing, surface-only construction, thick exposed frames, or distorted materials/structures in rendering? | Geometry, use relationships, construction, or tool verification. |
| Jarring/pasted on | Scenic/feature pieces not integrated into construction: no wall thickness/opening, exposed frames, isolated supporting pillars? | Build openings and finishing before scenic panels; remove unnecessary supports rather than adding ornaments. |
| Passable but inconvenient | Detours, queues/chair pull-out intrusion, arrival directly into work faces? | Reorganize groups/routes instead of continuing to snake around furniture. |

Make it Home's local translations/rotations and larger swaps inspire layered corrections: decide whether organization or fine adjustment is needed, rather than endlessly nudging coordinates.[2] Record the issue, causal hypothesis, expected improvement, actual evidence, and retain/revert decision. A successful operation is not a reason to defend a failed design.

### 9.4 Comparison and interpretation discipline

For formal layout comparisons, hold the shell, cameras, and evaluation conditions fixed. If assets/materials/light positions also change, describe a comparison of complete proposals rather than attributing differences only to layout. Anonymous A/B and reversed ordering can reduce bias; allow no clear preference or insufficient evidence. This does not require automatic calls to additional paid models.[3][4]

Use "usable / problematic / unidentified / insufficient evidence" per zone. Distinguish unseen from absent. Describe visible evidence without guessing exact dimensions or hidden equipment from images. Architect-Ant Appendix H explicitly limits its visual evaluation to automated image preference, not human research or geometric-validity testing. Different shells and selected samples also affect comparisons.[4]

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

- [ ] Every essential activity in the brief has a corresponding arrangement; functions were not deleted to reduce collisions or increase emptiness.
- [ ] Arrival, orientation, use, and departure are legible; primary routes do not cut through activity cores.
- [ ] The concept changes decisions; groups share a language while supporting distinct uses.
- [ ] Plan, backgrounds, elevations/sections, ceiling, lighting, and details have hierarchy and plausible junctions.
- [ ] Negative space has a purpose and dense areas retain operating space; item counts/scores do not replace judgment.

### Implementation is trustworthy

- [ ] Real MCP state and export match item by item. Check identity, scope, patch, unit scale, finite transforms, and budget.
- [ ] Recheck activity areas, support, and facing after binding actual assets, not just early rectangles.
- [ ] Preserve snapshots/stable IDs. Use revision-guarded atomic batches each round. After timeouts, read back first rather than replaying committed additions.
- [ ] List preview limitations, intentional overlaps/floating, and untested items explicitly. Do not alter unrelated zones/designs.
- [ ] Test entrance/door selection, characters/cameras, stairs, sitting/use, floating persistence after re-entry, and lighting in the target app. Untested is not passed.

### Delivery supports continuation and presentation

Retain a concise brief, proposal tradeoffs, editable object/group dependencies, dimension/facing evidence, representative plans and normal-eye images, necessary ceiling/section notes, and material references. Label each image's purpose, clipped content, and orientation. An approximate perspective is not a scaled construction drawing.[9]

List technical evidence separately: text/schema validity, native-mesh/static-material visibility, specified geometry tests, and app behavior tests. Updating this method does not make old layouts pass new checks automatically. Unretested historical results retain their original scope.

The following is an optional library of in-game construction techniques selected by the problem. Not every design needs them, and they are not newly implemented tool APIs.

## 11. HGXIV construction techniques and design adaptation

This section organizes useful content from the full guide, not one project's history or a requirement to use every trick. Establish purpose/composition before choosing techniques, then assess construction, item slots, and app verifiability.

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
- Hidden sources can sit above ceilings, in corners, or behind scenery; visible fixtures support use/composition. Light should guide entrances, routes, reading surfaces, and focal scenes rather than making the whole house uniformly bright.
- Light/dark surfaces, material reflectance, and source placement jointly affect atmosphere. White walls alone are not completion, and dimness does not require dark wood on every surface.
- HGXIV suggests Metal Work Lantern for white ambient fill, Alchemical Lantern/Assorted Candles for warmth, and Queen's Rest for strong spotlighting. Treat these as candidates to test, not permanently optimal rules; recheck acquisition/version availability.
- Custom pendants can combine candle holders/lanterns; Factory Wall Lamp can be partly embedded; Hingan Chochin Lantern can support slit-light forms. Establish fixture shape and hidden-source positions before testing illumination goals.

### 11.6 Dynamic light, shadows, water light, and platform limits
- Build starry skies from dark backgrounds, moon surfaces/small lights, and varied flickering objects. Keep interior brightness and nearby windows' day/night settings consistent rather than mixing contradictory skies.
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
- For weapon, clothing, or prop displays, hide mannequin bodies, hair/ears/tails, and names, and build plausible mounts/recesses. Objects stuck to walls are not completed displays.
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

This is a task-note format, not an MCP API or a requirement for fixed room/furniture counts.

```markdown
# Interior design working notes

## Program
- Users, activities, duration, simultaneous use:
- Essential/supporting/atmospheric functions; exclusions:
- Success criteria and required evidence:
- Confirmed requirements / provisional assumptions / questions that matter:

## Shell and constraints
- House type, interior style, seed, revision, floors in use:
- Entrance, final stair step/arrival, columns/beams, openings, headroom:
- This style's stair landing, enclosed/usable under-stair areas, walled-off floor (re-read after style selection):
- Render completeness: doors, stairs, scenic textures, other floors/ceiling parts mixed into plans:
- Fixed / replaceable / coverable / unverified:
- Patch/scope/whole-house budget and tool limitations:

## Parti and expression
- One-sentence organizing concept:
- Zoning, sections/sightlines, lighting, and material decisions it actually changes:
- Atmosphere references and available material/furniture boards:

## Relationships and alternative frameworks
- Activity zones; must adjoin / preferably near / separated:
- Primary/secondary routes, arrival/staying, service routes:
- Major A/B alternatives (more if needed), differences, costs, selection reasons:

## Furniture and activity relationship worksheet
- Requirement → zone → group/stable instance ID → usability evidence:
- Anchors, real assets/Item IDs, dimensions, pivots, facing/confidence:
- Use/operating areas, visible faces, target seats:
- Support parent/surface/children; dependencies for group moves:
- Legal overlap/embedding pairs, purpose, finished faces, cross-floor bodies:
- World coordinates/heights, export scale, display mirroring:

## This iteration's hypotheses and operations
- View/use scenario exposing the issue:
- Suspected cause; brief / zones / groups / construction / detail / tool layer to revise:
- Expected improvement and relationships to preserve:
- Snapshot, expected revision, committed operations; read back after timeouts:
- Observed/measured change; retain / revert / unresolved:
- Same-ID diagnostics: resolved / persistent / new; side effects on other relationships:

## Separate acceptance checks
- Technical: identity, patch, budget, transforms, support/unintended collision:
- Functions: each essential zone = usable / problematic / unidentified / insufficient evidence:
- Activity: arrival, operation, simultaneous use, departure; not just centerlines:
- Visual: concept, groups, backgrounds, ceiling/elevations/sections, hierarchy, junctions:
- Geometry test conditions: width/height, obstacles/exclusions, native stairs, scope:
- Views: normal-eye / overview / clipped diagnostic purposes; uncertainties/render gaps:
- If A/B: which shell/cameras/assets/lighting are fixed or different:
- Aesthetic preference with reasons / no clear preference / cannot judge; no inference of 3D function:

## Delivery and continuation
- Final state/export revisions and item-by-item read-back evidence:
- Verified / unverified / requiring app interaction or re-entry:
- Main tradeoffs, representative images, recoverable revisions, remaining issues:
- Quota and per-design MCP shutdown evidence:
```

**Core sequence: establish activities and spatial relationships first, then real furniture, the third dimension, and construction; use details to reinforce the whole last. Verify every layer with appropriate evidence.**

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
