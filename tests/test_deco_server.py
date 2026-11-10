"""MCP tool arguments, cameras, render caching, output artifacts and contact sheets."""
import asyncio
import io
import json
import numpy as np
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from ffxiv_furniture.deco import server
from ffxiv_furniture.deco.core import DecoError, Room, Session
from ffxiv_furniture.deco.server import SMALL_CAMERAS
from ffxiv_furniture.interiors import STYLES
from ffxiv_furniture.rendering.pipeline import run_pipeline
from mcp.server.fastmcp.exceptions import ToolError
from pathlib import Path
from shapely.geometry import box
from tests.support import P, ROOT, catalog, has_seed, needs_meshes, needs_seed, read_layout, room, seed, session
from types import SimpleNamespace
from unittest.mock import patch

class RouteToolTests(unittest.TestCase):

    def test_check_routes_mcp_tool_wraps_errors(self):
        from unittest.mock import patch
        from mcp.server.fastmcp.exceptions import ToolError
        from ffxiv_furniture.deco import server
        s = session()
        s.apply([P('Hingan Sitting Table', [0, -5, 0], instance_id='t')])
        with patch.object(server, '_boot', return_value=s), patch.object(server, '_sess', s):
            r = server.check_routes(routes=[dict(name='aisle', points=[[-3, -5], [3, -5]])])
            self.assertEqual(r['routes'][0]['blockers'][0]['instance_id'], 't')
            self.assertFalse(r['all_clear'])
            with self.assertRaises(ToolError):
                server.check_routes(routes=[])
REAL_BOOT = server._boot

def code_of(err):
    """BAD_INPUT etc. from a ToolError whose message is the JSON payload."""
    return json.loads(str(err))['error']['code']

