"""Structured design plan: schema, strict validation, and the agy (Gemini Flash) request. Never Opus."""
from __future__ import annotations
import json, re, shutil, subprocess
from pathlib import Path

ROLES = ('seating', 'table', 'storage', 'rug', 'wall-art', 'lighting', 'decor', 'architecture')   # architecture = partitions, pillars, screens, frames (Fixture category)
FACINGS = ('wall', 'center', 'along_wall', 'perpendicular_to_wall', 'outward', 'alternate', 'random')   # or a compass letter N/E/S/W or a number of degrees (world, 0 = +x/east, 90 = +y/north)
RELATIONS = ('anchor', 'flank', 'left', 'right', 'front', 'behind', 'on_top', 'above', 'around')   # placement of a group member relative to the group's anchor piece
ARRANGEMENTS = ('scatter', 'wall_row', 'ring', 'grid', 'corner', 'cluster', 'line')
COMPASS = {'E': 0, 'N': 90, 'W': 180, 'S': 270}
REGIONS = ('north', 'south', 'east', 'west', 'center', 'northeast', 'northwest', 'southeast', 'southwest')


def clean_placement(e, where='item'):
    """Optional model-chosen placement intent. Unknown or malformed values are dropped (with a note), never fatal and never a limit."""
    out, notes = {}, []
    f = e.get('facing')
    if isinstance(f, str) and f.strip():
        f = f.strip()
        if f.lower() in FACINGS: out['facing'] = f.lower()
        elif f.upper() in COMPASS: out['facing'] = f.upper()
        else:
            try: out['facing'] = float(f) % 360
            except ValueError: notes.append(f'facing {f!r}')
    elif isinstance(f, (int, float)) and not isinstance(f, bool): out['facing'] = float(f) % 360
    elif f is not None: notes.append(f'facing {f!r}')
    a = e.get('arrangement')
    if a is not None:
        if isinstance(a, str) and a.lower() in ARRANGEMENTS: out['arrangement'] = a.lower()
        else: notes.append(f'arrangement {a!r}')
    w = e.get('wall')
    if w is not None:
        if isinstance(w, str) and w.upper() in COMPASS: out['wall'] = w.upper()
        else: notes.append(f'wall {w!r}')
    sp = e.get('spacing_m')
    if sp is not None:
        if isinstance(sp, (int, float)) and not isinstance(sp, bool): out['spacing_m'] = float(sp)
        else: notes.append(f'spacing_m {sp!r}')
    g = e.get('group')
    if g is not None:
        if isinstance(g, str) and g.strip(): out['group'] = g.strip()[:40]
        else: notes.append(f'group {g!r}')
    rel = e.get('relation')
    if rel is not None:
        if isinstance(rel, str) and rel.lower() in RELATIONS: out['relation'] = rel.lower()
        else: notes.append(f'relation {rel!r}')
    gp = e.get('gap_m')
    if gp is not None:
        if isinstance(gp, (int, float)) and not isinstance(gp, bool): out['gap_m'] = float(gp)
        else: notes.append(f'gap_m {gp!r}')
    ov = e.get('allow_overlap')
    if ov is not None:
        if isinstance(ov, bool): out['allow_overlap'] = ov
        else: notes.append(f'allow_overlap {ov!r}')
    return out, [f'{where}: {n}' for n in notes]


FLOORS = ('ground',)  # multi-floor placement needs measured per-floor heights (not available yet)
MODEL = 'gemini-3.8-flash-medium'
# No artificial limits on zones / entries / counts: the model decides. The only hard bound is the game's own furnishing cap (max_items).


