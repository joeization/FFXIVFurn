"""Multi-round, model-judged refinement. NO score decides anything.

Each round: render the CURRENT layout (unmirrored, so image axes == JSON axes) -> the reviewing model looks at the pictures, says whether the room is good,
what is wrong, and proposes edits -> edits are applied unless they break physics (inside the floor, outside stair bodies, ...) -> render again, until the
model says "good", nothing changes, or the round limit is reached. The model sees its previous round (what it changed, what was refused, and the previous
pictures) so it can tell whether a change helped. Raw requests/responses are kept. Never Opus.

External models (not agy) use a file protocol: round-N-request.txt is written, the run stops until round-N-reply.json exists, then re-run to continue.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from .plan import MODEL, call_agy, parse_json_reply
from . import refine as R
from .layout_io import export_layout, write_layout

MAX_MOVE_HINT = 6.0
ZONE_VIEWS = 4


class WaitingForReply(Exception):
    pass


def zone_cameras(objs, limit=6):
    """Close-up cameras: one per zone (largest zones first), elevated, looking at the zone's furniture from the south-west (walls are hidden in cutaway views)."""
    zones = {}
    for o in objs:
        if o.removed or o.layer == 'rug': continue
        c = o.poly.centroid; zones.setdefault(o.p['zone'], []).append((c.x, c.y))
    cams = []
    for name, pts in sorted(zones.items(), key=lambda kv: -len(kv[1]))[:limit]:
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        cams.append({'name': f'zone: {name}'[:40], 'position': [cx - 4.2, cy - 4.2, 4.6], 'target': [cx, cy, 0.7], 'fov': 60, 'cutaway': True})
    return cams


def _render_job(args):
    """Runs in its own process so the three view groups render in parallel."""
    layout_path, out, kw = args
    from ..rendering.pipeline import run_pipeline
    run_pipeline(layout_path, out, artifacts=True, **kw)  # review/resume explicitly consumes diagnostic metadata
    return str(out)


def render_round(layout_path, out, objs, *, root, state=None):
    """Renders unmirrored views for the model, the three groups in parallel processes. Returns [(caption, path)].
    Each view costs minutes on a full room, so only what the reviewer uses is rendered: the top view, overview + entry, and close-ups of the biggest zones.
    `state` carries the overview/entry cameras chosen in round 1 so later rounds skip the corner search."""
    from concurrent.futures import ProcessPoolExecutor
    out = Path(out); state = state if state is not None else {}
    common = dict(db_path=root / 'data/furniture.sqlite3', room_context=True, rough_room_finish=True, approximate_tint=False, mirror_view=False, labels=True)
    jobs = []
    if not (out / 'three' / 'manifest.json').exists(): jobs.append((layout_path, out / 'three', dict(three_view=True, view_names=['top'], size=(960, 640), **common)))
    if not (out / 'main' / 'manifest.json').exists():
        if state.get('main_cameras'): jobs.append((layout_path, out / 'main', dict(cameras=state['main_cameras'], size=(960, 640), **common)))
        else: jobs.append((layout_path, out / 'main', dict(view_names=['overview', 'entry'], size=(960, 640), **common)))
    cams = zone_cameras(objs, limit=ZONE_VIEWS)
    if cams and not (out / 'zones' / 'manifest.json').exists(): jobs.append((layout_path, out / 'zones', dict(cameras=cams, size=(800, 540), **common)))
    if len(jobs) > 1:
        with ProcessPoolExecutor(len(jobs)) as ex: list(ex.map(_render_job, jobs))
    elif jobs: _render_job(jobs[0])
    files = []
    top = out / 'three' / 'view-01-labeled.png'
    if top.exists(): files.append(('TOP view (+x right, +y up; walls hidden)', str(top.resolve())))
    m = json.loads((out / 'main' / 'manifest.json').read_text(encoding='utf-8'))
    state.setdefault('main_cameras', [v['camera'] for v in m['views']])
    for k, v in enumerate(m['views'], 1):
        p = out / 'main' / f'view-{k:02d}-labeled.png'
        if p.exists(): files.append((f"{v['camera'].get('name', k)} view", str(p.resolve())))
    for k, c in enumerate(cams, 1):
        p = out / 'zones' / f'view-{k:02d}-labeled.png'
        if p.exists(): files.append((f"{c['name']} (close-up)", str(p.resolve())))
    return files


