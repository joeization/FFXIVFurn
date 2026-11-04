"""Candidate selection by a text model, in zone-sized batches. The model sees the top-k candidates per plan entry and DECIDES:
which distinct candidates to use (any number of them), how many of each, or none. Never Opus.

Reply per entry: {"entry":int,"picks":[{"i":candidate index,"count":int>=1}],"why":str}   (picks may be empty = none acceptable).
Legacy single-pick replies {"entry":int,"pick":int|null} still work (count = the planned count).
"""
from __future__ import annotations
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .plan import MODEL, call_agy, parse_json_reply

CHUNK = 12   # entries per model call; only keeps each prompt readable (top-k candidates are long), it does not limit the plan


def build_prompt(plan, resolved):
    entries = []
    for k, r in enumerate(resolved):
        entries.append({'entry': k, 'zone': r['zone'], 'role': r['role'], 'wanted': r['query'], 'planned_count': r['count'],
                        'candidates': [{'i': i, **{x: o.get(x) for x in ('name', 'category', 'size_m', 'placement', 'colour', 'shelf_boards', 'matches_role_category', 'description', 'tags')}} for i, o in enumerate(r['options'])]})
    concept = plan.get('concept') or {}
    extra = f"\nOverall direction: style {concept.get('style_keywords')}, palette {concept.get('palette')}, mood {concept.get('mood')}, density intent {concept.get('density_intent')}." if concept else ''
    return f"""You are choosing furniture for an FFXIV room themed: {plan['title']} - {plan['theme']}.{extra}
Each entry lists the top candidates found for what the designer wanted. YOU decide what goes into the room:
- pick any number of DIFFERENT candidates and give each its own count (e.g. a bookshelf wall = several different shelves side by side, not one shelf copied);
- planned_count is only the designer's suggestion; use more or fewer if the design benefits, or pick none if nothing fits (none beats a bad match);
- judge colour (the measured 'colour' of the texture is given: keep to the palette), material, style, and for shelves/cabinets prefer pieces with several shelf_boards when props will be placed on them; real size (size_m = length, width, height in metres) and placement for the role; candidates outside the role's usual category are flagged by matches_role_category.
Do not invent candidates. Reply with ONLY a JSON array covering every entry once:
[{{"entry":int,"picks":[{{"i":int,"count":int}}],"why":"short"}}]
{json.dumps(entries, ensure_ascii=False)}"""


def _picks_of(x, planned, n_options):
    if 'picks' in x:
        raw = x['picks']
        if not isinstance(raw, list): raise ValueError('picks must be a list')
    else:   # legacy {"pick": i|null}
        p = x.get('pick'); raw = [] if p is None else [{'i': p, 'count': planned}]
    seen, out = set(), []
    for pk in raw:
        i, n = pk.get('i'), pk.get('count', 1)
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < n_options: raise ValueError(f'bad candidate index {i} for entry {x["entry"]}')
        if isinstance(n, bool) or not isinstance(n, int) or n < 1: raise ValueError(f'bad count {n} for entry {x["entry"]}')
        if i in seen: raise ValueError(f'candidate {i} listed twice for entry {x["entry"]}; give one pick with the total count')
        seen.add(i); out.append((i, n))
    return out


def apply_picks(resolved, arr):
    """Validate a model reply against the candidate lists and expand it: one resolved entry per distinct chosen candidate."""
    if not isinstance(arr, list) or sorted(x['entry'] for x in arr) != list(range(len(resolved))): raise ValueError('entries must cover each index once')
    kept, report = [], []
    for x in sorted(arr, key=lambda x: x['entry']):
        r = resolved[x['entry']]; picks = _picks_of(x, r['count'], len(r['options'])); why = str(x.get('why', ''))[:200]
        if not picks:
            report.append({'zone': r['zone'], 'wanted': r['query'], 'planned_count': r['count'], 'picks': [], 'why': why, 'was': r['geometry']['name']}); continue
        names = []
        for i, n in picks:
            o = r['options'][i]; kept.append({**r, 'item_id': o['item_id'], 'geometry': o['geometry'], 'similarity': o['similarity'], 'count': n, 'candidate_rank': i}); names.append((o['name'], n))
        report.append({'zone': r['zone'], 'wanted': r['query'], 'planned_count': r['count'], 'picks': [{'name': a, 'count': b} for a, b in names], 'distinct': len(names),
                       'total': sum(b for _, b in names), 'why': why, 'was': r['geometry']['name']})
    return kept, report


def rerank_from_file(resolved, path):
    """Apply a reply written by any other model (plain JSON array, optional ``` fence)."""
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', Path(path).read_text(encoding='utf-8').strip()).strip()
    return apply_picks(resolved, json.loads(text))


def _chunk(plan, sub, out_dir, tag, model, attempts=2):
    prompt = build_prompt(plan, sub); (out_dir / f'rerank-request-{tag}.txt').write_text(prompt, encoding='utf-8'); err = ''
    for a in range(attempts):
        stdout, stderr = call_agy(prompt + (f'\nPrevious reply rejected: {err}. Fix it.' if err else ''), model=model, workdir=out_dir, name=f'rerank-prompt-{tag}-attempt{a}')
        (out_dir / f'rerank-response-{tag}-attempt{a}.json').write_text(stdout + '\n---STDERR---\n' + stderr, encoding='utf-8')
        try: return apply_picks(sub, parse_json_reply(stdout))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e: err = str(e)[:200]
    raise RuntimeError(f'Rerank {tag} rejected after retries: {err}')


def rerank(plan, resolved, out_dir, *, model=MODEL, attempts=2, workers=3):
    """Split by zone (and into CHUNK-sized pieces), select in parallel, keep the plan order."""
    out_dir = Path(out_dir); groups = []; by_zone = {}
    for r in resolved: by_zone.setdefault(r['zone_index'], []).append(r)
    for zi, rs in sorted(by_zone.items()):
        for k in range(0, len(rs), CHUNK): groups.append((f'z{zi:02d}-{k // CHUNK:02d}', rs[k:k + CHUNK]))
    with ThreadPoolExecutor(workers) as ex: results = list(ex.map(lambda g: _chunk(plan, g[1], out_dir, g[0], model, attempts), groups))
    kept, report = [], []
    for k, rep in results: kept += k; report += rep
    return kept, report
