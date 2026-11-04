"""Two-level planning by a text model: (1) overall design direction + zone partition, (2) one detailing call per zone.

No artificial limits on zones, entries or counts. The only hard bound is the game's own furnishing cap, which the model is TOLD as a fact.
Room facts (measured floor area, stairs, ceiling) are given so the model can judge how full the room should be. Never Opus.
"""
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .plan import MODEL, ROLES, call_agy, parse_json_reply, validate_plan

LAYERS = ('architecture (partitions, pillars, screens, frames from the Fixture category) -> main furniture groups -> rugs -> surface props on tables -> '
          'wall decor (scrolls, frames, shelves) -> lights at several heights (floor, table, wall, hanging) -> plants and small accents')


def room_facts(room, free_area, keepout_area, house_size, game_cap):
    (x0, y0), (x1, y1) = room['min'], room['max']
    return {'house_size': house_size, 'ground_floor_area_m2': round(room['polygon'].area, 1), 'free_area_after_stairs_m2': round(free_area, 1), 'stairs_keepout_area_m2': round(keepout_area, 1),
            'bounding_box_m': [round(x1 - x0, 1), round(y1 - y0, 1)], 'ceiling_height_m': room['ceiling_z'], 'floor_shape': 'L-shaped (a corner is missing); two staircases (up and down to basement) occupy part of the floor',
            'game_cap_instances_for_whole_house': game_cap}


def concept_prompt(request, facts, categories, tag_examples):
    return f"""You are the lead interior designer for an FFXIV house. Decide the OVERALL DESIGN DIRECTION for ONE ground floor; detailed furnishing is done afterwards, zone by zone.
Request: {request}
Measured facts: {json.dumps(facts)}
The game allows {facts['game_cap_instances_for_whole_house']} furniture instances for the whole house. That is a rule, not a target: decide yourself how full the room should be.
Players who build showcase rooms often use most of the allowance, layer the room ({LAYERS}) and treat Fixture items as architecture; decide what this concept needs.
Design the SPACE before the furniture: professional FFXIV rooms are divided into rooms-within-the-room with partitions, arches, pillars and screens (Fixture items), have 1-2 sight lines that end on a focal piece, and repeat a few motifs on purpose.
Fill "spatial_structure" accordingly. Every zone should be a composed scene (vignettes), not a list of loose items. A reviewer will later LOOK at renders of the finished room and judge it as a designer would (clutter, focal points, rhythm, walkability), so plan for that: say where the room stays open and what repeats on purpose.
Reply with ONLY one JSON object (no markdown):
{{"title":str,"theme":str,"style_keywords":[str],"palette":[str],"mood":str,
 "density_intent":"sparse|balanced|rich|maximal","density_reason":str,"target_instances_estimate":int,
 "focal_points":[str],"circulation_plan":"where people walk and which areas stay deliberately open","negative_space":"how much emptiness each area keeps and why","rhythm":"what repeats and how it varies (a row of identical pieces should have a reason)",
 "spatial_structure":{{"partitions":["where dividing walls/arches/screens go and what they separate"],"sight_lines":["from where to where, ending at which focal piece"],"symmetry_axes":["optional"],"motifs":["what repeats on purpose"]}},
 "lighting_plan":"light sources at several heights: ceiling/hanging, wall, table, floor","architecture_ideas":[str],
 "fixtures":{{"floor":"English query for the floor material","wall":"English query for the wallpaper","light":"English query for the ceiling light"}},
 "zones":[{{"name":str,"purpose":str,"character":str,"area_fraction":number>0,"region":"north|south|east|west|center|northeast|northwest|southeast|southwest (where in the floor plan this zone should sit; the L-shaped floor and stairs are in the facts)","adjacent_to":[zone names],"is_focal":bool}}]}}
Use as many zones as the room needs; area_fraction values are relative shares of the usable floor. Write queries in plain English describing appearance.
Furniture categories that exist: {', '.join(categories)}. Optional tag keys look like: {', '.join(tag_examples)}."""