def furniture_rows(objs):
    rows = []
    for o in objs:
        if o.removed: continue
        b = o.poly.bounds
        rows.append({'id': o.i, 'zone': o.p['zone'], 'name': o.item['name'], 'role': o.role, 'layer': o.layer, 'x': round(o.poly.centroid.x, 2), 'y': round(o.poly.centroid.y, 2),
                     'yaw_deg': round(o.yaw, 1), 'faces_deg': round(o.facing, 1), 'size_m': [round(b[2] - b[0], 2), round(b[3] - b[1], 2), round(o.item['height'], 2)]})
    return rows


def _cached_files(out_dir):
    out_dir = Path(out_dir); files = []
    top = out_dir / 'three' / 'view-01-labeled.png'
    if top.exists(): files.append(('TOP view (+x right, +y up; walls hidden)', str(top.resolve())))
    m = json.loads((out_dir / 'main' / 'manifest.json').read_text(encoding='utf-8'))
    for k, v in enumerate(m['views'], 1):
        p = out_dir / 'main' / f'view-{k:02d}-labeled.png'
        if p.exists(): files.append((f"{v['camera'].get('name', k)} view", str(p.resolve())))
    for k in range(1, 9):
        p = out_dir / 'zones' / f'view-{k:02d}-labeled.png'
        if p.exists(): files.append((f'close-up {k}', str(p.resolve())))
    return files


def build_prompt(n, rounds, request, plan, objs, files, house_size, facts, history, prev_files):
    concept = (plan or {}).get('concept') or {}
    brief = json.dumps({k: concept.get(k) for k in ('style_keywords', 'palette', 'mood', 'density_intent', 'focal_points', 'circulation_plan', 'negative_space', 'rhythm', 'lighting_plan')}, ensure_ascii=False) if concept else 'none recorded'
    hist = ''
    if history:
        h = history[-1]
        hist = (f"\nYOUR PREVIOUS ROUND ({h['round']}): you said \"{h['impression'][:300]}\" and asked for {len(h['ops'])} edits; "
                f"applied: {[(r['op'].get('instance'), r['op'].get('op')) for r in h['ops'] if r['accepted']]}; "
                f"refused by physics: {[(r['op'].get('instance'), r['reason'][:70]) for r in h['ops'] if not r['accepted']]}.\n"
                f"Pictures from before those edits, for comparison: {json.dumps(prev_files)}\nDecide whether your edits helped; undo or refine them if they did not.")
    return f"""You are the reviewing interior designer AND editor of a furnished FFXIV {house_size} house ground floor (review round {n} of at most {rounds}).
Original request: {request}
Design intent: title {(plan or {}).get('title')!r}, theme {(plan or {}).get('theme')!r}; {brief}.
Open these rendered pictures with your file-read tool (do NOT run shell commands), each caption says what it shows:
{json.dumps([{'caption': c, 'file': f} for c, f in files], ensure_ascii=False)}
The pictures are NOT mirrored: in the TOP view world +x is image RIGHT and +y is image UP, matching the furniture table. They have no real lighting and rough textures.
Furniture on the floor (world metres, footprint-centre x/y; yaw counter-clockwise; faces_deg = direction the front points, 0 = +x, 90 = +y; size_m = footprint width, depth, height):
{json.dumps(furniture_rows(objs), ensure_ascii=False)}
Layout facts (diagnostic only; NOT a score and NOT a goal - trust the pictures over these numbers): {json.dumps({'hard_violations': facts['hard_violations'], **facts['components']})}{hist}

Judge it the way a human designer would: does it look good and intentional, and does it fit the request and the design intent? Look at clutter and piling, clear focal points,
rhythm and repetition, whether many pieces point the same mechanical way, whether pieces collide in ugly ways (FFXIV allows overlap, so deliberate layering is fine), empty dead areas,
walkability, whether each zone reads as what it should be, and anything that looks random. Removing things is a valid fix, but do not delete deliberate structure: continuous lines of partitions/arches and vignette groups (pieces whose notes say 'group ...') are design, judge whether they work as a whole before removing parts. Bare surfaces (tables, shelves, sills with nothing on them) and a flat single-height lighting are also problems; you may move existing small props onto them with place.
Edits you may propose (floor items only, ids from the table; at most one edit per id per round): {{"instance":id,"op":"rotate","yaw":0..360}} or {{"op":"rotate","yaw_delta":deg}},
{{"op":"move","dx":m,"dy":m}} (up to {MAX_MOVE_HINT} m), {{"op":"place","x":m,"y":m,"yaw":deg(optional)}} (put the footprint centre at x,y), {{"op":"remove"}}. Every edit needs a short "reason".
Edits are applied unless they break physics (outside the floor, inside a stair body). There is no score; you are the judge.
Reply with ONLY JSON: {{"verdict":"good"|"needs_work","impression":"2-4 sentences on how the room looks now","problems":["..."],"ops":[{{"instance":id,"op":"...",...,"reason":"..."}}]}}
Say "good" only if you would be happy to show this room; then ops should be empty."""


