"""Helpers for an EXTERNAL model (not agy) doing the two-level plan by hand.
  emit  : concept.json + room-facts.json -> zoneNN-request.txt (one per zone)
  build : concept.json + zoneNN-reply.json ({"items":[...]}) -> plan.json (queries sanitised to English; game-cap validated per zone)
"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.design.concept import zone_prompt, clean_query, SANITIZED
from ffxiv_furniture.design.plan import validate_plan

ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['emit', 'build']); ap.add_argument('--dir', type=Path, required=True); a = ap.parse_args()
con = json.loads((a.dir / 'concept.json').read_text(encoding='utf-8')); facts = json.loads((a.dir / 'room-facts.json').read_text(encoding='utf-8')); cap = facts['game_cap_instances_for_whole_house']
with FurnitureDB(ROOT / 'data/furniture.sqlite3') as db:
    c = db.connection
    vocab = {f'{r[0]}:{r[1]}' for r in c.execute("SELECT category,name FROM tags WHERE category NOT IN ('function','scope')")}
    cats = [r[0] for r in c.execute("SELECT DISTINCT source_category FROM candidate_assets WHERE scope='interior' AND source_category!='Fixture' ORDER BY 1")]
ex = sorted(vocab)[::max(1, len(vocab) // 25)][:25]
total = sum(z['area_fraction'] for z in con['zones']); req = (a.dir / 'request.txt').read_text(encoding='utf-8').strip()
for k, v in list(con['fixtures'].items()): con['fixtures'][k] = clean_query(v, f'fixtures.{k}')
if a.mode == 'emit':
    for i, z in enumerate(con['zones']):
        share = z['area_fraction'] / total; budget = max(1, int(cap * share))
        (a.dir / f'zone{i:02d}-request.txt').write_text(zone_prompt(req, con, z, facts, facts['free_area_after_stairs_m2'] * share, cats, ex, budget), encoding='utf-8'); print('wrote zone', i, z['name'], 'budget', budget)
else:
    zones = []
    for i, z in enumerate(con['zones']):
        share = z['area_fraction'] / total; budget = max(1, int(cap * share)); items = json.loads((a.dir / f'zone{i:02d}-reply.json').read_text(encoding='utf-8'))['items']
        for it in items: it['query'] = clean_query(it.get('query'), z['name'])
        validate_plan({'title': 't', 'theme': 't', 'used_floors': ['ground'], 'fixtures': con['fixtures'], 'zones': [{'name': z['name'], 'area_fraction': 1, 'items': items}]}, vocab_keys=vocab, max_items=budget)
        zones.append({'name': z['name'], 'purpose': z.get('purpose', ''), 'character': z.get('character', ''), 'area_fraction': share, 'items': items})
    plan = {'title': con.get('title', ''), 'theme': con.get('theme', ''), 'used_floors': ['ground'], 'fixtures': con['fixtures'], 'zones': zones, 'concept': {k: v for k, v in con.items() if k not in ('zones', 'fixtures')}}
    plan = validate_plan(plan, vocab_keys=vocab, max_items=cap)
    if SANITIZED: plan['sanitized_queries'] = list(SANITIZED)
    (a.dir / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8'); print('plan.json: zones', len(zones), 'planned_instances', plan['planned_instances'])
