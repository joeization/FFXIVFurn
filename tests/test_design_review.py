"""Refinement physics, model-judged critique and independent review-tool contracts."""

import csv
import importlib.util
import json
import math
import tempfile
import unittest
from ffxiv_furniture.design import place as P, refine as R, visual as V
from pathlib import Path
from shapely.geometry import Polygon, box
from unittest import mock
from tests.support import ROOT

def load_script(name):
    """Load one repository script without repeating importlib boilerplate."""
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exploration_policy = load_script('finish_exploration')
finalization = load_script('finalize_and_classify')
review_export = load_script('export_tag_review')
review_harness = load_script('review_deco')


try:
    from shapely.geometry import Polygon, box
except ImportError:
    raise unittest.SkipTest('shapely not installed')


REVIEW_ROOM = {'polygon': Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), 'ceiling_z': 6.5, 'corridor': None, 'keepouts': [box(9, 4, 12, 8)]}


def refine_geometry(name, w, d, h, category, **info):
    g = {'name': name, 'length': w, 'width': d, 'height': h, 'category': category, 'lo': [-w / 2, -d / 2, 0.0], 'hi': [w / 2, d / 2, h]}
    g.update(info); return g


def refine_entry(zone, role, item_id, g, count=1):
    return {'zone_index': zone, 'zone': f'z{zone}', 'area_fraction': 1.0, 'role': role, 'count': count, 'query': 'q', 'item_id': item_id, 'geometry': g}


def build_refine_scene():
    res = [refine_entry(0, 'table', 1, refine_geometry('Round Table', 1.8, 1.8, 0.7, 'Furniture/Table', ptype='floor', supports_top=True, top_z_local=0.7, round_top=True)),
           refine_entry(0, 'seating', 2, refine_geometry('Chair', 0.5, 0.5, 0.9, 'Furniture/Chair', ptype='floor', front_deg=90.0), 3),
           refine_entry(0, 'storage', 3, refine_geometry('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf', ptype='floor', front_deg=90.0), 2)]
    scene, _ = P.place_all(REVIEW_ROOM, res)
    solids = [s[2] for s in scene.solid]; pls = [p for p in scene.placements if p['layer'] in ('solid', 'seat')]
    return scene, [R.Obj(i, p, it) for i, (p, it) in enumerate(zip(pls, solids))]


class RefineOrientationTests(unittest.TestCase):
    def test_round_table_seats_use_non_right_angles_and_face_the_table(self):
        scene, objs = build_refine_scene(); seats = [o for o in objs if o.role == 'seating']; table = next(o for o in objs if o.role == 'table')
        self.assertEqual(len(seats), 3)
        tc = table.poly.centroid
        for o in seats:
            c = o.poly.centroid; want = math.degrees(math.atan2(tc.y - c.y, tc.x - c.x)) % 360
            self.assertLess(abs(P.wrap(o.facing - want)), 1.0, o.label())
        self.assertTrue(any(abs(o.yaw % 90) > 1 for o in seats), 'ring placement must produce true free angles, not only multiples of 90')

    def test_front_deg_is_per_item(self):
        it = P.make_item({'item_id': 1, 'role': 'seating', 'zone': 'z'}, refine_geometry('Side Couch', 2, 1, 1, 'Furniture/Chair', ptype='floor', front_deg=0.0), 0)
        self.assertEqual(P.face_yaw(it, 90), 90.0)        # front is +X, so facing +Y needs a 90 deg turn
        it2 = P.make_item({'item_id': 1, 'role': 'seating', 'zone': 'z'}, refine_geometry('Chair', 1, 1, 1, 'Furniture/Chair', ptype='floor', front_deg=90.0), 0)
        self.assertEqual(P.face_yaw(it2, 90), 0.0)

    def test_wall_item_uses_measured_mount_height_and_ceiling_clamp(self):
        scene = P.Scene(REVIEW_ROOM)
        low = P.make_item({'item_id': 1, 'role': 'wall-art', 'zone': 'z'}, refine_geometry('Wall Shelf', 1.0, 0.3, 0.6, 'Furniture/Wall-Mounted', ptype='wall', mount_bottom_z=1.3), 0)
        self.assertAlmostEqual(P.wall_item_z(scene, low), 1.3, places=6)
        tall = P.make_item({'item_id': 2, 'role': 'wall-art', 'zone': 'z'}, refine_geometry('Huge', 1.0, 0.3, 6.4, 'Furniture/Wall-Mounted', ptype='wall', mount_bottom_z=1.3), 0)
        self.assertIsNone(P.wall_item_z(scene, tall))     # cannot hang below the ceiling: refused, not squeezed


