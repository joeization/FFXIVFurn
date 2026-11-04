"""Basement plan cutaways must show where the style's walls close off the floor (user-reported: Mist walls off the stair underside and the area
under the ground landing; with walls removed in cutaway plans that void looked like usable floor)."""
import json, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from ffxiv_furniture.interiors import BASE


def _seed():
    b = (ROOT / 'data/seeds/small-seed.json').read_bytes()
    lay = json.loads(b.decode('utf-16') if b[:2] == b'\xff\xfe' else b.decode('utf-8-sig'))
    lay['interiorFurniture'] = []; return lay


@unittest.skipUnless((BASE / 'Mist/Small/BasementFrame.uexp').exists(), 'native Small interiors not extracted')
class BasementVoidOverlayTests(unittest.TestCase):
    def _run(self, style, cutaway):
        from ffxiv_furniture.rendering.pipeline import run_pipeline
        lay = _seed()
        for fx in lay['interiorFixture']:
            if fx['type'] == 'District': fx['name'] = style
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'l.json'; src.write_text(json.dumps(lay), encoding='utf-8')
            cam = dict(name='bs_top', position=[2.5, 4, 30], target=[2, 4, -7], fov=40, basement=True, hide_above_z=-0.6, cutaway=cutaway)
            return run_pipeline(src, Path(tmp) / 'r', db_path=ROOT / 'data/furniture-test.sqlite3', room_context=True, basement_context=True,
                                size=(160, 160), mirror_view=False, cameras=[cam])

    def test_mist_plan_marks_walled_off_floor(self):
        m = self._run('Mist', True)
        void = [k for k, v in m['objects'].items() if k.isdigit() and v.get('instance_id') == 'basement-walled-off']
        self.assertEqual(len(void), 1)
        self.assertGreater(m['objects'][void[0]]['area_m2'], 40)
        self.assertGreater(m['views'][0]['visible_object_pixels'].get(void[0], 0), 0)

    def test_open_style_and_eye_views_unchanged(self):
        m = self._run('Minimalist', True)
        void = [k for k, v in m['objects'].items() if k.isdigit() and v.get('instance_id') == 'basement-walled-off']
        self.assertTrue(not void or m['objects'][void[0]]['area_m2'] < 5)
        m = self._run('Mist', False)
        void = [k for k, v in m['objects'].items() if k.isdigit() and v.get('instance_id') == 'basement-walled-off']
        self.assertTrue(not void or m['views'][0]['visible_object_pixels'].get(void[0], 0) == 0, 'overlay is for cutaway plans only')


if __name__ == '__main__':
    unittest.main()
