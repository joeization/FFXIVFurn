"""Regression tests for the deco server/analyze/driver bug sweep (one test per confirmed bug)."""
import asyncio, io, json, math, os, shutil, subprocess, sys, tempfile, time, unittest
from contextlib import redirect_stderr
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError
from shapely.geometry import box

from ffxiv_furniture.deco import analyze as an, server
from ffxiv_furniture.deco.core import Catalog, DecoError, Room, Session, ROOT

REAL_BOOT = server._boot

LOG = 28154   # Log Partition
SEED = json.loads((ROOT / 'outputs/designs/hand-tea-room/final-layout.json').read_bytes())
SEED = {k: v for k, v in SEED.items() if k != 'interiorFurniture'}
_cat = None; _rooms = {}


def mk(size='Medium'):
    global _cat
    _cat = _cat or Catalog()
    if size not in _rooms: _rooms[size] = Room('Shirogane', size)
    seed = dict(SEED, houseSize=size) if size != 'Medium' else SEED
    return Session('t', _cat, _rooms[size], tempfile.mkdtemp(), seed_layout=seed)


def P(item, x, y, yaw=0, z=0): return dict(op='place', item_id=item, position=[x, y, z], yaw_deg=yaw)


def code_of(err):
    """BAD_INPUT etc. from a ToolError whose message is the JSON payload."""
    return json.loads(str(err))['error']['code']


