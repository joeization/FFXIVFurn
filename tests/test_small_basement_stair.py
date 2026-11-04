"""Small basement stair handling per interior style (user-reported from app screenshots: Mist boxes the stair underside so there is no space
under it, Minimalist's open flight leaves room). Geometry facts must follow the chosen style, not one shared box."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from ffxiv_furniture.interiors import BASE

HAVE = (BASE / 'Mist/Small/BasementFrame.uexp').exists() and (BASE / 'Minimalist/Small/BasementFrame.uexp').exists()


@unittest.skipUnless(HAVE, 'native Small interiors not extracted')
class SmallBasementStairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ffxiv_furniture.deco.core import Room
        cls.mist = Room('Mist', 'Small'); cls.mini = Room('Minimalist', 'Small')

    def test_basement_outline_follows_style_walls(self):
        from shapely.geometry import Point
        mb, nb = self.mist.basement, self.mini.basement
        for xy in ((8.0, -3.0), (8.0, 2.0)):          # under the ground landing / under the flight
            self.assertFalse(mb.contains(Point(*xy)), f'Mist walls off {xy}')
            self.assertTrue(nb.contains(Point(*xy)), f'Minimalist leaves {xy} open')
        for room in (self.mist, self.mini):
            self.assertTrue(room.basement.contains(Point(0.0, 4.0)))
            self.assertTrue(room.basement.contains(Point(8.0, 11.5)))   # stair foot area stays reachable
            self.assertGreater(room.basement.area, 240)

    def test_under_stair_space_per_style(self):
        m = self.mist.stair_summary()['basement']['under_stair']; n = self.mini.stair_summary()['basement']['under_stair']
        self.assertGreater(m['enclosed_m2'], 25); self.assertLess(m['usable_ge_1p9m_m2'], 2)
        self.assertGreater(n['usable_ge_1p9m_m2'], 12); self.assertLess(n['enclosed_m2'], 3)
        cells = self.mini.stair_clearance()['basement']['cells']
        self.assertTrue(any(c[2] >= 2.5 and not c[3] for c in cells))
        self.assertTrue(all(c[2] == 0 for c in self.mist.stair_clearance()['basement']['cells'] if c[3]))

    def test_validation_flags_boxed_underside_only(self):
        from ffxiv_furniture.deco.core import Catalog, Session
        import json, tempfile
        seed = json.loads((ROOT / 'data/seeds/small-seed.json').read_bytes().decode('utf-16') if (ROOT / 'data/seeds/small-seed.json').read_bytes()[:2] == b'\xff\xfe' else (ROOT / 'data/seeds/small-seed.json').read_text(encoding='utf-8'))
        seed = {k: v for k, v in seed.items() if k != 'interiorFurniture'}
        for room, expect in ((self.mist, True), (self.mini, False)):
            with tempfile.TemporaryDirectory() as tmp:
                s = Session('t', Catalog(), room, tmp, seed_layout=seed)
                r = s.apply([dict(op='place', instance_id='barrel', name='Wine Barrel', position=[8.0, 1.0, -7.0])])
                codes = {w['code'] for w in r['warnings'] if w.get('instance_id') == 'barrel'}
                self.assertEqual(bool(codes & {'STAIR_INTERSECTION', 'OUTSIDE_FLOOR'}), expect, (room.style, codes))


if __name__ == '__main__':
    unittest.main()
