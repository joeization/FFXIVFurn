"""Triangle buffers associated with a cross-validated static-mesh bounds record."""
import hashlib
from pathlib import Path
import struct


def read_static_mesh_triangles(record):
    """Read adjacent color and raw-index buffers after an already verified position buffer."""
    data=Path(record['source']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=record['source_sha256']:
        raise ValueError('Geometry source changed')
    offset=record['vertex_buffer_offset'];count=record['vertex_count']
    end=offset+16+count*12
    uvsets,vertices,full_uv,high_tangent,tangent_size,tangent_count=struct.unpack_from('<6I',data,end+2)
    uv_header=end+26+tangent_size*tangent_count
    uv_size,uv_count=struct.unpack_from('<2I',data,uv_header)
    color=uv_header+8+uv_size*uv_count
    stride,ncolor=struct.unpack_from('<2I',data,color+2)
    index=color+10
    if ncolor:
        size,num=struct.unpack_from('<2I',data,index)
        if stride!=4 or size!=4 or num!=ncolor or ncolor!=count:
            raise ValueError('Unsupported color buffer')
        index+=8+size*num
    is32,size,num=struct.unpack_from('<3I',data,index)
    if is32 not in (0,1) or size!=1 or num<=0 or index+12+num>len(data):
        raise ValueError('Unsupported index buffer')
    element=4 if is32 else 2
    if num%element or (num//element)%3:
        raise ValueError('Index array is not triangles')
    indices=[x[0] for x in struct.iter_unpack('<I' if is32 else '<H',data[index+12:index+12+num])]
    if min(indices)<0 or max(indices)>=count:
        raise ValueError('Index references missing vertex')
    points=[tuple(v/100 for v in p) for p in struct.iter_unpack('<3f',data[offset+16:end])]
    return points,[tuple(indices[i:i+3]) for i in range(0,len(indices),3)]
