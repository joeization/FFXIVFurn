"""Run one full design (plan -> rerank -> placement -> render -> visual critique round) with a chosen agy model and measure the quota it consumed.

  python scripts/run_design_with_quota.py --model gemini-4-argon-medium --request "..." --name argon-tea-room
Quota = agy `/usage` buckets before vs after (fractions of each bucket), plus the token counts reported by every model call (raw replies are summed).
Quota is shared with other usage on the same account, so the delta is an upper bound if something else ran concurrently. Costs are NOT currency.
"""
from pathlib import Path
import argparse, json, shutil, subprocess, sys, time
ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)


def usage():
    r = subprocess.run([shutil.which('agy'), '-p', '/usage', '--output-format', 'json'], capture_output=True, text=True, encoding='utf-8', timeout=90)
    data = json.loads(r.stdout); buckets = {}
    for g in data['command']['data']['groups']:
        for b in g['buckets']: buckets[f"{g['name']} / {b['name']}"] = b['remaining_fraction']
    return buckets


def tokens(*dirs):
    total = {'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'thinking_tokens': 0, 'cache_read_tokens': 0, 'total_tokens': 0, 'seconds': 0.0}; per = []
    for d in dirs:
        for f in sorted(Path(d).rglob('*response*.json')):
            raw = f.read_text(encoding='utf-8').split('\n---STDERR---\n')[0]
            try: j = json.loads(raw)
            except Exception: continue
            u = j.get('usage') or {}; total['calls'] += 1; total['seconds'] += float(j.get('duration_seconds') or 0)
            for k in ('input_tokens', 'output_tokens', 'thinking_tokens', 'cache_read_tokens', 'total_tokens'): total[k] += int(u.get(k) or 0)
            per.append({'file': str(f.relative_to(ROOT)), 'status': j.get('status'), 'usage': u, 'seconds': j.get('duration_seconds')})
    return total, per


def run(cmd):
    t = time.time(); r = subprocess.run([str(PY), *cmd], cwd=ROOT, capture_output=True, text=True, encoding='utf-8'); return {'cmd': cmd[:3], 'code': r.returncode, 'seconds': round(time.time() - t, 1), 'tail': (r.stdout + r.stderr)[-600:]}


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--model', required=True); ap.add_argument('--request', required=True); ap.add_argument('--name', required=True)
    ap.add_argument('--house-size', default='Medium'); ap.add_argument('--max-items', type=int, default=None, help='default: no extra limit beyond the game cap'); ap.add_argument('--no-visual', action='store_true', help='skip the model review rounds'); ap.add_argument('--rounds', type=int, default=3)
    a = ap.parse_args()
    design, refined = ROOT / 'outputs/designs' / a.name, ROOT / 'outputs/designs' / (a.name + '-refined')
    if design.exists() or refined.exists(): raise SystemExit('output dirs exist; choose a new --name')
    before = usage(); started = time.time(); steps = []
    steps.append(run(['scripts/design_room.py', '--request', a.request, '--house-size', a.house_size, *(['--max-items', str(a.max_items)] if a.max_items else []), '--model', a.model, '--out', str(design), '--render']))
    if steps[-1]['code'] == 0:
        if not a.no_visual: steps.append(run(['scripts/refine_design.py', '--design-dir', str(design), '--out', str(refined), '--model', a.model, '--rounds', str(a.rounds), '--request', a.request]))
    after = usage(); tot, per = tokens(design, refined)
    delta = {k: round((before[k] - after[k]) * 100, 3) for k in before}
    out = {'model': a.model, 'request': a.request, 'design_dir': str(design), 'refined_dir': str(refined), 'wall_seconds': round(time.time() - started, 1), 'steps': steps,
           'quota_before_fraction': before, 'quota_after_fraction': after, 'quota_consumed_percentage_points': delta, 'tokens': tot, 'calls': per,
           'note': 'Fractions are the remaining share of each agy bucket; the account shares buckets with other usage, so the delta can include unrelated activity. Not currency.'}
    (ROOT / 'outputs/designs' / f'{a.name}-quota.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('model', 'wall_seconds', 'quota_consumed_percentage_points', 'tokens')}, ensure_ascii=False, indent=1))
    for s in steps: print(s['cmd'], 'exit', s['code'], s['seconds'], 's')


if __name__ == '__main__': main()
