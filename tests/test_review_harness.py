"""Review harness must keep the reviewer independent of the orchestrator (no claimed results, no pre-excuses, fresh rounds,
unanimous ok). Regression for a case where an orchestrator-written brief turned a broken design into 'ok'."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('review', ROOT / 'scripts/review_deco.py')
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)


class ReviewHarnessTests(unittest.TestCase):
    def test_lint_rejects_claims_and_pre_excuses(self):
        brief = ("Ground floor facts: front door at north; entry lane kept clear; living group on oat rug faces it.\n"
                 "Coordinates/physics are already verified by tools.\n"
                 "North third intentionally left dark/empty (declared negative space, not unfinished).\n"
                 "Known renderer limits (do NOT flag): windows.")
        self.assertEqual({n for n, _, _ in R.lint_program(brief)}, {1, 2, 3, 4})

    def test_lint_accepts_a_program(self):
        program = ("One person reads, cooks and eats upstairs; hosts 2-3 friends for an evening media night in the basement.\n"
                   "Wanted: kitchen + dining, a living group with a focal point, a closed washroom with a usable door, a closed storage room.\n"
                   "Style: white plaster, oak floor, walnut wood, linen and grey fabrics, one sage accent.")
        self.assertEqual(R.lint_program(program), [])

    def test_prompt_is_neutral_and_has_fixed_checklist(self):
        p = R.build_prompt('Wanted: a kitchen.', ['a.png', 'b.png'])
        self.assertIn('Nothing has been verified', p); self.assertIn('do not assume any of it exists', p)
        for item in ('doorway actually be walked through', 'float', 'face their table', 'line up and stay clear', 'requested function exist'):
            self.assertIn(item, p)
        self.assertNotIn('PREVIOUS ROUND', p); self.assertIn('a.png, b.png', p)
        self.assertEqual(R.lint_program(R.RENDER_LIMITS), [])

    def test_prompt_states_view_and_counting_conventions(self):
        p = R.build_prompt('Wanted: a yard.', ['a.jpg'])
        self.assertIn('mirrored left-right', p); self.assertIn('compass words', p)
        self.assertIn('counts as one item', p)
        self.assertEqual(R.lint_program(R.CONVENTIONS), [])

    def test_staged_runs_stop_at_first_revise_and_never_accept_early(self):
        calls = []
        def fake(order):
            def run(job):
                calls.append(job[0]); return order[job[0]]
            return run
        ok = {'verdict': 'ok', 'score': 9, 'issues': []}; bad = {'verdict': 'revise', 'score': 4, 'issues': [{'severity': 'must'}]}
        jobs = [('flash', 1), ('argon', 1)]
        runs, skipped = R.run_jobs(jobs, fake({'flash': bad, 'argon': ok}), staged=True)
        self.assertEqual(calls, ['flash']); self.assertEqual(skipped, [('argon', 1)]); self.assertEqual(R.aggregate(runs)['verdict'], 'revise')
        calls.clear()
        runs, skipped = R.run_jobs(jobs, fake({'flash': ok, 'argon': ok}), staged=True)
        self.assertEqual(calls, ['flash', 'argon']); self.assertEqual(skipped, []); self.assertEqual(R.aggregate(runs)['verdict'], 'ok')
        calls.clear()
        runs, skipped = R.run_jobs(jobs, fake({'flash': {'parse_error': 'x'}, 'argon': ok}), staged=True)
        self.assertEqual(calls, ['flash']); self.assertEqual(R.aggregate(runs)['verdict'], 'revise')
        calls.clear()
        runs, skipped = R.run_jobs(jobs, fake({'flash': bad, 'argon': ok}), staged=False)
        self.assertEqual(sorted(calls), ['argon', 'flash']); self.assertEqual(skipped, [])

    def test_round_cleanup_keeps_only_reply_and_inputs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            rd = Path(t)
            names = ('sheet.jpg', 'program.txt', 'review-prompt.txt', 'review-raw-m-1.json', 'review-run-m-1.json', 'review-reply.json')
            for n in names: (rd / n).write_text('x', encoding='utf-8')
            removed = R.cleanup_round(rd, [{'verdict': 'ok'}], keep_artifacts=False)
            self.assertEqual(sorted(p.name for p in rd.iterdir()), ['program.txt', 'review-reply.json', 'sheet.jpg'])
            self.assertEqual(sorted(removed), ['review-prompt.txt', 'review-raw-m-1.json', 'review-run-m-1.json'])
            for n in names: (rd / n).write_text('x', encoding='utf-8')
            self.assertEqual(R.cleanup_round(rd, [{'parse_error': 'bad json'}], keep_artifacts=False), [])   # keep evidence of a failed parse
            self.assertEqual(R.cleanup_round(rd, [{'verdict': 'ok'}], keep_artifacts=True), [])

    def test_sheets_include_jpeg_and_png_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            for n in ('b.jpg', 'a.png', 'c.jpeg', 'notes.txt', 'review-prompt.txt'): (Path(t) / n).write_bytes(b'x')
            self.assertEqual(R.find_sheets(Path(t)), ['a.png', 'b.jpg', 'c.jpeg'])

    def test_ok_requires_every_run_ok_and_valid(self):
        ok = {'verdict': 'ok', 'score': 8, 'issues': [{'severity': 'nit'}]}
        bad = {'verdict': 'revise', 'score': 4, 'issues': [{'severity': 'must'}]}
        self.assertEqual(R.aggregate([ok, ok])['verdict'], 'ok')
        self.assertEqual(R.aggregate([ok, bad])['verdict'], 'revise')
        self.assertEqual(R.aggregate([ok, {'parse_error': 'x'}])['verdict'], 'revise')
        self.assertEqual(R.aggregate([{'verdict': 'ok', 'issues': [{'severity': 'must'}]}])['verdict'], 'revise')


if __name__ == '__main__':
    unittest.main()