class RefinementPhysicsTests(unittest.TestCase):
    def test_check_flags_overlap_outside_and_keepout(self):
        scene, objs = build_refine_scene(); self.assertEqual(R.check(scene, objs), [])
        a, b = objs[1], objs[2]; b.pivot = a.pivot
        self.assertFalse(any('overlaps' in v for v in R.check(scene, objs)))      # overlap is legal in FFXIV: scored softly, never a hard violation
        scene, objs = build_refine_scene(); objs[1].pivot = (-5, -5); self.assertTrue(any('outside' in v for v in R.check(scene, objs)))
        scene, objs = build_refine_scene(); objs[1].pivot = (10.5, 6.0); self.assertTrue(any('stair' in v for v in R.check(scene, objs)))

    def test_try_op_is_gated_by_physics_only_not_by_any_score(self):
        scene, objs = build_refine_scene(); seat = next(o for o in objs if o.role == 'seating')
        self.assertNotIn('total', R.measure(scene, objs)); self.assertFalse(hasattr(R, 'optimise')); self.assertFalse(hasattr(R, 'score'))
        r = R.try_op(scene, objs, {'op': 'rotate', 'instance': seat.i, 'yaw_delta': 180}); self.assertTrue(r['accepted'])          # a "worse" facing is the model's call
        r = R.try_op(scene, objs, {'op': 'move', 'instance': seat.i, 'dx': 7, 'dy': 0}); self.assertFalse(r['accepted']); self.assertIn('exceeds', r['reason'])
        before = (seat.pivot, seat.yaw)
        r = R.try_op(scene, objs, {'op': 'place', 'instance': seat.i, 'x': 10.5, 'y': 6.0}); self.assertFalse(r['accepted']); self.assertIn('stair', r['reason'])   # physics still refuses
        self.assertEqual((seat.pivot, seat.yaw), before, 'refused ops must be fully undone')
        r = R.try_op(scene, objs, {'op': 'place', 'instance': seat.i, 'x': 3.0, 'y': 2.0, 'yaw': 45}); self.assertTrue(r['accepted'])
        c = seat.poly.centroid; self.assertAlmostEqual(c.x, 3.0, places=3); self.assertAlmostEqual(c.y, 2.0, places=3); self.assertAlmostEqual(seat.yaw, 45.0)

    def test_removal_is_allowed_by_default_in_the_review_loop(self):
        import inspect
        from ffxiv_furniture.design.visual import critique_loop
        self.assertTrue(inspect.signature(critique_loop).parameters['allow_remove'].default)


def review_geometry(name, w, d, h, category, **info):
    g = {'name': name, 'length': w, 'width': d, 'height': h, 'category': category, 'lo': [-w / 2, -d / 2, 0.0], 'hi': [w / 2, d / 2, h], 'ptype': 'floor', 'front_deg': 90.0}; g.update(info); return g