def zone_prompt(request, concept, zone, facts, zone_area, categories, tag_examples, budget):
    others = [{'name': z['name'], 'purpose': z.get('purpose', '')} for z in concept['zones'] if z['name'] != zone['name']]
    brief = {k: concept.get(k) for k in ('title', 'theme', 'style_keywords', 'palette', 'mood', 'density_intent', 'focal_points', 'circulation_plan', 'negative_space', 'rhythm', 'spatial_structure', 'lighting_plan', 'architecture_ideas')}
    return f"""You are the interior designer detailing ONE zone of a room whose overall direction is already decided.
Original request: {request}
Overall direction: {json.dumps(brief, ensure_ascii=False)}
Your zone: {json.dumps(zone, ensure_ascii=False)}  (about {zone_area:.0f} m2 of floor; ceiling {facts['ceiling_height_m']} m)
Other zones (they furnish themselves, do not duplicate them): {json.dumps(others, ensure_ascii=False)}
The whole house is capped by the game at {facts['game_cap_instances_for_whole_house']} instances (a rule, not a target), shared between zones by floor area: your zone's share is at most {budget} instances in total (sum of counts). The overall intent is "{concept.get('density_intent')}" with an estimate of {concept.get('target_instances_estimate')} instances for the whole room; use as much or as little of your share as the design needs.
List EVERYTHING this zone needs, layered: {LAYERS}. Roles: {list(ROLES)}. Be specific: each entry is one kind of item with a count, described by appearance (colour, material, shape, style) in plain English.
Surface props (books, tea sets, vases) use role "decor"; hanging scrolls/frames use "wall-art"; Fixture-type partitions/pillars/screens use "architecture".
COMPOSE IN VIGNETTES. A vignette is an anchor piece plus the things that belong with it, placed relative to it. Give every member of a vignette the same "group" name; the anchor has "relation":"anchor" (or none) and each other member says where it goes:
  "flank" (symmetric pairs on both sides, e.g. two planters beside a bookshelf), "left", "right", "front" (faces the anchor, e.g. a chair at a desk), "behind", "around" (ring, e.g. cushions round a low table),
  "on_top" (props on the anchor's surfaces: with several shelf boards the members are spread across the boards, so give a bookshelf 5-10 small props), "above" (wall decor hung over the anchor), optional "gap_m".
Examples: bookshelf (anchor) + 2 tall planters (flank) + 6 books/vases (on_top) + a scroll (above); low table (anchor) + 4 cushions (around) + tea set (on_top) + lantern (left).
Surfaces matter: every table, counter, shelf and sill in a good room carries something. Light at several heights (hanging/ceiling, wall, table, floor) and plants at several heights (hanging, floor, tabletop).
Partitions and arches (role architecture) should form continuous lines: use "arrangement":"line" or "wall_row" with spacing_m, and a facing that matches the line; do not scatter them.
Placement is YOURS to direct. Each item may also carry optional placement intent (omit for the engine's sensible default):
  "arrangement": "scatter" | "wall_row" (copies side by side along one wall) | "ring" (around the zone's table or centre) | "grid" | "corner" | "cluster" | "line"
  "wall": "N"|"E"|"S"|"W" (for wall_row / items that should hug a particular wall; N is +y, E is +x)
  "facing": "wall" (back to the wall, front into the room) | "center" (toward the zone centre) | "along_wall" | "perpendicular_to_wall" | "outward" | "alternate" (alternating 0/90 degrees) | "random" | "N"|"E"|"S"|"W" | degrees (0 = east/+x, 90 = north/+y)
  "spacing_m": gap between copies in metres (negative = deliberate overlap)
  "group": vignette name, "relation": see above, "gap_m": metres to the anchor (default 0.08)
  "allow_overlap": true when pieces may overlap each other or other furniture (FFXIV allows overlapping and layering; use it for screens in front of walls, plants tucked into shelves, lights inside furniture, stacked decor).
Vary orientation on purpose: a row of screens all facing the same way looks mechanical; alternate, angle or stagger them when the design wants rhythm.
Reply with ONLY JSON: {{"items":[{{"role":one of {list(ROLES)},"query":str,"count":int>=1,"tags":[optional tag keys],"arrangement":optional,"wall":optional,"group":optional,"relation":optional,"gap_m":optional,"facing":optional,"spacing_m":optional,"allow_overlap":optional,"why":str}}]}}
Optional tag keys look like: {', '.join(tag_examples)}."""


def _call(prompt, out_dir, tag, model, check, attempts=2):
    err = ''
    for a in range(attempts):
        p = prompt if not err else prompt + f'\nYour previous reply was rejected: {err}. Fix it and reply with the JSON only.'
        stdout, stderr = call_agy(p, model=model, workdir=out_dir, name=f'{tag}-prompt-attempt{a}')
        (out_dir / f'{tag}-response-attempt{a}.json').write_text(stdout + '\n---STDERR---\n' + stderr, encoding='utf-8')
        try: return check(parse_json_reply(stdout))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e: err = str(e)[:300]
    raise RuntimeError(f'{tag} rejected after retries: {err}')


