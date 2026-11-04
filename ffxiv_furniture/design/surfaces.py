"""Measure horizontal support planes from model-local, z-up metre meshes.

Groups have a maximum height span of 3 cm (not a transitive chain).
Clearance is conservative across the actual union of the group's triangles,
not the empty corners of its stored bounding box. Edge-only contacts with
vertical walls do not block a shelf. Topmost geometry has 9.9 m clearance.
"""
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union


def measure_support_surfaces(vertices, faces, *, height_tolerance=0.03,
                             min_area=0.02, min_height=0.15,
                             min_clearance=0.12):
    """Return ordered dictionaries matching support_surfaces' value columns."""
    v = np.asarray(vertices, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    if not v.size or not f.size:
        return []
    if v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all():
        raise ValueError('Vertices must be finite xyz triples')
    if f.ndim != 2 or f.shape[1] != 3 or f.min() < 0 or f.max() >= len(v):
        raise ValueError('Faces must index three existing vertices')
    triangles = v[f]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    # Extracted Unreal index buffers commonly wind inward in the z-up
    # coordinate convention. Signed volume establishes outward orientation
    # before applying normal.z > .95; otherwise tabletops become undersides.
    signed_volume6 = float(np.einsum('ij,ij->i', triangles[:, 0], cross).sum())
    if signed_volume6 < -1e-9:
        cross = -cross
    lengths = np.linalg.norm(cross, axis=1)
    means = triangles[:, :, 2].mean(axis=1)
    upward = np.flatnonzero(cross[:, 2] > 0.95 * np.maximum(lengths, 1e-15))
    upward = upward[np.argsort(means[upward], kind='stable')]
    groups = []
    for idx in upward:
        if not groups or means[idx] - means[groups[-1][0]] > height_tolerance + 1e-9:
            groups.append([])
        groups[-1].append(int(idx))
    # Nonzero XY projections include undersides and sloping obstructions,
    # regardless of winding. Pure vertical faces have zero overlap area.
    projectable = np.flatnonzero(np.abs(cross[:, 2]) > 1e-12)
    projected = shapely.polygons(triangles[projectable, :, :2])
    bounds = shapely.bounds(projected)
    zmin = triangles[projectable, :, 2].min(axis=1)
    result = []
    bottom, top = float(v[:, 2].min()), float(v[:, 2].max())
    for group in groups:
        area_weights = lengths[group] / 2
        z = float(np.average(means[group], weights=area_weights))
        if z - bottom < min_height - 1e-9:
            continue
        footprint = unary_union([Polygon(triangles[i, :, :2]) for i in group])
        # Union area avoids double-counting duplicate/two-sided triangles.
        area = float(footprint.area)
        if area < min_area - 1e-9:
            continue
        x0, y0, x1, y1 = footprint.bounds
        upper = float(triangles[group, :, 2].max())
        # Geometry must be above the board, not a side panel or bevel
        # rising out of it; those contacts otherwise erase every shelf.
        candidates = ((zmin > upper + height_tolerance + 1e-9)
                      & (bounds[:, 0] < x1) & (bounds[:, 2] > x0)
                      & (bounds[:, 1] < y1) & (bounds[:, 3] > y0))
        selected = np.flatnonzero(candidates)
        clearance = 9.9 if top - upper <= height_tolerance + 1e-9 else top - z
        if len(selected):
            intersections = shapely.intersection(projected[selected], footprint)
            positive = shapely.area(intersections) > 1e-10
            selected = selected[positive]
            intersections = intersections[positive]
            if len(selected):
                xy, owners = shapely.get_coordinates(intersections, return_index=True)
                ids = projectable[selected[owners]]
                normals = cross[ids]
                origins = triangles[ids, 0]
                heights = (origins[:, 2] - (normals[:, 0] * (xy[:, 0] - origins[:, 0])
                           + normals[:, 1] * (xy[:, 1] - origins[:, 1])) / normals[:, 2])
                lows = np.full(len(selected), np.inf)
                highs = np.full(len(selected), -np.inf)
                np.minimum.at(lows, owners, heights)
                np.maximum.at(highs, owners, heights)
                overhead = highs > upper + height_tolerance + 1e-9
                if overhead.any():
                    distances = np.maximum(lows[overhead] - z, height_tolerance)
                    clearance = min(clearance, float(distances.min()))
        if clearance < min_clearance - 1e-9:
            continue
        result.append(dict(z_local=z, min_x=float(x0), min_y=float(y0),
                           max_x=float(x1), max_y=float(y1), area_m2=area,
                           clearance_above_m=float(clearance),
                           is_top=int(top - upper <= height_tolerance + 1e-9)))
    return result
