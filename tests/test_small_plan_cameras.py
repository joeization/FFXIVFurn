"""Small ground plan cameras must hide basement furniture (user-reported misleading plan views: basement bed showed beside the ground floor)."""
import unittest
from ffxiv_furniture.deco.server import SMALL_CAMERAS


class SmallPlanCameraTests(unittest.TestCase):
    def test_ground_cutaways_hide_basement(self):
        for name in ('top', 'overview', 'overview_nw'):
            cam = SMALL_CAMERAS[name]
            self.assertTrue(cam.get('cutaway'), name)
            self.assertLess(cam.get('hide_below_z', -99), 0, name)
            self.assertGreater(cam['hide_below_z'], -7 + 4.5, f'{name}: basement furniture tops (~z -3) must be hidden')

    def test_ground_cutaways_hide_ceiling_mounted_pieces(self):
        # skylights/coffers recessed at the 5.5 m ceiling covered whole zones in plan views
        for name in ('top', 'overview', 'overview_nw'):
            self.assertLess(SMALL_CAMERAS[name]['hide_above_z'], 5.0, name)
            self.assertGreater(SMALL_CAMERAS[name]['hide_above_z'], 4.1, f'{name}: 4 m bookcases must stay visible')

    def test_basement_cameras_untouched(self):
        for name, cam in SMALL_CAMERAS.items():
            if cam.get('basement'): self.assertNotIn('hide_below_z', cam, name)


if __name__ == '__main__':
    unittest.main()