SANITIZED = []   # (where, original, cleaned) recorded for the report


def clean_query(q, where):
    """Drop non-Latin letters a model slipped into an English query (e.g. a CJK word next to its English gloss); empty result is an error."""
    if not isinstance(q, str): return q
    c = ' '.join(''.join(ch for ch in q if not (ch.isalpha() and ord(ch) > 0x24F)).split())
    if c != q.strip():
        if not c: raise ValueError(f'query {q!r} has no English words; write it in English')
        SANITIZED.append({'where': where, 'original': q, 'cleaned': c})
    return c


def check_concept(c):
    if not isinstance(c, dict) or not isinstance(c.get('zones'), list) or not c['zones']: raise ValueError('concept needs zones')
    fx = c.get('fixtures')
    if not isinstance(fx, dict) or set(fx) != {'floor', 'wall', 'light'}: raise ValueError('concept needs fixtures floor/wall/light')
    names = set()
    for z in c['zones']:
        if not isinstance(z.get('name'), str) or not z['name'].strip() or z['name'] in names: raise ValueError('zones need unique names')
        names.add(z['name']); f = z.get('area_fraction')
        if isinstance(f, bool) or not isinstance(f, (int, float)) or f <= 0: raise ValueError('area_fraction must be > 0')
    for k, v in list(fx.items()): fx[k] = clean_query(v, f'concept.fixtures.{k}')
    return c


def request_hierarchical_plan(request, out_dir, *, facts, categories, tag_examples, vocab_keys, model=MODEL, workers=3):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True); cap = facts['game_cap_instances_for_whole_house']
    prompt = concept_prompt(request, facts, categories, tag_examples); (out_dir / 'concept-request.txt').write_text(prompt, encoding='utf-8')
    concept = _call(prompt, out_dir, 'concept', model, check_concept)
    (out_dir / 'concept.json').write_text(json.dumps(concept, ensure_ascii=False, indent=1), encoding='utf-8')
    total = sum(z['area_fraction'] for z in concept['zones']); free = facts['free_area_after_stairs_m2']
    def detail(item):
        i, z = item; share = z['area_fraction'] / total; area = free * share; budget = max(1, int(cap * share))   # the game cap is shared between zones by floor area
        p = zone_prompt(request, concept, z, facts, area, categories, tag_examples, budget)
        (out_dir / f'zone{i:02d}-request.txt').write_text(p, encoding='utf-8')
        def check(obj):
            if not isinstance(obj, dict) or not isinstance(obj.get('items'), list) or not obj['items']: raise ValueError('reply must be {"items":[...]} with at least one item')
            for it in obj['items']:
                if isinstance(it, dict): it['query'] = clean_query(it.get('query'), z['name'])
            probe = {'title': 't', 'theme': 't', 'used_floors': ['ground'], 'fixtures': concept['fixtures'], 'zones': [{'name': z['name'], 'area_fraction': 1, 'items': obj['items']}]}
            validate_plan(probe, vocab_keys=vocab_keys, max_items=budget); return obj['items']
        return _call(p, out_dir, f'zone{i:02d}', model, check)
    with ThreadPoolExecutor(workers) as ex: items = list(ex.map(detail, list(enumerate(concept['zones']))))
    zones = [{'name': z['name'], 'purpose': z.get('purpose', ''), 'character': z.get('character', ''), 'area_fraction': z['area_fraction'] / total, **({'region': z['region']} if z.get('region') else {}), 'items': its} for z, its in zip(concept['zones'], items)]   # model gives relative shares; validate_plan wants 0..1
    plan = {'title': concept.get('title', ''), 'theme': concept.get('theme', ''), 'used_floors': ['ground'], 'fixtures': concept['fixtures'], 'zones': zones, 'concept': {k: v for k, v in concept.items() if k not in ('zones', 'fixtures')}}
    plan = validate_plan(plan, vocab_keys=vocab_keys, max_items=cap); plan['model'] = model
    if SANITIZED: plan['sanitized_queries'] = list(SANITIZED); (out_dir / 'sanitized-queries.json').write_text(json.dumps(SANITIZED, ensure_ascii=False, indent=1), encoding='utf-8')
    return plan
