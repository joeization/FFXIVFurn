"""Shared camera validation and honest fallback diagnostics."""
import sqlite3
from .raster import camera_basis


def validate_cameras(cameras):
    if not isinstance(cameras, list) or not 1 <= len(cameras) <= 8 or not all(isinstance(c, dict) for c in cameras):
        raise ValueError('Need 1..8 camera dictionaries')
    for camera in cameras:
        try:
            camera_basis(camera)
            if not 1 < camera.get('fov', 70) < 175:
                raise ValueError('Invalid camera projection')
        except (KeyError, TypeError, IndexError) as error:
            raise ValueError('Invalid camera position/target/projection') from error


def load_fallback_colours(db, warnings):
    try:
        return dict(db.execute('SELECT item_id,c1_hex FROM item_colors WHERE c1_hex IS NOT NULL'))
    except sqlite3.OperationalError as error:
        warnings.append(f'item_colors unavailable ({error}); untextured meshes may use neutral grey.')
        return {}


def coverage_warnings(coverage):
    slots = sum(row['material_slots'] for row in coverage)
    untextured = sum(row['material_slots'] - row['textured_slots'] for row in coverage)
    reasons = sorted({str(message) for row in coverage for message in [*row.get('notes', []), *(m.get('warning') for m in row.get('materials', []))] if message})
    if not reasons and not untextured:
        return []
    return [f'Native decode: {untextured} of {slots} material slots untextured; ' + '; '.join(reasons)]