def validate_plan(plan, *, vocab_keys, max_items):
    """Return a normalised copy or raise ValueError. Unknown tag keys are dropped (recorded), never invented."""
    if not isinstance(plan, dict): raise ValueError('plan must be an object')
    out = {'title': str(plan.get('title', ''))[:160], 'theme': str(plan.get('theme', ''))[:600], 'dropped_tags': []}
    if isinstance(plan.get('concept'), dict): out['concept'] = plan['concept']   # overall design direction, kept for the critic and the report
    floors = plan.get('used_floors', ['ground'])
    if not isinstance(floors, list) or 'ground' not in floors or not set(floors) <= set(FLOORS):
        raise ValueError(f'used_floors must be {list(FLOORS)} for now (per-floor heights are not measured)')
    out['used_floors'] = ['ground']
    fx = plan.get('fixtures')
    if not isinstance(fx, dict) or set(fx) != {'floor', 'wall', 'light'} or not all(isinstance(v, str) and v.strip() for v in fx.values()):
        raise ValueError('fixtures needs non-empty English queries: floor, wall, light')
    out['fixtures'] = {k: fx[k].strip()[:200] for k in ('floor', 'wall', 'light')}
    zones = plan.get('zones')
    if not isinstance(zones, list) or not zones: raise ValueError('at least one zone required')
    out['zones'] = []; total = 0
    for z in zones:
        if not isinstance(z, dict) or not isinstance(z.get('name'), str) or not z['name'].strip(): raise ValueError('zone needs a name')
        frac = z.get('area_fraction', 1 / len(zones))
        if isinstance(frac, bool) or not isinstance(frac, (int, float)) or not 0 < frac <= 1: raise ValueError('area_fraction must be in (0,1]')
        entries = z.get('items')
        if not isinstance(entries, list) or not entries: raise ValueError(f'zone {z["name"]!r} needs at least one item')
        ne = []
        for e in entries:
            if not isinstance(e, dict) or e.get('role') not in ROLES: raise ValueError(f'item role must be one of {ROLES}')
            q = e.get('query')
            if not isinstance(q, str) or not q.strip(): raise ValueError('item query must be English text')
            if any(ch.isalpha() and ord(ch) > 0x24F for ch in q): raise ValueError('item query must be English (non-Latin script rejected)')
            n = e.get('count', 1)
            if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= max_items: raise ValueError(f'count must be 1..{max_items} (the game cap)')
            tags = []
            for t in e.get('tags', []) if isinstance(e.get('tags', []), list) else []:
                (tags if t in vocab_keys else out['dropped_tags']).append(t)
            pl, notes = clean_placement(e, f'{z["name"]}/{q.strip()[:30]}'); out['dropped_tags'] += []; out.setdefault('dropped_placement', []).extend(notes)
            total += n; ne.append({'role': e['role'], 'query': q.strip()[:200], 'count': n, 'tags': tags[:6], **({'placement': pl} if pl else {})})
        out['zones'].append({'name': z['name'].strip()[:80], 'purpose': str(z.get('purpose', ''))[:400], 'area_fraction': float(frac), 'items': ne, **({'region': z['region'].lower()} if isinstance(z.get('region'), str) and z['region'].lower() in REGIONS else {}), **({'character': str(z['character'])[:400]} if z.get('character') else {})})
    if total > max_items: raise ValueError(f'plan asks for {total} instances > the game cap {max_items}')
    s = sum(z['area_fraction'] for z in out['zones'])
    for z in out['zones']: z['area_fraction'] /= s
    out['planned_instances'] = total
    return out


def build_prompt(request, *, house_size, max_items, categories, tag_examples):
    return f"""You are an interior designer planning ONE ground-floor room for an FFXIV house. Reply with ONLY one JSON object, no markdown.
Request: {request}
House size: {house_size}. The game allows at most {max_items} furniture instances for the whole house (a rule, not a target: decide how full the room should be). Only the ground floor is supported.
Write every query in plain English describing visible appearance (colour, material, shape, style, e.g. "dark wood round dining table", "soft green sofa with cushions").
JSON shape:
{{"title":str,"theme":str,"used_floors":["ground"],
 "fixtures":{{"floor":"query for floor material","wall":"query for wallpaper","light":"query for ceiling light"}},
 "zones":[{{"name":str,"purpose":str,"area_fraction":0-1,
   "items":[{{"role":one of {list(ROLES)},"query":str,"count":int>=1,"tags":[optional keys from the examples]}}]}}]}}
Rules: as many zones and items as the design needs; layer the room (architecture, main furniture, surface props, wall decor, lights at several heights, plants); rugs go under seating/table groups;
keep a coherent single theme. Optional tag keys look like: {', '.join(tag_examples)}.
Furniture categories that exist: {', '.join(categories)}."""


def call_agy(prompt, *, model=MODEL, timeout=420, workdir=None, name='prompt'):
    exe = shutil.which('agy')
    if exe is None: raise RuntimeError('agy CLI not found')
    extra = []
    if len(prompt) > 6000:  # Windows command line limit (WinError 206): hand the prompt over as a file
        if workdir is None: raise ValueError('long prompt needs a workdir')
        f = Path(workdir) / f'{name}.txt'; f.write_text(prompt, encoding='utf-8')
        prompt = f'Read the file {f.resolve()} with your file-read tool (do not run shell commands) and follow its instructions exactly. Reply with ONLY what it asks for.'
        extra = ['--add-dir', str(Path(workdir).resolve())]
    r = subprocess.run([exe, '-p', prompt, *extra, '--model', model, '--output-format', 'json', '--print-timeout', f'{timeout - 30}s'],
                       capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    return r.stdout, r.stderr


def parse_json_reply(stdout):
    text = (json.loads(stdout).get('response') or '').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text).strip()
    return json.loads(text)


def request_plan(request, out_dir, *, house_size, max_items, categories, tag_examples, vocab_keys, model=MODEL, attempts=2):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(request, house_size=house_size, max_items=max_items, categories=categories, tag_examples=tag_examples)
    (out_dir / 'plan-request.txt').write_text(prompt, encoding='utf-8'); err = ''
    for i in range(attempts):
        p = prompt if not err else prompt + f'\nYour previous reply was rejected: {err}. Fix it and reply with the JSON only.'
        stdout, stderr = call_agy(p, model=model, workdir=out_dir, name=f'plan-prompt-attempt{i}')
        (out_dir / f'plan-response-attempt{i}.json').write_text(stdout + '\n---STDERR---\n' + stderr, encoding='utf-8')
        try:
            raw = parse_json_reply(stdout); plan = validate_plan(raw, vocab_keys=vocab_keys, max_items=max_items)
            plan['model'] = model; return plan
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            err = str(e)[:300]
    raise RuntimeError('Model plan rejected after retries: ' + err)
