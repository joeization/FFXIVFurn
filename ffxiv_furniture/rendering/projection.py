"""Exact XY triangle unions, reusable across cameras/translated instances.

Cache the rotated local geometry, not a world-space bbox or convex hull. Byte
keys bind the actual coordinates and triangle indices, including tilted meshes.
Shapely geometries are immutable; the bounded cache can safely share them.
"""
from functools import lru_cache
import numpy as np
import shapely
from shapely.geometry import GeometryCollection


def projected_footprint(vertices, triangles):
    xy=np.ascontiguousarray(np.asarray(vertices,dtype='<f8')[:,:2])
    tri=np.ascontiguousarray(np.asarray(triangles,dtype='<i8').reshape(-1,3))
    return _projected(xy.tobytes(),tri.tobytes())


@lru_cache(maxsize=256)
def _projected(xy_bytes,triangle_bytes):
    xy=np.frombuffer(xy_bytes,dtype='<f8').reshape(-1,2)
    tri=np.frombuffer(triangle_bytes,dtype='<i8').reshape(-1,3)
    if not len(tri):return GeometryCollection()
    points=xy[tri];ab=points[:,1]-points[:,0];ac=points[:,2]-points[:,0]
    area=np.abs(ab[:,0]*ac[:,1]-ab[:,1]*ac[:,0])*.5
    points=points[area>1e-8]
    if not len(points):return GeometryCollection()
    # Vectorized construction avoids hundreds of thousands of Python Polygon
    # wrappers, while retaining the original nondegenerate-triangle threshold.
    polygons=shapely.polygons(points)
    try:return shapely.union_all(polygons)
    except shapely.GEOSException:
        return shapely.union_all(shapely.set_precision(shapely.make_valid(polygons),1e-6))
