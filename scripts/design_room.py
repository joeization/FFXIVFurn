"""Design a ground-floor room: prompt -> Gemini Flash plan -> DB resolution -> deterministic placement -> layout JSON (+ optional render).

Never calls Opus. Output goes to a NEW directory (never overwrites app saves or earlier runs).
  python scripts/design_room.py --request "cozy Hingan tea room" --house-size Medium --out outputs/designs/tea-room
  python scripts/design_room.py --plan-file outputs/designs/tea-room/plan.json --out outputs/designs/tea-room-v2   # no model call
"""
from pathlib import Path
import argparse, json, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.housing import HOUSING_LIMITS, validate_layout_budget
from ffxiv_furniture.layout import build_layout, apply_fixtures
from ffxiv_furniture.house_profiles import room_bounds, room_polygon, room_keepouts
from ffxiv_furniture.material_semantic import MaterialIndex
from ffxiv_furniture.design.plan import request_plan, validate_plan, MODEL
from ffxiv_furniture.design.concept import request_hierarchical_plan, room_facts
from ffxiv_furniture.design.resolve import resolve_furniture, resolve_fixtures
from ffxiv_furniture.design.place import place_all
from ffxiv_furniture.config import local_input
from ffxiv_furniture.design.rerank import rerank

SEEDS = {'Medium': lambda: local_input('DECO_SEED', 'a complete layout JSON you may use'), 'Large': lambda: local_input('FFXIVFURN_LARGE_SEED', 'a complete Large-house layout JSON')}   # operator-provided; no private defaults


