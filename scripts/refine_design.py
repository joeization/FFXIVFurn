"""Refine an existing design with a model that LOOKS at renders and judges it (multi-round). There is no score and nothing is accepted because a number went up.

  python scripts/refine_design.py --design-dir outputs/designs/X --out outputs/designs/X-refined [--rounds 3] [--model gemini-4-argon-medium]
  external model (file protocol):  ... --external outputs/designs/X-ext   (writes round-N-request.txt, stops; put round-N-reply.json next to it and run again with a NEW --out)

Each round: render (unmirrored, image axes == JSON axes) -> model verdict + edits -> edits applied unless they break physics -> render again.
Never edits the input design; never calls Opus. Facts such as overlap and clearance are shown to the model as diagnostics only.
"""
from pathlib import Path
import argparse, json, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.house_profiles import room_bounds, room_polygon, room_keepouts
from ffxiv_furniture.design import place as P, refine as R
from ffxiv_furniture.design.layout_io import read_layout, export_layout, write_layout
from ffxiv_furniture.design.visual import critique_loop, WaitingForReply


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--design-dir', type=Path, required=True); ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--rounds', type=int, default=3); ap.add_argument('--model', default='gemini-3.8-flash-medium', help='agy model that reviews the renders')
    ap.add_argument('--external', type=Path, help='directory for the file protocol with a non-agy model')
    ap.add_argument('--request', default='', help='original request text shown to the reviewer (default: plan title)')
    ap.add_argument('--no-remove', action='store_true', help='refuse ops that remove items (removal is allowed by default)')
    ap.add_argument('--no-final-render', action='store_true', help='skip the final mirrored (app-like) renders')
    a = ap.parse_args(argv)
    if a.out.exists() and any(a.out.iterdir()) and not (a.external and any(a.external.glob('round-*-reply.json'))): raise SystemExit('Output directory is not empty; use a new one (or --external with replies to resume)')
    rep = json.loads((a.design_dir / 'design-report.json').read_text(encoding='utf-8')); size = rep['house_size']
    src, u16 = read_layout(a.design_dir / 'layout.json'); scale = src['interiorScale']
    room = room_bounds(ROOT, size); room['polygon'] = room_polygon(ROOT, size); room['keepouts'] = room_keepouts(ROOT, size, 'ground')
    scene = P.Scene(room); a.out.mkdir(parents=True, exist_ok=True)
    with FurnitureDB(ROOT / 'data/furniture.sqlite3') as db:
        objs = R.load_objects(rep['placements'], db)
        assert len(objs) == len(src['interiorFurniture']), 'design report and layout disagree'
        before = R.measure(scene, objs)
        try:
            history, stop = critique_loop(scene, objs, a.design_dir, a.out, src, scale, u16, rep, root=ROOT, request=a.request, model=a.model, rounds=a.rounds, allow_remove=not a.no_remove, external_dir=a.external)
        except WaitingForReply as e:
            print('WAITING:', e); return 2
        after = R.measure(scene, objs); lp = a.out / 'layout.json'; write_layout(lp, export_layout(src, objs, scale), u16)
        report = {'input': str(a.design_dir), 'house_size': size, 'kind': 'model-judged refinement; no score', 'rounds': history, 'stop': stop,
                  'final_verdict': history[-1]['verdict'] if history else None, 'final_impression': history[-1]['impression'] if history else None,
                  'facts_before': {'components': before['components'], 'hard_violations': before['hard_violations']}, 'facts_after': {'components': after['components'], 'hard_violations': after['hard_violations']},
                  'items_before': len(rep['placements']), 'items_after': sum(1 for o in objs if not o.removed),
                  'accepted_ops': sum(1 for h in history for r in h['ops'] if r['accepted']), 'rejected_ops': sum(1 for h in history for r in h['ops'] if not r['accepted']), 'input_untouched': True}
        (a.out / 'refine-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('stop', 'final_verdict', 'final_impression', 'items_before', 'items_after', 'accepted_ops', 'rejected_ops')}, ensure_ascii=False, indent=1))
    if not a.no_final_render:
        from ffxiv_furniture.rendering.pipeline import run_pipeline
        common = dict(db_path=ROOT / 'data/furniture.sqlite3', room_context=True, rough_room_finish=True, approximate_tint=False, size=(960, 640))
        run_pipeline(lp, a.out / 'render', **common); run_pipeline(lp, a.out / 'render-3view', three_view=True, **common); print('rendered (app-like mirrored views)')
    return 0


if __name__ == '__main__': sys.exit(main())