class RenderCacheRevisionTests(unittest.TestCase):
    """B1: a cache hit from an older revision must survive later prunes."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name)
        lay = json.loads((ROOT / 'data/seeds/apartment-seed.json').read_bytes()); lay.update(houseSize='Small', interiorFurniture=[])
        self.lay = lay
        self.session = SimpleNamespace(dir=self.root, revision=0, room=SimpleNamespace(house_size='Small', style='Shirogane'), instances={},
                                       layout_dict=lambda: deepcopy(self.lay))
        for p in (patch.object(server, '_boot', return_value=self.session), patch.object(server, '_sess', self.session)):
            p.start(); self.addCleanup(p.stop)
        server._render_cache.clear()

    def render(self, view='entry', **kw):
        return json.loads(server.render(view=view, width=96, height=64, lighting='off', mirror=False, **kw)[-1])

    def test_hit_from_older_revision_survives_later_renders(self):
        base = deepcopy(self.lay)
        self.render('entry')                                          # r0, layout A
        self.session.revision = 1; self.lay['marker'] = 1; self.render('entry')     # r1, layout B
        self.session.revision = 2; self.lay.clear(); self.lay.update(base)           # "undo": layout A again at revision 2
        hit = self.render('entry')
        self.assertTrue(hit['cache_hit'])
        self.assertTrue(Path(hit['image']).is_file())
        self.assertIn('r2-', Path(hit['image']).name)                  # re-homed to the current revision
        self.render('north')                                           # r2 again -> prune must not eat the returned image
        self.session.revision = 3; self.render('north')
        again = self.render('entry')
        self.assertTrue(Path(again['image']).is_file())

    def test_rehomed_hit_exists_after_next_render_same_revision(self):
        base = deepcopy(self.lay)
        self.render('entry')
        self.session.revision = 1; self.lay['marker'] = 1; self.render('north')
        self.session.revision = 2; self.lay.clear(); self.lay.update(base)
        hit = self.render('entry'); self.assertTrue(hit['cache_hit'])
        self.render('north')
        self.assertTrue(Path(hit['image']).is_file())

    def test_hit_with_diagnostics_artifacts_survive(self):
        base = deepcopy(self.lay)
        self.render('entry', diagnostics=True)
        self.session.revision = 1; self.lay['marker'] = 1; self.render('north')
        self.session.revision = 2; self.lay.clear(); self.lay.update(base)
        hit = self.render('entry', diagnostics=True); self.assertTrue(hit['cache_hit'])
        self.render('north')
        self.assertTrue(Path(hit['image']).is_file())
        for p in hit['artifacts'].values(): self.assertTrue(Path(p).is_file(), p)
        manifest = json.loads(Path(hit['artifacts']['manifest']).read_text(encoding='utf-8'))
        self.assertEqual(manifest['views'][0]['image'], hit['image'])
        self.assertEqual(manifest['artifacts'], hit['artifacts'])
        request = json.loads(Path(hit['artifacts']['review_request']).read_text(encoding='utf-8'))
        self.assertEqual(request['views'], [hit['image']])

    def test_labeled_crop_cache_hit_rehomes_all_paths(self):
        base = deepcopy(self.lay)
        kw = dict(labels=True, crop=[0, 0, 64, 64], diagnostics=True)
        self.render('entry', **kw)
        self.session.revision = 1; self.lay['marker'] = 1; self.render('north')
        self.session.revision = 2; self.lay.clear(); self.lay.update(base)
        hit = self.render('entry', **kw)
        self.assertTrue(hit['cache_hit'])
        self.render('north')
        self.assertTrue(Path(hit['image']).is_file())
        manifest = json.loads(Path(hit['artifacts']['manifest']).read_text(encoding='utf-8'))
        self.assertIn('r2-', Path(manifest['views'][0]['image']).name)
        self.assertTrue(Path(manifest['views'][0]['image']).is_file())


class WallGapTests(unittest.TestCase):
    def test_b2_partition_near_wall_with_pillars_is_reported_on_both_sides(self):
        south = mk(); south.apply([P(LOG, 1.5, 5.7, 90)]); north = mk(); north.apply([P(LOG, 1.5, -5.7, 90)])
        a, b = an.analyze(south)['wall_gaps'], an.analyze(north)['wall_gaps']
        self.assertEqual([g['b'] for g in a], ['room-wall'])
        self.assertEqual([g['b'] for g in b], ['room-wall'], b)
        self.assertAlmostEqual(a[0]['width_m'], b[0]['width_m'], 2)

    def test_b3_at_is_slit_centre_end_to_end(self):
        s = mk(); s.apply([P(LOG, 0, 0), P(LOG, 4.2, 0)])
        g = an.analyze(s)['wall_gaps']
        self.assertEqual(len(g), 1)
        self.assertAlmostEqual(g[0]['at'][1], 0.0, delta=0.06)
        self.assertAlmostEqual(g[0]['at'][0], 2.1, delta=0.06)
        self.assertAlmostEqual(g[0]['width_m'], 0.2, delta=0.01)


class CheckRoutesLevelTests(unittest.TestCase):
    def test_b4_unknown_level_for_house_rejected(self):
        s = mk('Small')
        self.assertNotIn('upper', s.room.levels)
        with self.assertRaises(DecoError) as c:
            an.check_routes(s, [dict(name='r', points=[[0, 0], [1, 1]])], level='upper')
        self.assertEqual(c.exception.code, 'BAD_INPUT')
        r = an.check_routes(s, [dict(name='r', points=[[0, 0], [1, 1]])], level='basement')   # Small has a basement
        self.assertTrue(r[0]['clear'])
        with self.assertRaises(DecoError): an.check_routes(s, [dict(name='r', points=[[0, 0], [1, 1]])], level='bogus')


class _ServerBase(unittest.TestCase):
    def setUp(self):
        self.s = mk()
        for p in (patch.object(server, '_boot', return_value=self.s), patch.object(server, '_sess', self.s)):
            p.start(); self.addCleanup(p.stop)


class UnknownKwargTests(_ServerBase):
    def test_b5_camera_dict_unknown_key_rejected(self):
        for bad in (dict(position=[0, 0, 5], target=[0, 0, 0], cutawya=True), dict(position=[0, 0, 5], target=[0, 0, 0], hide_above=3)):
            with self.subTest(bad=bad), self.assertRaises(DecoError) as c: server._camera(bad, self.s)
            self.assertEqual(c.exception.code, 'BAD_INPUT'); self.assertIn('unknown', c.exception.message.lower())
        with self.assertRaises(ToolError) as c: server.render(view=dict(position=[0, 0, 5], target=[0, 0, 0], fov=60, bogus=1), width=96, height=64)
        self.assertEqual(code_of(c.exception), 'BAD_INPUT')
        with self.assertRaises(ToolError) as c: server.render_sheet(views=[dict(label='x', view=dict(position=[0, 0, 5], target=[0, 0, 0], bogus=1))], width=96, height=64)
        self.assertEqual(code_of(c.exception), 'BAD_INPUT')

    def test_b5_misspelled_tool_argument_rejected_on_real_tool_path(self):
        async def call(name, args): return await server.mcp.call_tool(name, args)
        with self.assertRaises(Exception) as c: asyncio.run(call('search_furniture', {'qurey': 'chair', 'limit': 2}))
        self.assertIn('qurey', str(c.exception))
        with self.assertRaises(Exception) as c: asyncio.run(call('status', {'foo': 1}))
        self.assertIn('foo', str(c.exception))
        asyncio.run(call('status', {}))   # valid calls still work


class BadInputTests(_ServerBase):
    def assertBad(self, fn, *a, **kw):
        with self.assertRaises(ToolError) as c: fn(*a, **kw)
        self.assertEqual(code_of(c.exception), 'BAD_INPUT', str(c.exception))

    def test_b6_wrap_maps_value_type_key_errors_and_keeps_traceback(self):
        for exc in (ValueError('v'), TypeError('t'), KeyError('k')):
            def boom(exc=exc): raise exc
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(ToolError) as c: server._wrap(boom)
            self.assertEqual(code_of(c.exception), 'BAD_INPUT')
            self.assertIn('Traceback', err.getvalue())
        with self.assertRaises(RuntimeError): server._wrap(lambda: (_ for _ in ()).throw(RuntimeError('real bug')))

    def test_b6_analyze_args(self):
        for kw in (dict(start=[1, 2, 3]), dict(start=['a', 'b']), dict(start=[float('nan'), 0]), dict(start=[1]), dict(path_width_m=0),
                   dict(path_width_m=-1), dict(path_width_m=float('nan')), dict(path_width_m=float('inf')), dict(front_depth_m=0), dict(front_depth_m=-0.5),
                   dict(front_depth_m=float('nan'))):
            with self.subTest(kw=kw): self.assertBad(server.analyze_layout, **kw)
        self.assertTrue(server.analyze_layout(start=[0, 5])['ok'])

    def test_b6_render_args(self):
        cam = dict(position=[0, 0, 5], target=[0, 0, 0])
        self.assertBad(server.render, view='entry', width=96, height=64, lighting='bogus')
        self.assertBad(server.render, view='entry', width=96, height=64, dye='bogus')
        for bad in (dict(position=[0, 0], target=[0, 0, 0]), dict(position=[0, 0, 5], target=[0, 0, 0, 1]), dict(position=['a', 0, 5], target=[0, 0, 0]),
                    dict(position=[float('nan'), 0, 5], target=[0, 0, 0]), dict(position=[0, 0, 5], target=[0, 0, float('inf')]), dict(position='abc', target=[0, 0, 0]),
                    dict(cam, fov='x'), dict(cam, fov=1), dict(cam, fov=175), dict(cam, fov=float('nan')), dict(cam, fov=True)):
            with self.subTest(bad=bad): self.assertBad(server.render, view=bad, width=96, height=64)
        self.assertEqual(server._camera(dict(cam, fov=60), self.s)['fov'], 60)
        self.assertEqual(server._camera(cam, self.s)['fov'], 70)

    def test_b6_boot_bad_max_patch_is_bad_input(self):
        with patch.object(server, '_sess', None), patch.dict(os.environ, {'DECO_MAX_PATCH': 'abc', 'DECO_SEED': str(ROOT / 'data/seeds/medium-seed.json'), 'DECO_SESSION': 'zz-fix-server-patch'}):
            with self.assertRaises(DecoError) as c: REAL_BOOT()
        self.assertEqual(c.exception.code, 'BAD_INPUT')
        shutil.rmtree(ROOT / 'outputs/deco-sessions/zz-fix-server-patch', ignore_errors=True)

    def test_set_fixtures_empty_error_lists_window_door(self):
        with self.assertRaises(ToolError) as c: server.set_fixtures()
        self.assertEqual(code_of(c.exception), 'BAD_INPUT')
        msg = str(c.exception)
        for w in ('wall', 'floor', 'light', 'window', 'door'): self.assertIn(w, msg)


class TopViewTests(unittest.TestCase):
    def assert_tilt_along_y(self, cam):
        dx = cam['position'][0] - cam['target'][0]; dy = cam['position'][1] - cam['target'][1]
        self.assertAlmostEqual(dx, 0.0, places=6)    # no x tilt: +x stays horizontal in the plan
        self.assertLess(dy, 0)                        # tilt toward -y like _generated_cameras: north up

    def test_b7_top_cameras_tilt_along_minus_y(self):
        self.assert_tilt_along_y(server.APT_CAMERAS['top'])
        self.assert_tilt_along_y(server.CAMERAS['up_top'])
        gen = server._generated_cameras(Room('Shirogane', 'Medium'))
        self.assert_tilt_along_y(dict(position=gen['top']['position'], target=gen['top']['target']))

    def test_b7_exterior_top(self):
        fake = SimpleNamespace(cat=SimpleNamespace(scope='exterior'), room=SimpleNamespace(floor=box(-10, -10, 10, 10)))
        with patch.object(server, '_sess', fake): cams = server._cameras()
        self.assert_tilt_along_y(cams['top'])
        # the renderer's own basis: tilting along -y keeps +x as the image's horizontal axis
        import numpy as np
        pos = np.array(cams['top']['position'], float); tgt = np.array(cams['top']['target'], float)
        f = tgt - pos; right = np.cross(f, [0, 0, 1]); right /= np.linalg.norm(right)
        self.assertGreater(right[0], 0.99)


class RendererVersionTests(unittest.TestCase):
    def test_shared_render_helpers_are_in_cache_fingerprint(self):
        version = server._renderer_version()
        self.assertIn('common.py:', version)
        self.assertIn('lighting.py:', version)

    def test_s1_missing_map_files_count_as_zero(self):
        with patch.object(server, 'source_path', lambda *a, **k: Path('C:/zz-nonexistent-houses')):
            v = server._renderer_version()
        self.assertIn('XIVSmallExterior.umap:0', v)


class DriverTests(unittest.TestCase):
    SEED = ROOT / 'data/seeds/small-seed.json'

    def setUp(self):
        self.name = f'zz-fix-server-drv-{os.getpid()}'
        self.dir = ROOT / 'outputs/deco-sessions' / self.name
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))

    def test_b8_ctor_failure_kills_child_and_closes_stderr(self):
        from scripts import deco_driver
        rec = []
        orig = subprocess.Popen

        class Rec(orig):
            def __init__(self, *a, **k): super().__init__(*a, **k); rec.append((self, k.get('stderr')))
        with patch.object(deco_driver.subprocess, 'Popen', Rec):
            with self.assertRaises((TimeoutError, deco_driver.ToolCallError)):
                deco_driver.DecoClient(self.name, self.SEED, ready_timeout=0.3)
        p, err = rec[0]
        self.assertIsNotNone(p.poll())          # child reaped, not orphaned
        self.assertTrue(err.closed)             # stderr handle released

    def test_b8_bad_seed_error_carries_stderr_tail(self):
        from scripts.deco_driver import DecoClient, ToolCallError
        with self.assertRaises(ToolCallError) as c:
            DecoClient(self.name, ROOT / 'data/seeds/zz-does-not-exist.json', ready_timeout=120)
        self.assertIn('exited', str(c.exception))
        self.assertTrue('DECO_SEED' in str(c.exception) or 'Cannot read' in str(c.exception) or 'Traceback' in str(c.exception), str(c.exception)[-400:])

    def test_b8_payload_closed_and_fast_death_detection(self):
        from scripts.deco_driver import DecoClient, ToolCallError
        c = DecoClient(self.name, self.SEED, max_patch='7.2')
        try:
            with self.assertRaises(ToolCallError) as e:
                c('batch', {'operations': [dict(op='place', name='No Such Item', position=[0, 0, 0])]})
            self.assertIsInstance(e.exception.payload, dict)
            self.assertIn('code', e.exception.payload); self.assertIn('message', e.exception.payload)
            with self.assertRaises(ToolCallError) as e:
                c('no_such_tool', {})
            self.assertTrue(hasattr(e.exception, 'payload'))   # present (None when the text was not a payload)
            c._p.kill()                                        # the interactive client dies underneath us
            t = time.time()
            with self.assertRaises(ToolCallError): c('status')
            self.assertLess(time.time() - t, 3.0)
        finally:
            c.close()
        with self.assertRaises(ToolCallError) as e: c('status')
        self.assertIn('client closed', str(e.exception))


class SharedLevelRuleTests(unittest.TestCase):
    def test_render_context_follows_the_shared_floor_rule(self):
        from ffxiv_furniture.deco import server
        span = lambda zb, zt: server._levels_of_spans([(zb, zt)])
        self.assertEqual(span(-1.1, -0.9), {'basement'})   # hung from the basement ceiling
        self.assertEqual(span(-4.4, -2.69), {'basement'})
        self.assertEqual(span(7.0, 8.0), {'upper'})
        self.assertEqual(span(0.0, 0.02), {'ground'})


if __name__ == '__main__':
    unittest.main()