def build_review_scene():
    res = [{'zone_index': 0, 'zone': 'z0', 'area_fraction': 1.0, 'role': 'storage', 'count': 3, 'query': 'q', 'item_id': 3, 'geometry': review_geometry('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf'), 'placement': {}, 'entry_key': '0:0'}]
    scene, _ = P.place_all(REVIEW_ROOM, res); solids = [s[2] for s in scene.solid]; pls = [p for p in scene.placements if p['layer'] in ('solid', 'seat')]
    objs = [R.Obj(i, p, it) for i, (p, it) in enumerate(zip(pls, solids))]
    src = {'interiorScale': 100, 'interiorFurniture': [{'transform': {'location': [0, 0, 0], 'rotation': [0, 0, 0, 1]}} for _ in objs]}
    return scene, objs, src


class CritiqueLoopTests(unittest.TestCase):
    def run_loop(self, replies, rounds=3, allow_remove=True):
        scene, objs, src = build_review_scene(); prompts = []; it = iter(replies)
        def agy(prompt, **kw): prompts.append(prompt); return json.dumps(next(it)), ''
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(V, 'call_agy', agy), mock.patch.object(V, 'render_round', lambda lp, out, objs, root, state=None: [('TOP', 'top.png')]):
            hist, stop = V.critique_loop(scene, objs, tmp, tmp, src, 100, False, {'house_size': 'Medium'}, root=Path(tmp), request='tea room', rounds=rounds, allow_remove=allow_remove)
        return hist, stop, objs, prompts

    def test_stops_when_the_model_says_good_and_ignores_edits_then(self):
        hist, stop, objs, _ = self.run_loop([{'verdict': 'good', 'impression': 'nice', 'problems': [], 'ops': [{'instance': 0, 'op': 'remove'}]}])
        self.assertEqual(stop, 'the model judged the room good'); self.assertFalse(any(o.removed for o in objs)); self.assertEqual(len(hist), 1)

    def test_multi_round_applies_edits_and_shows_the_model_what_happened(self):
        r1 = {'verdict': 'needs_work', 'impression': 'cramped', 'problems': ['shelves pile up'], 'ops': [{'instance': 0, 'op': 'place', 'x': 3, 'y': 2, 'yaw': 45, 'reason': 'spread'}, {'instance': 1, 'op': 'place', 'x': 10.5, 'y': 6, 'reason': 'stairs'}]}
        r2 = {'verdict': 'good', 'impression': 'better', 'problems': [], 'ops': []}
        hist, stop, objs, prompts = self.run_loop([r1, r2])
        self.assertEqual(len(hist), 2); self.assertEqual([r['accepted'] for r in hist[0]['ops']], [True, False]); self.assertIn('stair', hist[0]['ops'][1]['reason'])
        self.assertAlmostEqual(objs[0].poly.centroid.x, 3.0, places=3)
        self.assertIn('YOUR PREVIOUS ROUND (1)', prompts[1]); self.assertIn('refused by physics', prompts[1]); self.assertIn('There is no score', prompts[0]); self.assertNotIn('YOUR PREVIOUS ROUND', prompts[0])

    def test_round_limit_nothing_applicable_remove_switch_and_garbage_reply(self):
        spin = {'verdict': 'needs_work', 'impression': 'x', 'problems': [], 'ops': [{'instance': 0, 'op': 'place', 'x': 5, 'y': 3, 'yaw': 20}]}
        spin2 = {'verdict': 'needs_work', 'impression': 'x', 'problems': [], 'ops': [{'instance': 0, 'op': 'place', 'x': 5, 'y': 3, 'yaw': 40}]}
        hist, stop, _, _ = self.run_loop([spin, spin2], rounds=2); self.assertEqual(len(hist), 2); self.assertIn('round limit', stop)
        hist, stop, _, _ = self.run_loop([{'verdict': 'needs_work', 'impression': 'x', 'problems': [], 'ops': [{'instance': 99, 'op': 'remove'}]}]); self.assertIn('nothing', stop)
        hist, stop, objs, _ = self.run_loop([{'verdict': 'needs_work', 'impression': 'x', 'problems': [], 'ops': [{'instance': 0, 'op': 'remove'}]}], allow_remove=False)
        self.assertFalse(objs[0].removed); self.assertIn('disabled', hist[0]['ops'][0]['reason'])
        hist, stop, objs, _ = self.run_loop([{'verdict': 'needs_work', 'impression': 'x', 'problems': [], 'ops': [{'instance': 0, 'op': 'remove'}]}, {'verdict': 'good', 'impression': 'ok', 'problems': [], 'ops': []}]); self.assertTrue(objs[0].removed)   # removal allowed by default
        scene, objs, src = build_review_scene()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(V, 'call_agy', lambda *a, **k: ('not json at all', '')), mock.patch.object(V, 'render_round', lambda *a, **k: []):
            hist, stop = V.critique_loop(scene, objs, tmp, tmp, src, 100, False, {'house_size': 'Medium'}, root=Path(tmp))
        self.assertEqual(stop, 'unparseable model reply')

    def test_external_file_protocol_waits_then_continues(self):
        scene, objs, src = build_review_scene()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(V, 'render_round', lambda *a, **k: [('TOP', 'top.png')]):
            ext = Path(tmp) / 'ext'
            with self.assertRaises(V.WaitingForReply): V.critique_loop(scene, objs, tmp, tmp, src, 100, False, {'house_size': 'Medium'}, root=Path(tmp), external_dir=ext)
            self.assertTrue((ext / 'round-1-request.txt').exists())
            (ext / 'round-1-reply.json').write_text(json.dumps({'verdict': 'good', 'impression': 'ok', 'problems': [], 'ops': []}), encoding='utf-8')
            hist, stop = V.critique_loop(scene, objs, tmp, tmp, src, 100, False, {'house_size': 'Medium'}, root=Path(tmp), external_dir=ext)
        self.assertEqual(stop, 'the model judged the room good')

    def test_prompt_shows_facts_but_calls_them_not_a_score_and_has_unmirrored_axes(self):
        _, _, _, prompts = self.run_loop([{'verdict': 'good', 'impression': 'ok', 'problems': [], 'ops': []}])
        self.assertIn('NOT a score', prompts[0]); self.assertIn('+x is image RIGHT', prompts[0]); self.assertNotIn('mirror', prompts[0].replace('NOT mirrored', ''))


