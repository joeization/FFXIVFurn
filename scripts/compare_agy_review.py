"""Compare agy Gemini Flash second review against original + Qwen review (advisory; no writes to predictions/DB)."""
from pathlib import Path
import csv, json, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture.classification.audit import check_asset
F = ROOT / 'runs/round1/finalization'; W = F / 'agy-flash-review'
rd = lambda p: json.loads(p.read_text(encoding='utf-8'))
rep = rd(F / 'qwen-flagged-review/report.json'); vocab = rd(F / 'frozen-vocab.json'); aud = rd(F / 'tag-audit/report.json')
accepted = {c['key'] for c in vocab['concepts'] if c['status'] == 'accepted'}
agy = rd(W / 'agy-flash-predictions.json'); meta = {}
for it in aud['needs_review']: meta.setdefault(it['image_hash'], []).append(it)
rows = []; out = []
for c in rep['changes']:
    h = c['image_hash']
    if h not in agy: continue
    a = agy[h]; ag = {t['key'] for t in a['tags']}; q = {t['key'] for t in c['after']['tags']}; o = {t['key'] for t in c['before']['tags']}
    issues = [{'asset_key': m['asset_key'], 'issues': check_asset(m, {'tags': a['tags']}, accepted)} for m in meta[h]]
    still = any(i['issues'] for i in issues)
    j = lambda x, y: round(len(x & y) / max(1, len(x | y)), 2)
    out.append({'image_hash': h, 'names': [m['name'] for m in meta[h]], 'agy': a, 'agy_still_flagged': still, 'checks': issues})
    rows.append({'name': ' | '.join(m['name'] for m in meta[h]), 'jaccard_agy_vs_qwen': j(ag, q), 'jaccard_agy_vs_orig': j(ag, o),
                 'agy_still_flagged': still, 'agy_tags': ' | '.join(sorted(ag)), 'qwen_tags': ' | '.join(sorted(q)), 'orig_tags': ' | '.join(sorted(o)),
                 'agy_uncertain': ' | '.join(a.get('uncertain', []))})
(W / 'comparison.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
with (W / 'comparison.csv').open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader()
    for r in rows: w.writerow({k: ("'" + v if isinstance(v, str) and v[:1] in '=+-@' else v) for k, v in r.items()})
print(json.dumps({'images': len(rows), 'agy_still_flagged': sum(r['agy_still_flagged'] for r in rows),
                  'with_uncertain': sum(bool(r['agy_uncertain']) for r in rows),
                  'mean_jaccard_agy_qwen': round(sum(r['jaccard_agy_vs_qwen'] for r in rows) / len(rows), 2)}))
for r in rows:
    if r['agy_still_flagged']: print('STILL', r['name'])
