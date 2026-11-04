"""Bounded UE5.3 static-mesh geometry reader, not a general Unreal serializer.

Accept only matching position/tangent/UV buffers plus an independently stored
FBoxSphereBounds followed by the UE5.3 eight cooked screen-size records.
"""
from __future__ import annotations
import copy
import functools
import hashlib
import math
from pathlib import Path
import re
import struct


def _screen_sizes(data,offset):
    if offset+68>len(data):return False
    if struct.unpack_from('<I',data,offset)[0] not in (0,1):return False
    values=[struct.unpack_from('<If',data,offset+4+i*8) for i in range(8)]
    return all(flag==1 and math.isfinite(value) and 0<=value<=100 for flag,value in values)


def read_static_mesh_bounds(uexp_path):
    """Parse (memoised per process): keyed by the given path + size/mtime of the .uexp and .uasset, so edited or re-extracted files are re-read.
    Returns a fresh copy each call because callers annotate records (item_id, ...)."""
    path=Path(uexp_path);a=path.stat();b=path.with_suffix('.uasset').stat()
    return copy.deepcopy(_read_static_mesh_bounds_cached(str(path),a.st_mtime_ns,a.st_size,b.st_mtime_ns,b.st_size))


@functools.lru_cache(maxsize=4096)
def _read_static_mesh_bounds_cached(path,_m1,_s1,_m2,_s2):
    return _read_static_mesh_bounds_uncached(path)


def _read_static_mesh_bounds_uncached(uexp_path):
    path=Path(uexp_path);data=path.read_bytes();header=path.with_suffix('.uasset').read_bytes()
    if b'StaticMesh\0' not in header or data[-4:]!=bytes.fromhex('c1832a9e'):
        raise ValueError('Not a supported legacy static-mesh package')
    candidates=[]
    for match in re.finditer(re.escape(struct.pack('<I',12)),data):
        offset=match.start()
        if offset+16>len(data):continue
        stride,count,element_size,count2=struct.unpack_from('<4I',data,offset)
        end=offset+16+count*12
        if stride!=12 or element_size!=12 or count!=count2 or not 3<=count<=2_000_000 or end+26>len(data):continue
        # Adjacent FStaticMeshVertexBuffer metadata and tangent bulk array.
        uvsets,vertices,full_uv,high_tangent,tangent_size,tangent_count=struct.unpack_from('<6I',data,end+2)
        if not (1<=uvsets<=8 and vertices==count and full_uv in (0,1) and high_tangent in (0,1)
                and tangent_count==count and tangent_size==(16 if high_tangent else 8)):continue
        uv_header=end+2+24+tangent_size*count
        if uv_header+8>len(data):continue
        uv_size,uv_count=struct.unpack_from('<2I',data,uv_header)
        allowed_counts={count*uvsets,(count+uvsets%2)*uvsets}
        if uv_size!=(8 if full_uv else 4) or uv_count not in allowed_counts or uv_header+8+uv_size*uv_count>len(data):continue
        points=list(struct.iter_unpack('<3f',data[offset+16:end]))
        if not all(math.isfinite(v) and abs(v)<1e7 for point in points for v in point):continue
        minimum=[min(p[i] for p in points) for i in range(3)]
        maximum=[max(p[i] for p in points) for i in range(3)]
        center=[(lo+hi)/2 for lo,hi in zip(minimum,maximum)]
        extent=[(hi-lo)/2 for lo,hi in zip(minimum,maximum)]
        if any(x<=0 for x in extent):continue
        hits=[]
        for at in range(max(0,len(data)-8192),len(data)-124):
            if not _screen_sizes(data,at+56):continue
            values=struct.unpack_from('<7d',data,at)
            if not all(math.isfinite(v) for v in values):continue
            if any(abs(a-b)>max(.05,abs(b)*1e-4) for a,b in zip(values[:6],center+extent)):continue
            if values[6]<max(extent) or values[6]>math.sqrt(sum(x*x for x in extent))+.1:continue
            farthest=max(math.sqrt(sum((p[i]-values[i])**2 for i in range(3))) for p in points)
            if farthest>values[6]+.1:continue
            hits.append((at,values))
        if len(hits)!=1:continue
        at,values=hits[0]
        candidates.append({'vertex_buffer_offset':offset,'vertex_count':count,'bounds_offset':at,
            'vertex_min_cm':minimum,'vertex_max_cm':maximum,'origin_cm':list(values[:3]),
            'extent_cm':list(values[3:6]),'sphere_radius_cm':values[6],
            'length_m':values[3]*2/100,'width_m':values[4]*2/100,'height_m':values[5]*2/100,
            'local_min_m':[(values[i]-values[i+3])/100 for i in range(3)],
            'local_max_m':[(values[i]+values[i+3])/100 for i in range(3)]})
    if not candidates:raise ValueError('No cross-validated position/tangent/UV/bounds layout found')
    candidates.sort(key=lambda x:x['vertex_count'],reverse=True)
    result=candidates[0]
    result.update(source=str(path.resolve()),source_sha256=hashlib.sha256(data).hexdigest(),
        method='UE5.3 native float32 positions + adjacent tangent/UV arrays + float64 render bounds + cooked screen sizes',
        units='model-local centimetres converted to metres; actor runtime scale not measured',
        supported_vertex_buffers=len(candidates))
    return result
