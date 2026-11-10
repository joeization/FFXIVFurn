"""Lighting moods, real-emitter classification and bounded light selection."""

import unittest


class LightingModuleTests(unittest.TestCase):

    def test_emitters_are_real_lights_or_emissive_materials(self):
        from ffxiv_furniture.rendering.lighting import emitter_light

        for name in (
            "Flame Desk",
            "Flame Armoire",
            "Flame Trophy (Left)",
            "Loss, Fire, Faith Reproduction",
            "Moonfire Faire MMXIV Advertisement",
            "Immortal Flames Banner",
            "Trophy of Light",
            "Firewood",
            "Firebloom",
            "Flame Storage Bench",
            "Sultana and Flame General Portrait",
        ):
            self.assertIsNone(emitter_light(name), name)
        for name in (
            "Classic Table Lamp",
            "Alchemical Lantern",
            "Assorted Candles",
            "Far Eastern Brazier",
            "Campfire",
            "Manor Fireplace",
            "Iron Torch",
            "Crystal Chandelier",
            "Pendant Wall Light",
            "Cooking Stove",
            "Riviera Lamppost",
            "Cosmolamp",
            "Pumpkin Candlestand",
            "Candlelit Sundries",
            "Riviera Path Light",
            "Overhead Studio Light",
            "Illuminated Tree",
            "Cold Knight's Cookfire",
        ):
            self.assertIsNotNone(emitter_light(name), name)
        self.assertIsNotNone(
            emitter_light("Flame Desk", has_emissive_material=True)
        )  # decoded emissive material wins over the name

    def test_resolve_mood_accepts_every_form(self):
        from ffxiv_furniture.rendering.lighting import resolve_mood

        dusk = resolve_mood("dusk")
        self.assertEqual(resolve_mood(True), dusk)
        self.assertEqual(resolve_mood("warm"), dusk)
        custom = dict(lo=(0.1, 0.1, 0.1), hi=(0.2, 0.2, 0.2), exposure=1.0, scale=1.0)
        self.assertEqual(resolve_mood(custom)["exposure"], 1.0)
        with self.assertRaises(ValueError):
            resolve_mood("nope")

    def test_light_budget_reports_and_strips_dropped_glow(self):
        from ffxiv_furniture.rendering.lighting import apply_light_budget

        lights = [
            dict(id=i, pos=[0, 0, 0], color=[1, 1, 1], intensity=float(i), radius=1.0)
            for i in range(1, 71)
        ]
        meshes = [dict(id=i, emissive=(1, 1, 1)) for i in range(1, 71)]
        kept, dropped, message = apply_light_budget(lights, meshes, cap=64)
        self.assertEqual((len(kept), len(dropped)), (64, 6))
        self.assertIn("kept 64", message)
        self.assertIn("dropped 6", message)
        self.assertEqual(
            {m["id"] for m in meshes if not m.get("emissive")}, {1, 2, 3, 4, 5, 6}
        )
        self.assertEqual(apply_light_budget(lights[:3], meshes, cap=64)[2], None)
