"""Rough room-finish colour from native wallpaper/flooring albedo textures.

Deliberately approximate: the average of the first `_d` texture's mip0, applied as a flat colour to
room meshes (which have no verified UVs/transforms). Not a shader/tint/dye reconstruction.
"""
from pathlib import Path
import numpy as np
from .native import decode_texture
from ..config import source_path

LEGACY = source_path('materials') / 'HouseAssets'
KIND = {'Floor': 'Flooring', 'Wall': 'Wallpaper'}


def fixture_folder(db, category, fixture):
    """Resolve catalog-native folder spelling; only use the encoded name as fallback."""
    if db is not None:
        row = db.execute('SELECT asset_key FROM house_materials WHERE category=? AND name=?',
                         (category, fixture['name'])).fetchone()
        if row:
            return row[0].rsplit('/', 1)[-1]
    import re
    encoded = fixture['name'].replace('&', '0x26').replace('(', '0x28').replace(')', '0x29').replace("'", '_')
    compact = ''.join(encoded.split())
    root = LEGACY / category
    if root.is_dir():
        matches = [p.name for p in root.iterdir() if p.is_dir() and p.name.casefold() == compact.casefold()]
        if len(matches) == 1:
            return matches[0]
    return compact


def folder_name(display):
    return fixture_folder(None, '', {'name': display})


def average_color(kind, fixtures=(), level='Ground Floor'):
    """Return (linear-ish sRGB 0..1 array, provenance) for the fixture chosen on `level`, or raise."""
    chosen = next((f for f in fixtures if f.get('type') == kind and f.get('level') == level), None)
    if chosen is None:
        raise ValueError(f'No {kind} fixture on {level}')
    folder = LEGACY / KIND[kind] / fixture_folder(None, KIND[kind], chosen)
    textures = sorted(folder.glob('*_d.uasset'))
    if not textures:
        raise FileNotFoundError(f'Extract {folder} first (retoc to-legacy --filter {folder.name}); not guessing a colour')
    image, meta = decode_texture(textures[0])
    arr = np.asarray(image.convert('RGB'), float) / 255
    return arr.mean(axis=(0, 1)), {'fixture': chosen['name'], 'item_id': chosen['itemId'], 'texture': textures[0].name,
                                   'source_sha256': meta['source_sha256'], 'method': 'flat average of mip0 albedo (rough)'}


def fixture_texture(kind, fixtures=(), level='Ground Floor'):
    """Albedo (`_d`) texture of the wallpaper/floor chosen on `level` as RGBA uint8, tiled by the room mesh UVs. Rough: no normal/specular/tint."""
    chosen = next((f for f in fixtures if f.get('type') == kind and f.get('level') == level), None)
    if chosen is None: raise ValueError(f'No {kind} fixture on {level}')
    folder = LEGACY / KIND[kind] / fixture_folder(None, KIND[kind], chosen)
    textures = sorted(folder.glob('*_d.uasset'))
    if not textures: raise FileNotFoundError(f'Extract {folder} first; not guessing a texture')
    image, meta = decode_texture(textures[0])
    return {'texture': np.asarray(image.convert('RGBA')), 'provenance': {'fixture': chosen['name'], 'item_id': chosen.get('itemId'), 'texture': textures[0].name, 'source_sha256': meta['source_sha256']}}
