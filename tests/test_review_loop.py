"""The multi-round, model-judged loop with a fake reviewer (no rendering, no agy)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from shapely.geometry import Polygon, box
from ffxiv_furniture.design import place as P, refine as R, visual as V
from ffxiv_furniture.design.layout_io import export_layout

ROOM = {'polygon': Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), 'ceiling_z': 6.5, 'corridor': None, 'keepouts': [box(9, 4, 12, 8)]}


def geo(name, w, d, h, category, **info):
    g = {'name': name, 'length': w, 'width': d, 'height': h, 'category': category, 'lo': [-w / 2, -d / 2, 0.0], 'hi': [w / 2, d / 2, h], 'ptype': 'floor', 'front_deg': 90.0}; g.update(info); return g


def setup():
    res = [{'zone_index': 0, 'zone': 'z0', 'area_fraction': 1.0, 'role': 'storage', 'count': 3, 'query': 'q', 'item_id': 3, 'geometry': geo('Shelf', 1.5, 0.5, 2.0, 'Furniture/Shelf'), 'placement': {}, 'entry_key': '0:0'}]
    scene, _ = P.place_all(ROOM, res); solids = [s[2] for s in scene.solid]; pls = [p for p in scene.placements if p['layer'] in ('solid', 'seat')]
    objs = [R.Obj(i, p, it) for i, (p, it) in enumerate(zip(pls, solids))]
    src = {'interiorScale': 100, 'interiorFurniture': [{'transform': {'location': [0, 0, 0], 'rotation': [0, 0, 0, 1]}} for _ in objs]}
    return scene, objs, src


class LoopTests(unittest.TestCase):
    def run_loop(self, replies, rounds=3, allow_remove=True):
        scene, objs, src = setup(); prompts = []; it = iter(replies)
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
        scene, objs, src = setup()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(V, 'call_agy', lambda *a, **k: ('not json at all', '')), mock.patch.object(V, 'render_round', lambda *a, **k: []):
            hist, stop = V.critique_loop(scene, objs, tmp, tmp, src, 100, False, {'house_size': 'Medium'}, root=Path(tmp))
        self.assertEqual(stop, 'unparseable model reply')

    def test_external_file_protocol_waits_then_continues(self):
        scene, objs, src = setup()
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


if __name__ == '__main__':
    unittest.main()