class CompletionPolicyTests(unittest.TestCase):
    def test_only_appearance_hedges_are_equivalent(self):
        for label in ['wood','wood-like','wood-look','wood appearance','wood-like appearance']:
            self.assertEqual(exploration_policy.equivalence_label(label),'wood')
        self.assertNotEqual(exploration_policy.equivalence_label('dark wood appearance'),'wood')
        self.assertNotEqual(exploration_policy.equivalence_label('wood-like frame'),'wood')
        self.assertNotEqual(exploration_policy.equivalence_label('painted wood'),'wood')
        self.assertNotEqual(exploration_policy.equivalence_label('white fabric'),'fabric')

    def test_finish_script_has_no_final_execution_stage(self):
        source=(Path(__file__).resolve().parents[1]/'scripts/finish_exploration.py').read_text(encoding='utf-8')
        self.assertNotIn("visual('final",source)
        self.assertIn("visual('discover-all-remaining','discover-rest'",source)
        self.assertIn("'no_remote_model_calls':True",source)


class FinalizationContractTests(unittest.TestCase):
    def value(self,**overrides):
        d={'concept_id':'a','status':'accepted','definition':'Visible reddish hue.','reason':'Observable color.'}
        d.update(overrides);return {'decisions':[d]}

    def test_complete_exact_ids(self):
        self.assertEqual(finalization.validate_decisions(self.value(),['a']),self.value())
        for v in [{'decisions':[]},{'decisions':self.value()['decisions']*2},self.value(concept_id='other')]:
            with self.assertRaises(ValueError):finalization.validate_decisions(v,['a'])

    def test_no_unsupported_status_or_empty_acceptance(self):
        for changes in [{'definition':''},{'status':'provisional'},{'reason':''},{'new_key':'x'}]:
            with self.assertRaises(ValueError):finalization.validate_decisions(self.value(**changes),['a'])
        self.assertEqual(finalization.validate_decisions(self.value(status='unresolved',definition=''),['a'])['decisions'][0]['status'],'unresolved')

    def test_server_schema_binds_ids_and_disallows_fields(self):
        schema=finalization.decision_format(['a'])['json_schema']
        self.assertTrue(schema['strict'])
        item=schema['schema']['properties']['decisions']['items']
        self.assertFalse(item['additionalProperties'])
        self.assertEqual(item['properties']['concept_id']['enum'],['a'])

    def test_no_tag_items_or_alias_mapping_output(self):
        with self.assertRaises(ValueError):finalization.validate_decisions({'items':[]},['a'])
        with self.assertRaises(ValueError):finalization.validate_decisions(dict(self.value(),aliases=[]),['a'])