def read_json_any(p):
    b = Path(p).read_bytes(); u16 = b[:2] in (b'\xff\xfe', b'\xfe\xff')
    return json.loads(b.decode('utf-16' if u16 else 'utf-8-sig')), u16


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--request'); ap.add_argument('--plan-file'); ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--house-size', default='Medium'); ap.add_argument('--max-items', type=int, default=None, help='default: the game cap for this house size (a rule, not a target)')
    ap.add_argument('--single-shot', action='store_true', help='legacy one-call planner (default is overall direction first, then one call per zone)')
    ap.add_argument('--seed', type=Path, help='real save/layout to use as template (required for Small/Apartment)')
    ap.add_argument('--model', default=MODEL); ap.add_argument('--no-rerank', action='store_true');
    ap.add_argument('--emit-rerank-request', action='store_true', help='resolve candidates, write rerank-request.txt and stop (for an external model)')
    ap.add_argument('--rerank-reply', type=Path, help='JSON file with the external model reply [{entry,pick,why}]'); ap.add_argument('--render', action='store_true')
    a = ap.parse_args(argv)
    if a.out.exists() and any(a.out.iterdir()): raise SystemExit('Output directory is not empty; use a new one')
    if bool(a.request) == bool(a.plan_file): raise SystemExit('Give exactly one of --request / --plan-file')
    cap = HOUSING_LIMITS[a.house_size]['interior']
    if a.max_items is None: a.max_items = cap
    if not 1 <= a.max_items <= cap: raise SystemExit(f'max-items must be 1..{cap}')
    seedp = a.seed or (SEEDS[a.house_size]() if a.house_size in SEEDS else None)
    if seedp is None: raise SystemExit(f'No real seed save for {a.house_size}; pass --seed')
    a.out.mkdir(parents=True, exist_ok=True)
    room = room_bounds(ROOT, a.house_size); room['polygon'] = room_polygon(ROOT, a.house_size); room['keepouts'] = room_keepouts(ROOT, a.house_size, 'ground')
    with FurnitureDB(ROOT / 'data/furniture.sqlite3') as db:
        c = db.connection
        vocab_keys = {f'{r[0]}:{r[1]}' for r in c.execute("SELECT category,name FROM tags WHERE category NOT IN ('function','scope')")}
        index = MaterialIndex(db, cache_dir=ROOT / 'data/model-cache', local_files_only=True)
        if a.plan_file:
            plan = validate_plan(json.loads(Path(a.plan_file).read_text(encoding='utf-8')), vocab_keys=vocab_keys, max_items=a.max_items)
        else:
            cats = [r[0] for r in c.execute("SELECT DISTINCT source_category FROM candidate_assets WHERE scope='interior' AND source_category!='Fixture' ORDER BY 1")]
            ex = sorted(vocab_keys)[::max(1, len(vocab_keys) // 25)][:25]
            if a.single_shot:
                plan = request_plan(a.request, a.out, house_size=a.house_size, max_items=a.max_items, categories=cats, tag_examples=ex, vocab_keys=vocab_keys, model=a.model)
            else:
                kp = room['keepouts']; kunion = __import__('shapely.ops', fromlist=['unary_union']).unary_union(kp) if kp else None
                facts = room_facts(room, room['polygon'].difference(kunion).area if kunion is not None else room['polygon'].area, kunion.intersection(room['polygon']).area if kunion is not None else 0.0, a.house_size, a.max_items)
                (a.out / 'room-facts.json').write_text(json.dumps(facts, indent=1), encoding='utf-8')
                plan = request_hierarchical_plan(a.request, a.out, facts=facts, categories=cats, tag_examples=ex, vocab_keys=vocab_keys, model=a.model)
        (a.out / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
        resolved, rreport = resolve_furniture(db, index, plan)
        rerank_report = None
        if a.emit_rerank_request:   # external-model workflow: write the candidate prompt and stop; a reply file is applied on the next run
            from ffxiv_furniture.design.rerank import build_prompt as _bp
            (a.out / 'rerank-request.txt').write_text(_bp(plan, resolved), encoding='utf-8'); print('wrote', a.out / 'rerank-request.txt', 'entries', len(resolved)); return 0
        if a.rerank_reply:
            from ffxiv_furniture.design.rerank import rerank_from_file
            resolved, rerank_report = rerank_from_file(resolved, a.rerank_reply)
            (a.out / 'rerank-report.json').write_text(json.dumps(rerank_report, ensure_ascii=False, indent=1), encoding='utf-8')
        elif not a.no_rerank:
            resolved, rerank_report = rerank(plan, resolved, a.out, model=a.model)
            (a.out / 'rerank-report.json').write_text(json.dumps(rerank_report, ensure_ascii=False, indent=1), encoding='utf-8')
        fixtures = resolve_fixtures(index, plan)
        scene, preport = place_all(room, resolved)
        seed, u16 = read_json_any(seedp); seed['houseSize'] = a.house_size; scale = seed['interiorScale']
        placements = [{'item_id': p['item_id'], 'location': [p['location_m'][0] * scale, p['location_m'][1] * scale, p['location_m'][2] * scale], 'yaw_degrees': p['yaw_degrees']} for p in scene.placements]
        layout = build_layout(db, seed, placements)
        layout, warnings = apply_fixtures(db, layout, [{'item_id': f['item_id'], 'level': 'Ground Floor'} for f in fixtures])
        budget = validate_layout_budget(layout)
        lp = a.out / 'layout.json'
        lp.write_bytes((json.dumps(layout, ensure_ascii=False, indent='\t') + '\n').encode('utf-16' if u16 else 'utf-8'))
        report = {'request': a.request, 'house_size': a.house_size, 'model': plan.get('model'), 'planned_instances': plan['planned_instances'], 'placed': len(scene.placements),
                  'unplaced': scene.unplaced, 'resolution': rreport, 'rerank': rerank_report, 'fixtures': fixtures, 'fixture_warnings': warnings, 'budget': budget, 'room': {k: v for k, v in room.items() if k not in ('polygon', 'keepouts')} | {'stair_keepouts': len(room['keepouts'])} | {'floor_area_m2': round(room['polygon'].area, 1), 'bbox_area_m2': round((room['max'][0]-room['min'][0])*(room['max'][1]-room['min'][1]), 1)}, 'regions': preport,
                  'placements': scene.placements, 'dropped_tags': plan['dropped_tags'], 'seed': str(seedp),
                  'assumptions': ['model-local front = +Y (64/73 chairs have backrest on -Y)', 'yaw multiples of 90 deg; CCW about Z', 'placement uses the real floor-mesh outline (Medium is L-shaped)', 'room transforms identity (uncalibrated)',
                                  'stairs: decoded Medium actor transforms are keepouts (1 m clearance); other sizes have none; entrance and pillars not modelled' + ('; Medium corridor reserved' if room.get('corridor') else ''), 'tabletop decor assumes flat table AABB top',
                                  'layout not verified in the app by this script']}
        (a.out / 'design-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('planned_instances', 'placed', 'unplaced', 'budget')}, ensure_ascii=False, indent=1)); print('layout', lp)
    if a.render:
        from ffxiv_furniture.rendering.pipeline import run_pipeline
        common = dict(db_path=ROOT / 'data/furniture.sqlite3', room_context=True, rough_room_finish=True, approximate_tint=False, size=(960, 640))
        m = run_pipeline(lp, a.out / 'render', **common)
        print('render', len(m['views']), 'views; warnings:', *m['warnings'], sep='\n  ')
        m3 = run_pipeline(lp, a.out / 'render-3view', three_view=True, **common)
        print('3view done', len(m3['views']))
        run_pipeline(lp, a.out / 'render-model', mirror_view=False, **common); run_pipeline(lp, a.out / 'render-model-3view', three_view=True, mirror_view=False, **common)   # model-facing: image axes == JSON axes


if __name__ == '__main__': main()
