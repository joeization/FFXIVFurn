"""Synthetic palette matching and texture-summary regression cases."""
import colorsys
import unittest


def row(hex_color):
    rgb = tuple(int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    return dict(c1_hex=hex_color, c1_frac=1., mean_h=h, mean_s=s, mean_v=v)


def test_dark_brown_matches_better_than_red_or_cream():
    from ffxiv_furniture.design.palette import palette_names_to_hsv_ranges, color_distance
    targets = palette_names_to_hsv_ranges(['dark brown'])
    assert color_distance(row('#49301d'), targets) < color_distance(row('#dd2020'), targets)
    assert color_distance(row('#49301d'), targets) < color_distance(row('#fff5dc'), targets)


def test_cream_and_red_targets_and_circular_hue():
    from ffxiv_furniture.design.palette import palette_names_to_hsv_ranges, color_distance
    for name, good, bad in [('cream', '#fff5dc', '#49301d'), ('crimson', '#d02035', '#fff5dc')]:
        targets = palette_names_to_hsv_ranges(name)
        assert color_distance(row(good), targets) < color_distance(row(bad), targets)
    red = palette_names_to_hsv_ranges('red')
    assert color_distance(row('#ff0010'), red) < .05
    assert color_distance(row('#ff1000'), red) < .05
    for name in ('dark brown', 'cream', 'warm amber', 'jade green', 'crimson', 'ivory', 'charcoal'):
        assert palette_names_to_hsv_ranges(name)
    assert color_distance({}, red) == 1
    assert color_distance({}, []) == 0


def test_texture_summary_ignores_transparent_and_near_black():
    import numpy as np
    from scripts.fill_dominant_colors import summarize_textures
    pixels = np.array([[[255, 0, 0, 255]] * 6 + [[0, 255, 0, 255]] * 2 +
                       [[0, 0, 255, 0]] * 4 + [[1, 1, 1, 255]] * 4], dtype=np.uint8)
    summary = summarize_textures([pixels])
    assert summary['c1_hex'] == '#ff0000'
    assert summary['c1_frac'] == .75
    assert summary['c2_hex'] == '#00ff00'
    assert summary['c2_frac'] == .25
    assert summary['c3_hex'] is None
    assert summary['hue_name'] == 'red'
    assert summarize_textures([])['c1_hex'] is None


class PaletteTests(unittest.TestCase):
    def test_brown(self):
        test_dark_brown_matches_better_than_red_or_cream()

    def test_targets(self):
        test_cream_and_red_targets_and_circular_hue()

    def test_textures(self):
        test_texture_summary_ignores_transparent_and_near_black()


if __name__ == '__main__':
    unittest.main()