class RenderCacheRevisionTests(unittest.TestCase):
    """Cache hits from older revisions survive subsequent pruning."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        lay = read_layout(ROOT / 'data/seeds/apartment-seed.json')
        lay.update(houseSize='Small', interiorFurniture=[])
        self.lay = lay
        self.session = SimpleNamespace(dir=self.root, revision=0, room=SimpleNamespace(house_size='Small', style='Shirogane'), instances={}, layout_dict=lambda: deepcopy(self.lay))
        for p in (patch.object(server, '_boot', return_value=self.session), patch.object(server, '_sess', self.session)):
            p.start()
            self.addCleanup(p.stop)
        server._render_cache.clear()

    def render(self, view='entry', **kw):
        return json.loads(server.render(view=view, width=96, height=64, lighting='off', mirror=False, **kw)[-1])

    @needs_seed('Apartment')
    def test_hit_from_older_revision_survives_later_renders(self):
        base = deepcopy(self.lay)
        self.render('entry')
        self.session.revision = 1
        self.lay['marker'] = 1
        self.render('entry')
        self.session.revision = 2
        self.lay.clear()
        self.lay.update(base)
        hit = self.render('entry')
        self.assertTrue(hit['cache_hit'])
        self.assertIn('r2-', Path(hit['image']).name)
        self.render('north')
        self.assertTrue(Path(hit['image']).is_file())
        self.session.revision = 3
        self.render('north')
        self.assertTrue(Path(self.render('entry')['image']).is_file())

    @needs_seed('Apartment')
    def test_hit_with_diagnostics_artifacts_survive(self):
        base = deepcopy(self.lay)
        self.render('entry', diagnostics=True)
        self.session.revision = 1
        self.lay['marker'] = 1
        self.render('north')
        self.session.revision = 2
        self.lay.clear()
        self.lay.update(base)
        hit = self.render('entry', diagnostics=True)
        self.assertTrue(hit['cache_hit'])
        self.render('north')
        self.assertTrue(Path(hit['image']).is_file())
        for p in hit['artifacts'].values():
            self.assertTrue(Path(p).is_file(), p)
        manifest = read_layout(Path(hit['artifacts']['manifest']))
        self.assertEqual(manifest['views'][0]['image'], hit['image'])
        self.assertEqual(manifest['artifacts'], hit['artifacts'])
        request = read_layout(Path(hit['artifacts']['review_request']))
        self.assertEqual(request['views'], [hit['image']])

    @needs_seed('Apartment')
    def test_labeled_crop_cache_hit_rehomes_all_paths(self):
        base = deepcopy(self.lay)
        kw = dict(labels=True, crop=[0, 0, 64, 64], diagnostics=True)
        self.render('entry', **kw)
        self.session.revision = 1
        self.lay['marker'] = 1
        self.render('north')
        self.session.revision = 2
        self.lay.clear()
        self.lay.update(base)
        hit = self.render('entry', **kw)
        self.assertTrue(hit['cache_hit'])
        self.render('north')
        self.assertTrue(Path(hit['image']).is_file())
        manifest = read_layout(Path(hit['artifacts']['manifest']))
        self.assertIn('r2-', Path(manifest['views'][0]['image']).name)
        self.assertTrue(Path(manifest['views'][0]['image']).is_file())

class _ServerBase(unittest.TestCase):

    def setUp(self):
        self.s = session()
        for p in (patch.object(server, '_boot', return_value=self.s), patch.object(server, '_sess', self.s)):
            p.start()
            self.addCleanup(p.stop)

class UnknownKwargTests(_ServerBase):

    def test_camera_dict_unknown_key_rejected(self):
        for bad in (dict(position=[0, 0, 5], target=[0, 0, 0], cutawya=True), dict(position=[0, 0, 5], target=[0, 0, 0], hide_above=3)):
            with self.subTest(bad=bad), self.assertRaises(DecoError) as c:
                server._camera(bad, self.s)
            self.assertEqual(c.exception.code, 'BAD_INPUT')
            self.assertIn('unknown', c.exception.message.lower())
        with self.assertRaises(ToolError) as c:
            server.render(view=dict(position=[0, 0, 5], target=[0, 0, 0], fov=60, bogus=1), width=96, height=64)
        self.assertEqual(code_of(c.exception), 'BAD_INPUT')
        with self.assertRaises(ToolError) as c:
            server.render_sheet(views=[dict(label='x', view=dict(position=[0, 0, 5], target=[0, 0, 0], bogus=1))], width=96, height=64)
        self.assertEqual(code_of(c.exception), 'BAD_INPUT')

    def test_misspelled_tool_argument_rejected_on_real_tool_path(self):

        async def call(name, args):
            return await server.mcp.call_tool(name, args)
        with self.assertRaises(Exception) as c:
            asyncio.run(call('search_furniture', {'qurey': 'chair', 'limit': 2}))
        self.assertIn('qurey', str(c.exception))
        with self.assertRaises(Exception) as c:
            asyncio.run(call('status', {'foo': 1}))
        self.assertIn('foo', str(c.exception))
        asyncio.run(call('status', {}))

class BadInputTests(_ServerBase):

    def assertBad(self, fn, *a, **kw):
        with self.assertRaises(ToolError) as c:
            fn(*a, **kw)
        self.assertEqual(code_of(c.exception), 'BAD_INPUT', str(c.exception))

    def test_wrap_maps_value_type_key_errors_and_keeps_traceback(self):
        for exc in (ValueError('v'), TypeError('t'), KeyError('k')):

            def boom(exc=exc):
                raise exc
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(ToolError) as c:
                server._wrap(boom)
            self.assertEqual(code_of(c.exception), 'BAD_INPUT')
            self.assertIn('Traceback', err.getvalue())
        with self.assertRaises(RuntimeError):
            server._wrap(lambda: (_ for _ in ()).throw(RuntimeError('real bug')))

    def test_analyze_args(self):
        for kw in (dict(start=[1, 2, 3]), dict(start=['a', 'b']), dict(start=[float('nan'), 0]), dict(start=[1]), dict(path_width_m=0), dict(path_width_m=-1), dict(path_width_m=float('nan')), dict(path_width_m=float('inf')), dict(front_depth_m=0), dict(front_depth_m=-0.5), dict(front_depth_m=float('nan'))):
            with self.subTest(kw=kw):
                self.assertBad(server.analyze_layout, **kw)
        self.assertTrue(server.analyze_layout(start=[0, 5])['ok'])

    def test_render_args(self):
        cam = dict(position=[0, 0, 5], target=[0, 0, 0])
        self.assertBad(server.render, view='entry', width=96, height=64, lighting='bogus')
        self.assertBad(server.render, view='entry', width=96, height=64, dye='bogus')
        for bad in (dict(position=[0, 0], target=[0, 0, 0]), dict(position=[0, 0, 5], target=[0, 0, 0, 1]), dict(position=['a', 0, 5], target=[0, 0, 0]), dict(position=[float('nan'), 0, 5], target=[0, 0, 0]), dict(position=[0, 0, 5], target=[0, 0, float('inf')]), dict(position='abc', target=[0, 0, 0]), dict(cam, fov='x'), dict(cam, fov=1), dict(cam, fov=175), dict(cam, fov=float('nan')), dict(cam, fov=True)):
            with self.subTest(bad=bad):
                self.assertBad(server.render, view=bad, width=96, height=64)
        self.assertEqual(server._camera(dict(cam, fov=60), self.s)['fov'], 60)
        self.assertEqual(server._camera(cam, self.s)['fov'], 70)

    def test_boot_bad_max_patch_is_bad_input(self):
        with patch.object(server, '_sess', None), patch.dict(os.environ, {'DECO_MAX_PATCH': 'abc', 'DECO_SEED': str(ROOT / 'data/seeds/medium-seed.json'), 'DECO_SESSION': 'zz-server-invalid-patch'}):
            with self.assertRaises(DecoError) as c:
                REAL_BOOT()
        self.assertEqual(c.exception.code, 'BAD_INPUT')
        shutil.rmtree(ROOT / 'outputs/deco-sessions/zz-server-invalid-patch', ignore_errors=True)

    def test_set_fixtures_empty_error_lists_window_door(self):
        with self.assertRaises(ToolError) as c:
            server.set_fixtures()
        self.assertEqual(code_of(c.exception), 'BAD_INPUT')
        msg = str(c.exception)
        for w in ('wall', 'floor', 'light', 'window', 'door'):
            self.assertIn(w, msg)

class TopViewTests(unittest.TestCase):

    def assert_tilt_along_y(self, cam):
        dx = cam['position'][0] - cam['target'][0]
        dy = cam['position'][1] - cam['target'][1]
        self.assertAlmostEqual(dx, 0.0, places=6)
        self.assertLess(dy, 0)

    def test_top_cameras_tilt_along_minus_y(self):
        import numpy as np
        self.assert_tilt_along_y(server.APT_CAMERAS['top'])
        self.assert_tilt_along_y(server.CAMERAS['up_top'])
        gen = server._generated_cameras(Room('Shirogane', 'Medium'))
        self.assert_tilt_along_y(dict(position=gen['top']['position'], target=gen['top']['target']))
        fake = SimpleNamespace(cat=SimpleNamespace(scope='exterior'), room=SimpleNamespace(floor=box(-10, -10, 10, 10)))
        with patch.object(server, '_sess', fake):
            ext = server._cameras()['top']
        self.assert_tilt_along_y(ext)
        f = np.array(ext['target'], float) - np.array(ext['position'], float)
        right = np.cross(f, [0, 0, 1])
        self.assertGreater(right[0] / np.linalg.norm(right), 0.99)

class RendererVersionTests(unittest.TestCase):

    def test_renderer_fingerprint_covers_helpers_and_tolerates_missing_maps(self):
        version = server._renderer_version()
        self.assertIn('common.py:', version)
        self.assertIn('lighting.py:', version)
        with patch.object(server, 'source_path', lambda *a, **k: Path('C:/zz-nonexistent-houses')):
            self.assertIn('XIVSmallExterior.umap:0', server._renderer_version())

class SharedLevelRuleTests(unittest.TestCase):

    def test_render_context_follows_the_shared_floor_rule(self):
        from ffxiv_furniture.deco import server
        span = lambda zb, zt: server._levels_of_spans([(zb, zt)])
        self.assertEqual(span(-1.1, -0.9), {'basement'})
        self.assertEqual(span(-4.4, -2.69), {'basement'})
        self.assertEqual(span(7.0, 8.0), {'upper'})
        self.assertEqual(span(0.0, 0.02), {'ground'})

@needs_meshes
class ServerSizeTests(unittest.TestCase):

    def test_cameras_cover_every_level_and_listing_reports_real_levels(self):
        from unittest.mock import patch
        from ffxiv_furniture.deco import server
        for size in ('Medium', 'Large'):
            s = session(size)
            with patch.object(server, '_boot', return_value=s), patch.object(server, '_sess', s):
                cams = server._cameras()
                for need in ('overview', 'top', 'entry', 'up_overview', 'up_top', 'bs_overview', 'bs_top', 'bs_stair'):
                    self.assertIn(need, cams, (size, need))
                self.assertTrue(cams['bs_top']['basement'])
                self.assertTrue(cams['up_top']['upper'])
                listing = server.list_interiors()['interiors']
                self.assertTrue(all((x['house_size'] == size and x['levels'] == ['ground', 'upper', 'basement'] for x in listing)), listing[:1])
        s = session('Small')
        with patch.object(server, '_boot', return_value=s), patch.object(server, '_sess', s):
            self.assertEqual(server.list_interiors()['interiors'][0]['levels'], ['ground', 'basement'])

    def test_large_basement_furniture_renders_and_validates(self):
        import json
        from unittest.mock import patch
        from ffxiv_furniture.deco import server
        s = session('Large')
        r = s.apply([dict(op='place', instance_id='bench', name='Hingan Bench', position=[0, 0, -7.0], yaw_deg=0)])
        self.assertNotIn('OUTSIDE_FLOOR', [w['code'] for w in r.get('warnings', [])])
        self.assertEqual(s.inspect(level='basement')['level'], 'basement')
        with patch.object(server, '_boot', return_value=s), patch.object(server, '_sess', s):
            meta = json.loads(server.render(view='bs_top', width=160, height=120, lighting='off')[-1])
            self.assertIn('bench', [v['instance_id'] for v in meta['visible']])

class NativeInteriorRenderTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cat = catalog()

    def session(self):
        return Session('test', self.cat, room(), self.tmp.name, seed_layout=seed('Medium') if has_seed('Medium') else None)

    @needs_seed('Medium')
    def test_render_native_mesh_sources_transforms_and_empty_house_all_styles(self):
        for style in STYLES:
            with self.subTest(style=style):
                s = self.session()
                s.apply([dict(op='interior', style=style)])
                lp = Path(self.tmp.name) / (style + '.json')
                s.write_layout(lp)
                m = run_pipeline(lp, Path(self.tmp.name) / ('render-' + style), room_context=True, upper_context=True, size=(96, 96), mirror_view=False, cameras=[dict(name='top', position=[0, 0, 50], target=[0, 0, 0], fov=40, cutaway=True)])
                objects = {v['instance_id']: v for v in m['objects'].values()}
                p = s.room.profile
                self.assertEqual(Path(objects['up-floor']['source']), p.paths['upper']['floor'])
                self.assertEqual(Path(objects['floor']['source']), p.paths['ground']['floor'])
                for actor, label in [('Stairs', 'stair-up'), ('Stairs2_9', 'stair-down'), ('Railing', 'railing-upper')]:
                    self.assertEqual(objects[label]['decoded_actor_transform'], p.actors[actor])
                self.assertEqual(m['interior_profile']['style'], style)
                self.assertFalse(m['app_equivalence_verified'])
                self.assertTrue(Path(m['views'][0]['image']).is_file())

class MCPFlatOutputTests(unittest.TestCase):

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        lay = read_layout(ROOT / 'data/seeds/apartment-seed.json')
        lay.update(houseSize='Small', interiorFurniture=[])

        def write_layout(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(lay), encoding='utf-8')
        self.lay = lay
        self.session = SimpleNamespace(dir=self.root, revision=0, room=SimpleNamespace(house_size='Small', style='Shirogane'), instances={}, layout_dict=lambda: deepcopy(lay), write_layout=write_layout)
        self.boot = patch.object(server, '_boot', return_value=self.session)
        self.boot.start()
        self.addCleanup(self.boot.stop)
        self.sess = patch.object(server, '_sess', self.session)
        self.sess.start()
        self.addCleanup(self.sess.stop)

    def render(self, view='entry', **kwargs):
        result = server.render(view=view, width=96, height=64, lighting='off', mirror=False, **kwargs)
        return json.loads(result[-1])

    def sheet(self, views, **kwargs):
        result = server.render_sheet(views=views, width=96, height=64, lighting='off', mirror=False, **kwargs)
        return result[-1] if isinstance(result[-1], dict) else json.loads(result[-1])

    def bump(self):
        self.session.revision += 1
        self.lay['revision_marker'] = self.session.revision

    @needs_seed('Apartment')
    def test_views_share_jpeg_only_directory_and_repeat_hits_cache(self):
        a = self.render()
        b = self.render('north')
        again = self.render()
        out = self.root / 'renders'
        self.assertEqual(Path(a['image']).parent.resolve(), out.resolve())
        self.assertEqual(Path(b['image']).parent.resolve(), out.resolve())
        self.assertNotEqual(a['image'], b['image'])
        self.assertTrue(again['cache_hit'])
        self.assertEqual(a['image'], again['image'])
        self.assertEqual(len(list(out.iterdir())), 2)
        self.assertTrue(all((p.is_file() and p.suffix == '.jpg' for p in out.iterdir())))
        self.assertFalse(list(out.rglob('*.json')))

    @needs_seed('Apartment')
    def test_render_sheet_returns_one_jpeg_with_every_panel(self):
        from PIL import Image
        views = [{'label': 'A entry', 'view': 'entry'}, {'label': 'B north', 'view': 'north'}, {'label': 'C custom', 'view': {'position': [0, 0, 2], 'target': [0, -3, 1], 'fov': 70}}]
        m = self.sheet(views, cols=2)
        self.assertEqual(Path(m['image']).suffix, '.jpg')
        with Image.open(m['image']) as im:
            self.assertEqual(im.format, 'JPEG')
            self.assertEqual(im.size, (2 * 96, 2 * (64 + server.SHEET_TITLE_PX)))
        self.assertEqual([p['label'] for p in m['panels']], ['A entry', 'B north', 'C custom'])
        out = self.root / 'renders'
        self.assertEqual([p.name for p in out.iterdir()], [Path(m['image']).name])
        again = self.sheet(views, cols=2)
        self.assertEqual(again['image'], m['image'])
        self.assertTrue(all((p['cache_hit'] for p in again['panels'])))
        self.assertEqual(len(list(out.iterdir())), 1)

    @needs_seed('Apartment')
    def test_old_revisions_are_pruned_but_kept_files_survive(self):
        out = self.root / 'renders'
        kept = self.render(keep=True)['image']
        self.assertIn('-keep', Path(kept).name)
        self.render()
        self.bump()
        self.render('north')
        self.bump()
        self.render()
        self.bump()
        self.render()
        revs = sorted({int(p.name.split('-')[0][1:]) for p in out.iterdir() if '-keep' not in p.name})
        self.assertEqual(revs, [2, 3])
        self.assertTrue(Path(kept).is_file())
        s = self.sheet([{'label': 'A', 'view': 'entry'}], keep=True)
        self.assertIn('-keep', Path(s['image']).name)
        self.bump()
        self.render()
        self.bump()
        self.render()
        self.assertTrue(Path(s['image']).is_file())
        self.assertTrue(Path(kept).is_file())

    @needs_seed('Apartment')
    def test_render_sheet_rejects_bad_input(self):
        from mcp.server.fastmcp.exceptions import ToolError
        for views, cols in (([], 2), ([{'label': 'x', 'view': 'entry'}] * 13, 2), ([{'label': 'x', 'view': 'entry'}], 0), ([{'view': 'entry'}], 2)):
            with self.subTest(n=len(views), cols=cols), self.assertRaises(ToolError):
                server.render_sheet(views=views, cols=cols, width=96, height=64, lighting='off')

    @needs_seed('Apartment')
    def test_crop_is_jpeg(self):
        a = self.render(crop=[0, 0, 48, 32])
        self.assertEqual(Path(a['image']).suffix, '.jpg')
        from PIL import Image
        with Image.open(a['image']) as im:
            self.assertEqual((im.format, im.size), ('JPEG', (48, 32)))

    @needs_seed('Apartment')
    def test_diagnostics_are_explicit_flat_and_named(self):
        a = self.render()
        b = self.render(diagnostics=True)
        self.assertTrue(b['artifacts'])
        for filename in b['artifacts'].values():
            self.assertEqual(Path(filename).parent.resolve(), (self.root / 'renders').resolve())
            self.assertTrue(Path(filename).is_file())
        self.assertTrue(Path(a['image']).is_file())
        self.assertFalse(any((p.is_dir() for p in (self.root / 'renders').iterdir())))

    @needs_seed('Apartment')
    def test_cache_missing_image_is_regenerated_and_labels_crop_work(self):
        a = self.render()
        Path(a['image']).unlink()
        b = self.render()
        self.assertFalse(b['cache_hit'])
        self.assertTrue(Path(b['image']).is_file())
        labeled = self.render(labels=True, crop=[0, 0, 64, 48])
        from PIL import Image
        with Image.open(labeled['image']) as image:
            self.assertEqual(image.size, (64, 48))
        self.assertIn('labeled', Path(labeled['image']).name)
        self.assertEqual(Path(labeled['image']).parent, self.root / 'renders')
        self.assertFalse(list((self.root / 'renders').rglob('*.json')))

    @needs_seed('Apartment')
    def test_bounded_cache_eviction_regenerates_without_new_folders(self):
        with patch.object(server, '_RENDER_CACHE_LIMIT', 1):
            a = self.render()
            self.render('north')
            again = self.render()
            self.assertLessEqual(len(server._render_cache), 1)
        self.assertFalse(again['cache_hit'])
        self.assertEqual(a['image'], again['image'])
        self.assertEqual(len(list((self.root / 'renders').iterdir())), 2)

class SmallPlanCameraTests(unittest.TestCase):

    def test_ground_cutaways_keep_furniture_between_basement_and_ceiling(self):
        for name in ('top', 'overview', 'overview_nw'):
            cam = SMALL_CAMERAS[name]
            self.assertTrue(cam.get('cutaway'), name)
            self.assertLess(cam.get('hide_below_z', -99), 0, name)
            self.assertGreater(cam['hide_below_z'], -7 + 4.5, f'{name}: basement furniture tops (~z -3) must be hidden')
            self.assertLess(SMALL_CAMERAS[name]['hide_above_z'], 5.0, name)
            self.assertGreater(SMALL_CAMERAS[name]['hide_above_z'], 4.1, f'{name}: 4 m bookcases must stay visible')

    def test_basement_cameras_untouched(self):
        for name, cam in SMALL_CAMERAS.items():
            if cam.get('basement'):
                self.assertNotIn('hide_below_z', cam, name)
