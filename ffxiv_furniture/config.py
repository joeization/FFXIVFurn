"""Explicit model settings and shared seed validation; no private deployment defaults."""

import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit


def model_settings(endpoint=None, model=None):
    """Resolve CLI overrides before environment; never discovers/calls a model."""
    endpoint = endpoint if endpoint is not None else os.environ.get("VLM_URL")
    model = model if model is not None else os.environ.get("VLM_MODEL")
    if not endpoint or not model or not endpoint.strip() or not model.strip():
        raise ValueError(
            "Set VLM_URL and VLM_MODEL, or supply explicit --endpoint/--model. No model is called by default."
        )
    parts = urlsplit(endpoint)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "Model endpoint must be an HTTP(S) base URL without credentials, query or fragment."
        )
    return endpoint.rstrip("/"), model


def load_seed_layout(path):
    """Read a complete layout without altering scales, fields or unknown payloads."""
    layout = json.loads(Path(path).read_bytes())
    keys = {"houseSize", "interiorScale", "exteriorScale", "interiorFixture"}
    if not isinstance(layout, dict) or not keys <= layout.keys():
        raise ValueError(
            "Seed must be a complete layout object with houseSize, interiorScale, exteriorScale and interiorFixture."
        )
    if not isinstance(layout["houseSize"], str) or not isinstance(layout["interiorFixture"], list):
        raise ValueError("Seed houseSize must be a string and interiorFixture must be a list.")
    for key in ("interiorScale", "exteriorScale"):
        value = layout[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"Seed {key} must be finite and positive.")
    if any(
        not isinstance(f, dict) or not isinstance(f.get("type"), str)
        for f in layout["interiorFixture"]
    ):
        raise ValueError("Seed interiorFixture entries must be objects with a type string.")
    return layout


# A sources file contains paths only, never assets or credentials. Relative paths
# are relative to that JSON file, not to the caller's working directory.
_DEFAULT_SOURCES = {
    "furniture_roots": ["gameassets-legacy/MakePlace/Content"],
    "interiors": "house-interiors-legacy/MakePlace/Content",
    "houses": "house-legacy/MakePlace/Content",
    "materials": "house-materials-legacy/MakePlace/Content",
    "items_csv": "external/Item.csv",
    "ui_categories_csv": "external/ItemUICategory.csv",
    "stains_csv": "external/Stain.csv",
}


def load_sources(path=None, *, root=None):
    """Resolve operator-provided local source paths; never extracts/downloads."""
    root = Path(root or Path(__file__).resolve().parents[1])
    path = path or os.environ.get("FFXIVFURN_SOURCES")
    if path:
        path = Path(path).resolve()
        values = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(values, dict) or values.keys() - (
            _DEFAULT_SOURCES.keys() | {"patches_csv"}
        ):
            raise ValueError("Unknown source keys or non-object sources JSON")
        missing = _DEFAULT_SOURCES.keys() - values.keys()
        if missing:
            raise ValueError("Missing source keys: " + ", ".join(sorted(missing)))
        base = path.parent
    else:
        values = _DEFAULT_SOURCES
        base = root / "data"
    result = {}
    for key, value in values.items():
        sequence = value if key == "furniture_roots" else [value]
        if (
            not isinstance(sequence, list)
            or not sequence
            or any(not isinstance(v, str) or not v for v in sequence)
        ):
            raise ValueError("Invalid source path(s): " + key)
        resolved = [str((base / Path(v)).resolve()) for v in sequence]
        result[key] = resolved if key == "furniture_roots" else resolved[0]
    return result


def source_path(key, *, root=None):
    return Path(load_sources(root=root)[key])


def local_input(env, what):
    """Operator-provided local path from an environment variable. The repository ships no private path defaults:
    DECO_SEED (a complete layout/app save you may use), FFXIVFURN_LARGE_SEED, FFXIVFURN_INSPECTION_DIR (retoc inspection output)."""
    value = os.environ.get(env)
    if not value or not value.strip():
        raise SystemExit(f"Set {env} to {what}; no private default path is provided.")
    return Path(value)


def catalog_path():
    root = Path(__file__).resolve().parents[1]
    return Path(os.environ.get("FFXIVFURN_DB") or root / "data/furniture.sqlite3").resolve()
