"""Contract tests use synthetic source files and explicitly injected measurements."""

from contextlib import closing
from pathlib import Path
import csv
import hashlib
import json
import sqlite3
import tempfile
import unittest
from typing import Any

from ffxiv_furniture.bootstrap import build_catalog
from ffxiv_furniture.config import load_sources


def synthetic_measure(job) -> dict[str, Any]:
    asset, item = job
    return dict(
        asset_key=asset["asset_key"],
        issues=[],
        placement=(item["item_id"], "floor", 0, 90, "prior +Y", 0, 1, 1, 1, None),
        surfaces=[
            dict(
                z_local=1,
                min_x=-0.5,
                min_y=-0.5,
                max_x=0.5,
                max_y=0.5,
                area_m2=1,
                clearance_above_m=9.9,
                is_top=1,
            )
        ],
        geometry=dict(
            source=asset["mesh"],
            source_sha256=hashlib.sha256(Path(asset["mesh"]).read_bytes()).hexdigest(),
            method="synthetic contract fixture",
            local_min_m=[-0.5, -0.5, 0],
            local_max_m=[0.5, 0.5, 1],
            origin_cm=[0, 0, 50],
            length_m=1,
            width_m=1,
            height_m=1,
        ),
    )


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sources = {}
        for key in ("interiors", "houses", "materials"):
            path = self.root / key
            path.mkdir()
            self.sources[key] = str(path)
        furniture = self.root / "furniture"
        self.sources["furniture_roots"] = [str(furniture)]
        for scope, name in [
            ("GameAssets", "TestChair"),
            ("YardAssets", "TestBench"),
            ("GameAssets", "Missing"),
            ("GameAssets", "Ambiguous"),
        ]:
            folder = furniture / scope / "Furniture/Chair" / name
            folder.mkdir(parents=True)
            (folder / (name + ".uasset")).write_bytes(b"synthetic source")
            (folder / (name + ".uexp")).write_bytes(b"synthetic source")
        folder = self.root / "materials/HouseAssets/Flooring/TestFloor"
        folder.mkdir(parents=True)
        (folder / "TestFloor.uasset").write_bytes(b"synthetic source")
        self.csv(
            "items_csv",
            [
                "#",
                "Name",
                "Description",
                "ItemUICategory",
                "DyeCount",
                "IsUntradable",
                "ItemSearchCategory",
            ],
            [
                ["1", "Test Chair", "Original chair text", "1", "1", "False", "2"],
                ["2", "Test Bench", "", "2", "0", "True", "0"],
                ["3", "Test Floor", "", "3", "0", "False", "2"],
                ["9", "Ambiguous", "", "1", "0", "True", "0"],
                ["10", "Ambiguous", "", "1", "0", "True", "0"],
            ],
        )
        self.csv(
            "ui_categories_csv",
            ["#", "Name"],
            [["1", "Furnishing"], ["2", "Outdoor Furnishing"], ["3", "Flooring"]],
        )
        self.csv(
            "stains_csv",
            ["Name", "Color", "Shade", "IsHousingApplicable", "IsMetallic"],
            [["Black", "1", "1", "True", "False"]],
        )
        (self.root / "interiors/HouseAssets/InteriorStyles").mkdir(parents=True)
        (self.root / "houses/Maps").mkdir(parents=True)
        self.output = self.root / "new.sqlite3"

    def csv(self, key, header, rows):
        path = self.root / (key + ".csv")
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        self.sources[key] = str(path)

    def test_runtime_schema_identity_provenance_and_unknowns(self):
        report = build_catalog(self.sources, self.output, measure=synthetic_measure)
        self.assertEqual(report["identified_items"], 2)
        self.assertEqual(report["issues"]["identity"], 2)
        with closing(sqlite3.connect(self.output)) as c:
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertFalse(c.execute("PRAGMA foreign_key_check").fetchall())
            self.assertEqual(
                c.execute("SELECT id,name,description FROM furniture ORDER BY id").fetchall(),
                [(1, "Test Chair", "Original chair text"), (2, "Test Bench", "")],
            )
            self.assertEqual(c.execute("SELECT COUNT(*) FROM furniture_bounds").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM support_surfaces").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM item_colors").fetchone()[0], 0)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM candidate_assets WHERE item_id IS NULL").fetchone()[
                    0
                ],
                2,
            )
            self.assertEqual(
                c.execute("SELECT DISTINCT source FROM furniture_tags").fetchall(),
                [("native-asset-path",)],
            )
            self.assertEqual(
                c.execute("SELECT patch,cash_shop FROM furniture WHERE id=1").fetchone(),
                (None, None),
            )
            self.assertEqual(
                json.loads(
                    c.execute(
                        "SELECT value FROM build_metadata WHERE key='bootstrap_sources'"
                    ).fetchone()[0]
                ),
                self.sources,
            )
        before = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            build_catalog(self.sources, self.output, measure=synthetic_measure)
        self.assertEqual(self.output.read_bytes(), before)

    def test_atomic_failure_leaves_no_target_or_stage(self):
        def fail(job):
            raise RuntimeError("intentional injected measurement failure")

        with self.assertRaisesRegex(RuntimeError, "intentional"):
            build_catalog(self.sources, self.output, measure=fail)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".new-*.sqlite3")))

    def test_bad_sources_and_literal_patch_fail_without_publishing(self):
        self.csv("patches_csv", ["item_id", "patch"], [["1", "7.2bad"]])
        with self.assertRaisesRegex(ValueError, "literal"):
            build_catalog(self.sources, self.output, measure=synthetic_measure)
        self.assertFalse(self.output.exists())
        self.csv("patches_csv", ["item_id", "patch"], [["1", "7.21"]])
        build_catalog(self.sources, self.output, measure=synthetic_measure)
        with closing(sqlite3.connect(self.output)) as c:
            self.assertEqual(
                c.execute("SELECT patch FROM furniture WHERE id=1").fetchone()[0], "7.21"
            )

    def test_changed_inputs_abort_publication(self):
        def mutate(job):
            value = synthetic_measure(job)
            with Path(self.sources["items_csv"]).open("a", encoding="utf-8") as f:
                f.write("\n")
            return value

        with self.assertRaisesRegex(ValueError, "Source CSV changed"):
            build_catalog(self.sources, self.output, measure=mutate)
        self.assertFalse(self.output.exists())

    def test_strict_geometry_rejects_partial_catalog(self):
        def partial(job):
            value = synthetic_measure(job)
            if job[1]["item_id"] == 1:
                value.update(
                    geometry=None,
                    issues=[("geometry_or_placement", "intentional unsupported fixture")],
                )
            return value

        with self.assertRaisesRegex(ValueError, "strict-geometry"):
            build_catalog(self.sources, self.output, strict_geometry=True, measure=partial)
        self.assertFalse(self.output.exists())

    def test_source_paths_are_relative_to_config_not_cwd(self):
        config = self.root / "sources.json"
        relative = {
            k: (
                [str(Path(v[0]).relative_to(self.root))]
                if isinstance(v, list)
                else str(Path(v).relative_to(self.root))
            )
            for k, v in self.sources.items()
        }
        config.write_text(json.dumps(relative), encoding="utf-8")
        self.assertEqual(load_sources(config), self.sources)

    def test_duplicate_asset_identity_does_not_pick_arbitrary_mesh(self):
        folder = Path(self.sources["furniture_roots"][0]) / "GameAssets/Other/TestChair"
        folder.mkdir(parents=True)
        for ext in (".uasset", ".uexp"):
            (folder / ("TestChair" + ext)).write_bytes(b"synthetic alternative")
        build_catalog(self.sources, self.output, measure=synthetic_measure)
        with closing(sqlite3.connect(self.output)) as c:
            self.assertEqual(c.execute("SELECT id FROM furniture").fetchall(), [(2,)])


if __name__ == "__main__":
    unittest.main()
