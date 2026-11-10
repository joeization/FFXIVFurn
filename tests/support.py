"""Shared test helpers. Import as `from tests.support import ...` (run from the repo root:
`python -m unittest discover -s tests -q` or `python -m unittest tests.test_x`)."""
import json
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / 'data/seeds'
SIZES = ('Small', 'Medium', 'Large', 'Apartment')


def read_layout(path):
    """Layout JSON from disk; app/MCP exports are UTF-16 with BOM, seeds are UTF-8."""
    raw = Path(path).read_bytes()
    return json.loads(raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8-sig'))


def has_seed(size):
    return (SEEDS / f'{size.lower()}-seed.json').exists()


def seed(size='Medium', furniture=False):
    """Fresh copy of a local seed layout; interiorFurniture emptied unless furniture=True."""
    lay = read_layout(SEEDS / f'{size.lower()}-seed.json')
    if not furniture:
        lay['interiorFurniture'] = []
    return lay


def have_interior_meshes():
    from ffxiv_furniture.interiors import BASE
    return (BASE / 'Shirogane/Large/GroundFloor/GroundFloorFrame.uexp').exists()


needs_meshes = unittest.skipUnless(have_interior_meshes(), 'extracted interior meshes absent')


def needs_seed(*sizes):
    missing = [s for s in sizes if not has_seed(s)]
    return unittest.skipUnless(not missing, f'local seeds absent: {missing}')


def P(name, pos, yaw=0, **kw):
    """Batch `place` op by catalog name."""
    return dict(op='place', name=name, position=list(pos), yaw_deg=yaw, **kw)


@lru_cache(maxsize=1)
def catalog():
    from ffxiv_furniture.deco.core import Catalog
    return Catalog()


@lru_cache(maxsize=16)
def room(style='Shirogane', size='Medium'):
    from ffxiv_furniture.deco.core import Room
    return Room(style, size)


def session(size='Medium', style='Shirogane', seed_layout=None, **kw):
    """Throwaway deco Session in a temp dir (catalog and room are shared, read-only).
    Uses the local seed when present; without one the session still places/inspects/analyzes/renders,
    so only export/fixture tests need @needs_seed."""
    from ffxiv_furniture.deco.core import Session
    lay = seed_layout if seed_layout is not None else (seed(size) if has_seed(size) else None)
    return Session('t', catalog(), room(style, size), tempfile.mkdtemp(), seed_layout=lay, **kw)
