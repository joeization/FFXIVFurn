import json
import unittest
from pathlib import Path
import tempfile
from unittest import mock
from ffxiv_furniture.design import concept as C, plan as PL, rerank as RR

VOCAB = {'color:red'}
FACTS = {'house_size': 'Medium', 'ground_floor_area_m2': 335.7, 'free_area_after_stairs_m2': 250.0, 'stairs_keepout_area_m2': 85.0, 'bounding_box_m': [24.0, 16.0],
         'ceiling_height_m': 6.5, 'floor_shape': 'L', 'game_cap_instances_for_whole_house': 450}
CONCEPT = {'title': 'T', 'theme': 'Th', 'style_keywords': ['wa'], 'palette': ['brown'], 'mood': 'calm', 'density_intent': 'rich', 'density_reason': 'showcase', 'target_instances_estimate': 120,
           'focal_points': ['tea alcove'], 'lighting_plan': 'many small lamps', 'architecture_ideas': ['lattice partition'],
           'fixtures': {'floor': 'dark wood floor', 'wall': 'cream plaster', 'light': 'paper lantern'},
           'zones': [{'name': 'Tea alcove', 'purpose': 'tea', 'character': 'intimate', 'area_fraction': 2, 'adjacent_to': ['Library'], 'is_focal': True},
                     {'name': 'Library', 'purpose': 'reading', 'character': 'quiet', 'area_fraction': 1, 'adjacent_to': [], 'is_focal': False}]}


def fake_agy(replies):
    seen = []
    def call(prompt, *, model=None, timeout=420, workdir=None, name='prompt'):
        seen.append((name, prompt)); text = replies(name, prompt)
        return json.dumps({'response': json.dumps(text) if not isinstance(text, str) else text, 'usage': {}}), ''
    call.seen = seen; return call


def zone_items(name, prompt):
    n = 40 if 'Tea alcove' in prompt.split('Your zone:')[1][:80] else 3          # a zone with 40 entries and count 25: far above the old 8 / 6 caps
    roles = ['architecture', 'table', 'seating', 'storage', 'rug', 'decor', 'wall-art', 'lighting']
    return {'items': [{'role': roles[i % len(roles)], 'query': f'dark wood item number {i}', 'count': 25 if i == 0 else 2, 'tags': ['color:red', 'bogus:tag'], 'why': 'x'} for i in range(n)]}


class HierarchicalPlanTests(unittest.TestCase):
    def run_plan(self, items_fn=zone_items):
        agy = fake_agy(lambda name, prompt: CONCEPT if name == 'concept-prompt-attempt0' else items_fn(name, prompt))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(C, 'call_agy', agy):
            plan = C.request_hierarchical_plan('tea room', tmp, facts=FACTS, categories=['Furniture/Table'], tag_examples=['color:red'], vocab_keys=VOCAB, workers=2)
            files = sorted(p.name for p in Path(tmp).iterdir())
        return plan, agy.seen, files

    def test_no_artificial_limits_and_concept_flows_down(self):
        plan, seen, files = self.run_plan()
        self.assertEqual(len(plan['zones'][0]['items']), 40)                       # old cap: 8 entries per zone
        self.assertGreater(plan['planned_instances'], 100)                         # old default cap: 40 instances
        self.assertIn('architecture', {i['role'] for z in plan['zones'] for i in z['items']})
        self.assertIn('concept', plan); self.assertEqual(plan['concept']['density_intent'], 'rich')
        zone_prompts = [p for n, p in seen if n.startswith('zone')]; self.assertEqual(len(zone_prompts), 2)
        for p in zone_prompts: self.assertIn('Overall direction', p); self.assertIn('lattice partition', p); self.assertIn('450', p)   # the game cap is stated as a fact
        self.assertTrue(any(f.startswith('zone00-response') for f in files) and any(f.startswith('concept-response') for f in files))   # counted by the quota tool
        self.assertAlmostEqual(sum(z['area_fraction'] for z in plan['zones']), 1.0)

    def test_game_cap_is_still_enforced(self):
        def too_many(name, prompt): return {'items': [{'role': 'decor', 'query': 'vase', 'count': 300, 'why': 'x'}]}
        with self.assertRaises(RuntimeError): self.run_plan(too_many)             # 2 zones x 300 > 450: rejected, retried, then reported

    def test_bad_zone_reply_is_retried_with_feedback(self):
        calls = {'n': 0}
        def flaky(name, prompt):
            if name.startswith('zone00') :
                calls['n'] += 1
                if calls['n'] == 1: return {'items': [{'role': 'sofa-ish', 'query': 'x', 'count': 1}]}
            return zone_items(name, prompt)
        plan, seen, _ = self.run_plan(flaky); self.assertEqual(calls['n'], 2)
        retry = [p for n, p in seen if n == 'zone00-prompt-attempt1'][0]; self.assertIn('rejected', retry)