def parse_reply(text):
    try: reply = parse_json_reply(text)
    except Exception: reply = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip()).strip())
    if not isinstance(reply, dict): raise ValueError('reply must be an object')
    return reply


def critique_loop(scene, objs, design_dir, out_dir, src_layout, scale, u16, report, *, root, request='', model=MODEL, rounds=3, allow_remove=True, external_dir=None):
    out_dir = Path(out_dir); history = []; plan = None; prev_files = []; render_state = {}
    pp = Path(design_dir) / 'plan.json'
    if pp.exists(): plan = json.loads(pp.read_text(encoding='utf-8'))
    request = request or (plan or {}).get('title', '')
    stop = f'round limit ({rounds}) reached'
    for n in range(1, rounds + 1):
        rd = out_dir / f'round-{n}'; rd.mkdir(parents=True, exist_ok=True)
        lp = rd / 'layout.json'; write_layout(lp, export_layout(src_layout, objs, scale), u16)
        if (rd / 'main' / 'view-01-labeled.png').exists() and (rd / 'review-request.txt').exists():
            files = _cached_files(rd); facts = R.measure(scene, objs)   # resume after a file-protocol reply: reuse the render already judged for this state
        else:
            files = render_round(lp, rd, objs, root=root, state=render_state); facts = R.measure(scene, objs)
        prompt = build_prompt(n, rounds, request, plan, objs, files, report['house_size'], facts, history, prev_files); (rd / 'review-request.txt').write_text(prompt, encoding='utf-8')
        if external_dir is not None:
            ext = Path(external_dir); ext.mkdir(parents=True, exist_ok=True); (ext / f'round-{n}-request.txt').write_text(prompt, encoding='utf-8')
            rp = ext / f'round-{n}-reply.json'
            if not rp.exists(): raise WaitingForReply(f'write {rp} (images are listed in {ext / f"round-{n}-request.txt"}), then run again')
            text = rp.read_text(encoding='utf-8'); (rd / 'review-response.json').write_text(text, encoding='utf-8')
        else:
            text, err = call_agy(prompt, model=model, workdir=rd, name='review-prompt', timeout=600); (rd / 'review-response.json').write_text(text + '\n---STDERR---\n' + err, encoding='utf-8')
        try: reply = parse_reply(text)
        except Exception as e:
            history.append({'round': n, 'verdict': 'unparseable', 'impression': f'unparseable reply: {e!r}'[:200], 'problems': [], 'ops': [], 'images': [f for _, f in files]}); stop = 'unparseable model reply'; break
        results = []; seen = set(); planned = {op['instance']: op for op in (reply.get('ops') or []) if isinstance(op, dict) and 'instance' in op}   # so a table may move together with everything standing on it
        for op in (reply.get('ops') or []) if reply.get('verdict') != 'good' else []:
            if not isinstance(op, dict) or 'op' not in op or 'instance' not in op: results.append({'op': op, 'accepted': False, 'reason': 'malformed op'}); continue
            if op['instance'] in seen: results.append({'op': op, 'accepted': False, 'reason': 'second edit for the same id in one round'}); continue
            seen.add(op['instance'])
            if op['op'] == 'remove' and not allow_remove: results.append({'op': op, 'accepted': False, 'reason': 'removal disabled (--no-remove)'}); continue
            clean = {k: op[k] for k in ('instance', 'op', 'yaw', 'yaw_delta', 'dx', 'dy', 'x', 'y') if k in op}
            res = R.try_op(scene, objs, clean, companions=planned); res['model_reason'] = str(op.get('reason', ''))[:200]; results.append(res)
        history.append({'round': n, 'verdict': reply.get('verdict'), 'impression': str(reply.get('impression', ''))[:600], 'problems': [str(x)[:200] for x in (reply.get('problems') or [])][:20],
                        'ops': results, 'images': [f for _, f in files]})
        prev_files = [f for _, f in files][:2]
        if reply.get('verdict') == 'good': stop = 'the model judged the room good'; break
        if not any(r['accepted'] for r in results): stop = 'the model proposed nothing that could be applied'; break
    return history, stop
