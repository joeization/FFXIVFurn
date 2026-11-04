"""Setup/configuration regressions. All inputs are local, never call a model."""

from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from ffxiv_furniture.config import model_settings
from ffxiv_furniture.doctor import diagnose
from ffxiv_furniture import FurnitureDB


class SetupTests(unittest.TestCase):
    def test_model_is_explicit_and_cli_overrides_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "VLM_URL"):
                model_settings()
        with patch.dict(os.environ, {"VLM_URL": "http://localhost:9000/v1", "VLM_MODEL": "local"}):
            self.assertEqual(model_settings(), ("http://localhost:9000/v1", "local"))
            self.assertEqual(
                model_settings("https://example.org/v1/", "override"),
                ("https://example.org/v1", "override"),
            )
        for endpoint in (
            "file:///tmp/model",
            "http://user:secret@example.org/v1",
            "http://example.org/v1?key=secret",
        ):
            with self.assertRaises(ValueError):
                model_settings(endpoint, "local")

    def test_shared_seed_loader_preserves_unknown_fields_and_rejects_bad_scale(self):
        from ffxiv_furniture.config import load_seed_layout

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed.json"
            layout = dict(
                houseSize="Small",
                interiorScale=100,
                exteriorScale=100,
                interiorFixture=[],
                unknown={"preserve": [1, 2, 3]},
            )
            path.write_bytes(b"\xff\xfe" + json.dumps(layout).encode("utf-16-le"))
            self.assertEqual(load_seed_layout(path), layout)
            for value in (0, -1, True, "100", float("inf")):
                path.write_text(json.dumps(dict(layout, exteriorScale=value)), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_seed_layout(path)

    def test_doctor_never_creates_missing_db_and_does_not_mistake_empty_crud_for_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "catalog.sqlite3"
            self.assertFalse(diagnose(db)["ok"])
            self.assertFalse(db.exists())
            with FurnitureDB(db):
                pass
            before = db.read_bytes()
            self.assertTrue(diagnose(db)["ok"])
            result = diagnose(db, render=True)
            self.assertFalse(result["ok"])
            self.assertTrue(any(c["name"] == "catalog" and not c["ok"] for c in result["checks"]))
            self.assertEqual(db.read_bytes(), before)

    def test_resume_rejects_wrong_house_size_without_rewriting_saved_state(self):
        from types import SimpleNamespace
        from ffxiv_furniture.deco.core import Session, DecoError
        from ffxiv_furniture.deco.exterior import ExteriorSession

        for cls, scope in ((Session, "interior"), (ExteriorSession, "exterior")):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as tmp:
                cat = SimpleNamespace(scope=scope, max_patch=None, sha=lambda: "test-catalog")
                small = SimpleNamespace(house_size="Small", style="Shirogane")
                cls("saved", cat, small, tmp, seed_layout={"houseSize": "Small"})
                state = Path(tmp) / "saved/state.json"
                before = state.read_bytes()
                medium = SimpleNamespace(house_size="Medium", style="Shirogane")
                with self.assertRaisesRegex(DecoError, "matching DECO_SEED"):
                    cls("saved", cat, medium, tmp, seed_layout={"houseSize": "Medium"})
                self.assertEqual(state.read_bytes(), before)

    def test_boot_requires_complete_seed_before_opening_catalog(self):
        from ffxiv_furniture.deco import server
        from ffxiv_furniture.deco.core import DecoError

        with patch.object(server, "_sess", None), patch.object(server, "Catalog") as catalog:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(DecoError, "DECO_SEED"):
                    server._boot()
            with tempfile.TemporaryDirectory() as tmp:
                seed = Path(tmp) / "seed.json"
                seed.write_text(json.dumps([]), encoding="utf-8")
                with patch.dict(os.environ, {"DECO_SEED": str(seed)}):
                    with self.assertRaisesRegex(DecoError, "complete layout"):
                        server._boot()
            catalog.assert_not_called()