class SanitiseTests(unittest.TestCase):
    def test_non_latin_words_are_removed_and_recorded_not_fatal(self):
        C.SANITIZED.clear()
        def cjk(name, prompt): return {'items': [{'role': 'lighting', 'query': 'small dark wood and washi paper floor\u884c\u706f andon lantern', 'count': 2, 'why': 'x'}]}
        plan, seen, files = HierarchicalPlanTests().run_plan(cjk)
        self.assertEqual(plan['zones'][0]['items'][0]['query'], 'small dark wood and washi paper floor andon lantern')
        self.assertTrue(plan['sanitized_queries'] and 'original' in plan['sanitized_queries'][0])

    def test_query_with_no_english_left_is_still_an_error(self):
        with self.assertRaises(ValueError): C.clean_query('\u884c\u706f', 'z')


def resolved_entry(zone, k, n_options=24, planned=3, role='storage'):
    opts = []
    for i in range(n_options):
        g = {'name': f'item{zone}-{k}-{i}', 'category': 'Furniture/Shelf'}
        opts.append({'item_id': 100000 * zone + 1000 * k + i, 'name': g['name'], 'category': 'Furniture/Shelf', 'size_m': [3.0, 1.1, 3.4], 'placement': 'floor', 'matches_role_category': True,
                     'description': 'a tall dark wooden shelf', 'tags': ['form:shelving unit'], 'similarity': 0.9 - i * 0.001, 'geometry': g})
    return {'zone_index': zone, 'zone': f'z{zone}', 'role': role, 'query': 'tall dark wood bookshelf', 'count': planned, 'item_id': opts[0]['item_id'], 'geometry': opts[0]['geometry'], 'similarity': .9, 'options': opts}


class MultiPickTests(unittest.TestCase):
    def test_model_can_pick_several_distinct_candidates_with_own_counts(self):
        res = [resolved_entry(0, 0, planned=3)]
        kept, rep = RR.apply_picks(res, [{'entry': 0, 'picks': [{'i': 4, 'count': 2}, {'i': 9, 'count': 1}, {'i': 17, 'count': 3}], 'why': 'varied wall'}])
        self.assertEqual([(k['geometry']['name'], k['count']) for k in kept], [('item0-0-4', 2), ('item0-0-9', 1), ('item0-0-17', 3)])   # 3 different shelves, total 6 > planned 3: the model decides
        self.assertEqual(rep[0]['distinct'], 3); self.assertEqual(rep[0]['total'], 6)

    def test_none_and_legacy_single_pick_still_work_and_bad_replies_are_rejected(self):
        res = [resolved_entry(0, 0), resolved_entry(0, 1)]
        kept, rep = RR.apply_picks(res, [{'entry': 0, 'picks': [], 'why': 'nothing fits'}, {'entry': 1, 'pick': 5, 'why': 'legacy'}])
        self.assertEqual(len(kept), 1); self.assertEqual(kept[0]['count'], 3); self.assertEqual(rep[0]['picks'], [])
        for bad in ([{'entry': 0, 'picks': [{'i': 99, 'count': 1}]}, {'entry': 1, 'picks': []}], [{'entry': 0, 'picks': [{'i': 1, 'count': 0}]}, {'entry': 1, 'picks': []}],
                    [{'entry': 0, 'picks': [{'i': 1, 'count': 1}, {'i': 1, 'count': 1}]}, {'entry': 1, 'picks': []}], [{'entry': 0, 'picks': []}]):
            with self.assertRaises(ValueError): RR.apply_picks(res, bad)

    def test_resolve_exposes_top24_with_rich_info_and_prompt_lists_them_all(self):
        r = resolved_entry(0, 0); p = RR.build_prompt({'title': 't', 'theme': 'x'}, [r]); self.assertEqual(p.count('"matches_role_category"'), 24); self.assertIn('size_m', p); self.assertIn('placement', p)
        self.assertIn('several different shelves', p)


class RerankBatchTests(unittest.TestCase):
    def test_batches_by_zone_keep_order_and_are_not_a_limit(self):
        resolved = [resolved_entry(zi, k, n_options=2, planned=1, role='decor') for zi in range(3) for k in range(70)]
        def reply(name, prompt):
            n = prompt.count('"entry": '); return [{'entry': i, 'picks': [{'i': 0, 'count': 1}], 'why': 'ok'} for i in range(n)]
        agy = fake_agy(lambda name, prompt: reply(name, prompt))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(RR, 'call_agy', agy):
            kept, report = RR.rerank({'title': 't', 'theme': 'x'}, resolved, tmp)
        self.assertEqual(len(kept), 210); self.assertEqual([r['item_id'] for r in kept], [r['item_id'] for r in resolved])
        self.assertEqual(len(agy.seen), 18); self.assertTrue(all(len(p) < 60000 for _, p in agy.seen))   # ceil(70/12)=6 calls per zone


if __name__ == '__main__':
    unittest.main()