class ReviewExportTests(unittest.TestCase):
    def test_export_preserves_original_and_escapes_spreadsheet_formulas(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'vocab.json'
            value={'concepts':[{'concept_id':'c1','key':'color:red','category':'color','name':'=bad',
                   'status':'accepted','definition':'紅色','frequency':{'unique_images':2}}],
                   'proposals':[{'proposal_id':'p1','action':'keep','source':'c1','reason':'@danger'}]}
            source.write_text(json.dumps(value),encoding='utf-8');before=source.read_bytes()
            stats=review_export.export(source,root/'out')
            self.assertEqual(stats['concept_rows'],1)
            self.assertEqual(source.read_bytes(),before)
            with (root/'out/tags.csv').open(encoding='utf-8-sig',newline='') as f:
                row=next(csv.DictReader(f));self.assertEqual(row['name'],"'=bad");self.assertEqual(row['source_unique_images'],'2')
            with (root/'out/decisions.csv').open(encoding='utf-8-sig',newline='') as f:
                self.assertEqual(next(csv.DictReader(f))['reason'],"'@danger")

    def test_duplicate_concept_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'v.json';p.write_text(json.dumps({'concepts':[{'concept_id':'c'},{'concept_id':'c'}]}))
            with self.assertRaises(ValueError):review_export.export(p,Path(temp)/'out')


class ReviewHarnessTests(unittest.TestCase):
    def test_lint_rejects_claims_and_pre_excuses(self):
        brief = ("Ground floor facts: front door at north; entry lane kept clear; living group on oat rug faces it.\n"
                 "Coordinates/physics are already verified by tools.\n"
                 "North third intentionally left dark/empty (declared negative space, not unfinished).\n"
                 "Known renderer limits (do NOT flag): windows.")
        self.assertEqual({n for n, _, _ in review_harness.lint_program(brief)}, {1, 2, 3, 4})

    def test_lint_accepts_a_program(self):
        program = ("One person reads, cooks and eats upstairs; hosts 2-3 friends for an evening media night in the basement.\n"
                   "Wanted: kitchen + dining, a living group with a focal point, a closed washroom with a usable door, a closed storage room.\n"
                   "Style: white plaster, oak floor, walnut wood, linen and grey fabrics, one sage accent.")
        self.assertEqual(review_harness.lint_program(program), [])

    def test_prompt_is_neutral_and_has_fixed_checklist(self):
        p = review_harness.build_prompt('Wanted: a kitchen.', ['a.png', 'b.png'])
        self.assertIn('Nothing has been verified', p); self.assertIn('do not assume any of it exists', p)
        for item in ('doorway actually be walked through', 'float', 'face their table', 'line up and stay clear', 'requested function exist'):
            self.assertIn(item, p)
        self.assertNotIn('PREVIOUS ROUND', p); self.assertIn('a.png, b.png', p)
        self.assertEqual(review_harness.lint_program(review_harness.RENDER_LIMITS), [])

    def test_prompt_states_view_and_counting_conventions(self):
        p = review_harness.build_prompt('Wanted: a yard.', ['a.jpg'])
        self.assertIn('mirrored left-right', p); self.assertIn('compass words', p)
        self.assertIn('counts as one item', p)
        self.assertEqual(review_harness.lint_program(review_harness.CONVENTIONS), [])

    def test_staged_runs_stop_at_first_revise_and_never_accept_early(self):
        calls = []
        def fake(order):
            def run(job):
                calls.append(job[0]); return order[job[0]]
            return run
        ok = {'verdict': 'ok', 'score': 9, 'issues': []}; bad = {'verdict': 'revise', 'score': 4, 'issues': [{'severity': 'must'}]}
        jobs = [('flash', 1), ('argon', 1)]
        runs, skipped = review_harness.run_jobs(jobs, fake({'flash': bad, 'argon': ok}), staged=True)
        self.assertEqual(calls, ['flash']); self.assertEqual(skipped, [('argon', 1)]); self.assertEqual(review_harness.aggregate(runs)['verdict'], 'revise')
        calls.clear()
        runs, skipped = review_harness.run_jobs(jobs, fake({'flash': ok, 'argon': ok}), staged=True)
        self.assertEqual(calls, ['flash', 'argon']); self.assertEqual(skipped, []); self.assertEqual(review_harness.aggregate(runs)['verdict'], 'ok')
        calls.clear()
        runs, skipped = review_harness.run_jobs(jobs, fake({'flash': {'parse_error': 'x'}, 'argon': ok}), staged=True)
        self.assertEqual(calls, ['flash']); self.assertEqual(review_harness.aggregate(runs)['verdict'], 'revise')
        calls.clear()
        runs, skipped = review_harness.run_jobs(jobs, fake({'flash': bad, 'argon': ok}), staged=False)
        self.assertEqual(sorted(calls), ['argon', 'flash']); self.assertEqual(skipped, [])

    def test_round_cleanup_keeps_only_reply_and_inputs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            rd = Path(t)
            names = ('sheet.jpg', 'program.txt', 'review-prompt.txt', 'review-raw-m-1.json', 'review-run-m-1.json', 'review-reply.json')
            for n in names: (rd / n).write_text('x', encoding='utf-8')
            removed = review_harness.cleanup_round(rd, [{'verdict': 'ok'}], keep_artifacts=False)
            self.assertEqual(sorted(p.name for p in rd.iterdir()), ['program.txt', 'review-reply.json', 'sheet.jpg'])
            self.assertEqual(sorted(removed), ['review-prompt.txt', 'review-raw-m-1.json', 'review-run-m-1.json'])
            for n in names: (rd / n).write_text('x', encoding='utf-8')
            self.assertEqual(review_harness.cleanup_round(rd, [{'parse_error': 'bad json'}], keep_artifacts=False), [])   # keep evidence of a failed parse
            self.assertEqual(review_harness.cleanup_round(rd, [{'verdict': 'ok'}], keep_artifacts=True), [])

    def test_sheets_include_jpeg_and_png_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            for n in ('b.jpg', 'a.png', 'c.jpeg', 'notes.txt', 'review-prompt.txt'): (Path(t) / n).write_bytes(b'x')
            self.assertEqual(review_harness.find_sheets(Path(t)), ['a.png', 'b.jpg', 'c.jpeg'])

    def test_ok_requires_every_run_ok_and_valid(self):
        ok = {'verdict': 'ok', 'score': 8, 'issues': [{'severity': 'nit'}]}
        bad = {'verdict': 'revise', 'score': 4, 'issues': [{'severity': 'must'}]}
        self.assertEqual(review_harness.aggregate([ok, ok])['verdict'], 'ok')
        self.assertEqual(review_harness.aggregate([ok, bad])['verdict'], 'revise')
        self.assertEqual(review_harness.aggregate([ok, {'parse_error': 'x'}])['verdict'], 'revise')
        self.assertEqual(review_harness.aggregate([{'verdict': 'ok', 'issues': [{'severity': 'must'}]}])['verdict'], 'revise')


if __name__ == '__main__':
    unittest.main()
