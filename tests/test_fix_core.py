"""Regression tests for the deco core review findings (B1..B10) plus behaviour pinned by the simplifications."""
import json, tempfile, unittest
from ffxiv_furniture.deco.core import Catalog, Room, Session, DecoError, ROOT

SEED = json.loads((ROOT / 'outputs/designs/hand-tea-room/final-layout.json').read_bytes())
SEED = {k: v for k, v in SEED.items() if k != 'interiorFurniture'}
_cat = None; _room = None


def mk(seed=SEED, **kw):
    global _cat, _room
    _cat = _cat or Catalog(); _room = _room or Room()
    return Session('t', _cat, _room, tempfile.mkdtemp(), seed_layout=seed, **kw)


def P(name, pos, yaw=0, **k): return dict(op='place', name=name, position=pos, yaw_deg=yaw, **k)


def rejected(test, s, ops, **kw):
    rev, n = s.revision, len(s.instances)
    with test.assertRaises(DecoError) as c: s.apply(ops, **kw)
    test.assertEqual((s.revision, len(s.instances)), (rev, n))   # batch unchanged
    return c.exception


class FixCoreTests(unittest.TestCase):
    # ---- B1
    def test_b1_removed_excludes_recreated_ids(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a'), P('Hingan Bench', [3, -3, 0], instance_id='b')])
        r = s.apply([dict(op='remove', instance_id='a'), P('Hingan Sofa', [0, -3, 0], instance_id='a'), dict(op='remove', instance_id='b')])
        self.assertEqual(r['removed'], ['b']); self.assertIn('a', s.instances)

    # ---- B2
    def test_b2_non_dict_op_is_bad_input_with_op_index(self):
        s = mk(); e = rejected(self, s, [P('Hingan Sofa', [0, -3, 0], instance_id='a'), 'x'])
        self.assertEqual(e.code, 'REJECTED'); i = e.issues[0]
        self.assertEqual((i['code'], i['op_index']), ('BAD_INPUT', 1))

    def test_b2_unhashable_or_non_string_instance_id(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        for bad in ([1], {'k': 1}, 5):
            for op in (dict(op='remove', instance_id=bad), dict(op='move', instance_id=bad, delta=[1, 0, 0]),
                       dict(op='rotate', instance_id=bad, yaw_deg=1), P('Hingan Sofa', [0, -3, 0], instance_id=bad)):
                e = rejected(self, s, [op]); self.assertEqual(e.issues[0]['code'], 'BAD_INPUT', op); self.assertEqual(e.issues[0]['op_index'], 0)

    def test_b2_unknown_key_lists_allowed_keys(self):
        s = mk(); e = rejected(self, s, [dict(op='place', name='Hingan Sofa', psotion=[0, -3, 0], position=[0, -3, 0])])
        i = e.issues[0]; self.assertEqual(i['code'], 'BAD_INPUT'); self.assertIn('psotion', i['message']); self.assertIn('position', i['message'])
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        e = rejected(self, s, [dict(op='move', instance_id='a', delat=[1, 0, 0])]); self.assertIn('delat', e.issues[0]['message'])

    def test_b2_place_requires_position(self):
        s = mk(); e = rejected(self, s, [dict(op='place', name='Hingan Sofa', instance_id='a')])
        self.assertEqual(e.issues[0]['code'], 'BAD_INPUT'); self.assertIn('position', e.issues[0]['message'])

    def test_b2_move_needs_exactly_one_of_position_delta(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        for op in (dict(op='move', instance_id='a'), dict(op='move', instance_id='a', position=[1, -3, 0], delta=[1, 0, 0])):
            self.assertEqual(rejected(self, s, [op]).issues[0]['code'], 'BAD_INPUT')

    def test_b2_rotate_needs_exactly_one_of_yaw_forms(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        for op in (dict(op='rotate', instance_id='a'), dict(op='rotate', instance_id='a', yaw_deg=10, yaw_delta_deg=5)):
            self.assertEqual(rejected(self, s, [op]).issues[0]['code'], 'BAD_INPUT')

    def test_b2_existing_instance_with_other_item_rejected(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        e = rejected(self, s, [P('Hingan Bench', [0, -3, 0], instance_id='a')]); self.assertEqual(e.issues[0]['code'], 'BAD_INPUT')
        # same item (by name or id) is still fine
        it = s.cat.item(name='Hingan Sofa')
        s.apply([P('Hingan Sofa', [1, -3, 0], instance_id='a')]); s.apply([dict(op='place', item_id=it['id'], position=[2, -3, 0], instance_id='a')])

    # ---- B3 / B4
    def _lights(self, s):
        return {l['name']: l['item_id'] for l in s.cat.search_materials('', 'light', 60) if l['renderable']}

    def test_b3_validate_uses_pending_fixtures(self):
        s = mk(); lights = self._lights(s); big = 'Star Chandelier'
        if big not in lights: self.skipTest('Star Chandelier mesh not extracted')
        committed = s._ceiling_light_disc('ground')
        if committed is None or committed[0] > 0.8: self.skipTest('seed light unexpectedly large')
        r = s.apply([dict(op='fixture', type='Light', name=big), P('Zabuton Cushion', [1.6, 0, 4.0], instance_id='z')])
        self.assertIn('CEILING_LIGHT_CONFLICT', {w['code'] for w in r['warnings']})
        s2 = mk()   # control: same placement without the new light is clean
        r2 = s2.apply([P('Zabuton Cushion', [1.6, 0, 4.0], instance_id='z')])
        self.assertNotIn('CEILING_LIGHT_CONFLICT', {w['code'] for w in r2['warnings']})

    def test_b3_restore_validates_snapshot_fixtures(self):
        s = mk(); big = 'Star Chandelier'
        if big not in self._lights(s): self.skipTest('Star Chandelier mesh not extracted')
        s.apply([dict(op='fixture', type='Light', name=big), P('Zabuton Cushion', [1.6, 0, 4.0], instance_id='z')])
        sid = s.snapshot('x')['snapshot_id']
        s.apply([dict(op='fixture', type='Light', name='Oasis Pendant Lamp')])   # committed fixtures are now small
        seen = []
        orig = s.validate
        def spy(inst, issues, op_index=None):
            n0 = len(issues); orig(inst, issues, op_index); seen.extend(i['code'] for i in issues[n0:])
        s.validate = spy
        s.restore(sid)
        self.assertIn('CEILING_LIGHT_CONFLICT', seen)
        self.assertEqual(s.fixtures['Light']['name'], big)

    def test_b4_light_mesh_resolved_via_asset_key(self):
        s = mk(); lights = self._lights(s)
        for nm in ('Flame Ceiling Fan & Lamp', 'Serpent Ceiling Fan & Lamp', "Watcher's Palace Ceiling Lamp"):
            if nm not in lights: continue
            s.fixtures = {'Light': dict(item_id=lights[nm], name=nm)}
            d = s._ceiling_light_disc('ground'); self.assertIsNotNone(d, nm); self.assertGreater(d[0], 0.1)

    def test_b4_missing_mesh_is_unreadable_not_crash(self):
        s = mk(); s.fixtures = {'Light': dict(item_id=-12345, name='No Such Lamp')}
        self.assertIsNone(s._ceiling_light_disc('ground'))

    # ---- B5
    def _over_cap(self):
        f = _cat_item('Hingan Sofa')
        lay = {**SEED, 'interiorFurniture': [dict(itemId=f['id'], name=f['name'], transform=dict(location=[0, -300, 0], rotation=[0, 0, 0, 1], scale=[1, 1, 1]), properties={}, attachments=[]) for _ in range(455)]}
        global _room
        _room = _room or Room()
        return Session('big', _cat, _room, tempfile.mkdtemp(), from_layout=lay)

    def test_b5_over_cap_session_allows_removes_and_noop_dyes(self):
        s = self._over_cap(); self.assertEqual(len(s.instances), 455)
        s.apply([dict(op='dye', instance_id='i1', color='default')])
        r = s.apply([dict(op='remove', instance_id='i1')]); self.assertEqual(r['count'], 454)

    def test_b5_over_cap_session_rejects_growth_with_remove_count(self):
        s = self._over_cap()
        e = rejected(self, s, [P('Hingan Sofa', [0, -3, 0])])
        m = next(i for i in e.issues if i['code'] == 'BUDGET_EXCEEDED')['message']
        self.assertIn('remove 6', m)
        s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='n'), dict(op='remove', instance_id='i1'), dict(op='remove', instance_id='i2')])   # net shrink is fine

    # ---- B6
    def test_b6_inspect_level_filters_instances_and_surfaces(self):
        s = mk(); s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='g'), P('Hingan Sitting Table', [0, -5, 7.0], instance_id='u')])
        if 'upper' not in s.room.levels: self.skipTest('no upper')
        g = s.inspect(level='ground'); u = s.inspect(level='upper')
        self.assertEqual([v['instance_id'] for v in g['instances']], ['g']); self.assertEqual([v['instance_id'] for v in u['instances']], ['u'])
        self.assertTrue(g['surfaces'] and {x['owner_id'] for x in g['surfaces']} == {'g'}); self.assertEqual({x['owner_id'] for x in u['surfaces']}, {'u'})
        self.assertEqual((g['used'], u['used']), (2, 2))

    # ---- B7
    def test_b7_rotate_invalid_anchor(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0], instance_id='a')])
        self.assertEqual(rejected(self, s, [dict(op='rotate', instance_id='a', yaw_deg=10, anchor='zzz')]).issues[0]['code'], 'BAD_INPUT')

    # ---- B8
    def test_b8_search_limits_clamped(self):
        c = _cat_or_new()
        for lim in (-5, 0):
            self.assertEqual(len(c.search_materials('', 'wall', limit=lim)), 1); self.assertEqual(len(c.search_dyes('', limit=lim)), 1)
        self.assertLessEqual(len(c.search_materials('', 'wall', limit=10_000)), 60); self.assertLessEqual(len(c.search_dyes('', limit=10_000)), 60)

    # ---- B9
    def test_b9_place_on_and_face_reject_self_target(self):
        s = mk(); s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t')])
        for op in (dict(op='place_on', instance_id='t', target_id='t'), dict(op='face', instance_id='t', target_id='t')):
            self.assertEqual(rejected(self, s, [op]).issues[0]['code'], 'BAD_INPUT')

    # ---- B10
    def test_b10_ids_never_reused_after_undo(self):
        s = mk(); r1 = s.apply([P('Hingan Sofa', [0, -3, 0])]); a = r1['changed'][0]['instance_id']
        s.undo(); r2 = s.apply([P('Hingan Bench', [0, -3, 0])]); self.assertNotEqual(r2['changed'][0]['instance_id'], a)

    def test_b10_ids_never_reused_after_restore_and_reload(self):
        s = mk(); sid = s.snapshot('empty')['snapshot_id']
        used = set()
        for x in (0, 2, 4):
            used.add(s.apply([P('Hingan Bench', [x, -3, 0])])['changed'][0]['instance_id'])
        s.restore(sid); self.assertEqual(len(s.instances), 0)
        n = s.apply([P('Hingan Sofa', [0, -3, 0])])['changed'][0]['instance_id']; self.assertNotIn(n, used)
        s2 = Session('t', _cat, _room, str(s.dir.parent), seed_layout=SEED)   # reload from state.json
        s2.undo(); s2.undo()
        m = s2.apply([P('Hingan Sofa', [0, -3, 0])])['changed'][0]['instance_id']; self.assertNotIn(m, used | {n})

    def test_b10_old_state_file_without_counter_loads(self):
        s = mk(); s.apply([P('Hingan Sofa', [0, -3, 0])])
        p = s.dir / 'state.json'; d = json.loads(p.read_text(encoding='utf-8')); d.pop('id_floor', None); p.write_text(json.dumps(d), encoding='utf-8')
        s2 = Session('t', _cat, _room, str(s.dir.parent), seed_layout=SEED)
        self.assertEqual(len(s2.instances), 1); self.assertTrue(s2.apply([P('Hingan Bench', [2, -3, 0])])['ok'])


def _cat_or_new():
    global _cat
    _cat = _cat or Catalog(); return _cat


def _cat_item(name):
    return _cat_or_new().item(name=name)


if __name__ == '__main__':
    unittest.main()
