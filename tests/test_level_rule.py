"""Shared floor-assignment rule for items (validation, analyze, render, plans)."""
import unittest
from ffxiv_furniture.interiors import level_for_span


class LevelForSpanTests(unittest.TestCase):
    def test_rule(self):
        cases = {(0.0, 0.02): 'ground', (-0.4, 1.0): 'ground', (6.2, 6.5): 'ground', (7.0, 8.0): 'upper', (6.4, 9.0): 'upper',
                 (-7.0, -6.0): 'basement', (-3.38, -2.66): 'basement', (-4.4, -2.69): 'basement', (-1.1, -0.9): 'basement',
                 (-2.4, 3.6): 'ground'}
        for (zb, zt), want in cases.items():
            with self.subTest(zb=zb, zt=zt):
                self.assertEqual(level_for_span(zb, zt), want)


if __name__ == '__main__':
    unittest.main()
