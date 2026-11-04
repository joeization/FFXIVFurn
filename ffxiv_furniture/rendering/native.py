"""Bounded UE5.3 single-material texture proof; not a general Unreal material decoder."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import struct
import sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
spec=importlib.util.spec_from_file_location('native_tables',ROOT/'scripts/inspect_house_stairs.py');tables=importlib.util.module_from_spec(spec);spec.loader.exec_module(tables)


def names(path):
    b=Path(path).read_bytes();n=struct.unpack_from('<i',b,32)[0];count,off=struct.unpack_from('<2i',b,36+n+4);result=[]
    for _ in range(count):
        n=struct.unpack_from('<i',b,off)[0];off+=4
        if not 0<abs(n)<10000:raise ValueError('Bad FName string length')
        end=off+(n if n>0 else -n*2);result.append(b[off:end].decode('utf-8' if n>0 else 'utf-16-le').rstrip(chr(0)));off=end+4
    return result


class Reader:
    def __init__(self,data,name_map):self.data=data;self.pos=0;self.names=name_map
    def read(self,fmt):
        size=struct.calcsize(fmt)
        if self.pos+size>len(self.data):raise ValueError('Unexpected end')
        v=struct.unpack_from(fmt,self.data,self.pos);self.pos+=size;return v[0] if len(v)==1 else v
    def header(self):
        fields=[];zero_fields=[];index=0
        for _ in range(64):
            v=self.read('<H');index+=v&127;count=v>>9
            fields.extend(range(index,index+count))
            if v&128:zero_fields.extend(range(index,index+count))
            index+=count
            if v&256:break
        else:raise ValueError('Unbounded unversioned header')
        zero=set()
        if zero_fields:
            count=len(zero_fields);num=1 if count<=8 else 2 if count<=16 else ((count+31)//32)*4
            if self.pos+num>len(self.data):raise ValueError('Truncated zero mask')
            mask=int.from_bytes(self.data[self.pos:self.pos+num],'little');self.pos+=num
            zero={f for i,f in enumerate(zero_fields) if mask&(1<<i)}
        return fields,zero
    def fname(self):
        i,num=self.read('<2i')
        if not 0<=i<len(self.names):raise ValueError('Bad FName index')
        return self.names[i]+('_'+str(num-1) if num else '')
    def parameter_info(self):
        fields,zero=self.header()
        if fields!=[0,1,2] or zero:raise ValueError('Unsupported material parameter info')
        name=self.fname();association=self.read('<b');index=self.read('<i')
        if association!=2 or index!=-1:raise ValueError('Only global material parameters supported')
        return name


def _scan_material_instance(r,imp,parent,table,path):
    """Fallback for material instances with extra serialized properties we cannot skip: scan for FMaterialParameterValue structs.
    Accepts texture params Base/Normal/Specular/DiffuseA/DiffuseB (valid Texture2D import) and vector params Tint/FixedTint/EmissiveColor (4 finite floats). Everything else is ignored."""
    data=r.data;values={};pos=r.pos;tex_names={'Base','Normal','Specular','DiffuseA','DiffuseB'};vec_names={'Tint','FixedTint','EmissiveColor'}   # DiffuseA/B: M_bgUvScroll two-layer albedo (Phasmascape scenes)
    while pos<len(data)-24:
        q=Reader(data,r.names);q.pos=pos
        try:
            fields,zero=q.header()
            if fields!=[0,1,2] or 0 in zero:raise ValueError
            key=q.parameter_info()
            if key in tex_names and 1 not in zero:
                obj=imp[q.read('<i')]
                if obj['class']!='Texture2D':raise ValueError
                value=obj['resolved'];kind='texture'
            elif key in vec_names and 1 not in zero:
                value=list(q.read('<4f'))
                if not all(math.isfinite(v) and -1e3<v<1e3 for v in value):raise ValueError
                kind='vector'
            else:raise ValueError
            if 2 not in zero:q.read('<4I')
        except (ValueError,KeyError,IndexError,struct.error):
            pos+=1;continue
        values.setdefault(key,{'kind':kind,'value':value});pos=q.pos
    return {'parent':parent['resolved'],'parameters':values,'parsed_prefix_bytes':r.pos,'remaining_native_properties_not_decoded':-1,'source_sha256':hashlib.sha256(data).hexdigest(),'scanned':True}


def material_instance(path):
    table=tables.map_tables(path);imp={x['index']:x for x in table['imports']};r=Reader(path.with_suffix('.uexp').read_bytes(),names(path))
    fields,zero=r.header()
    if not fields or fields[0]!=10 or zero:raise ValueError('Unsupported material instance property layout')
    extra=set(f for f in fields if f<=17)-{10,14,15,17}
    parent=imp[r.read('<i')]
    if parent['class']!='Material':raise ValueError('Expected native parent Material')
    if extra:return _scan_material_instance(r,imp,parent,table,path)   # unknown extra property (e.g. field 12, big cached data): recover parameters by structure scan
    values={};property_fields=tuple(fields)
    for field,kind in [(14,'scalar'),(15,'vector'),(17,'texture')]:
        if field not in property_fields:continue
        count=r.read('<i')
        if not 0<=count<=64:raise ValueError('Parameter array out of bounds')
        for _ in range(count):
            fields,zero=r.header()
            if fields!=[0,1,2] or 0 in zero:raise ValueError('Unsupported parameter value struct')
            key=r.parameter_info()
            if 1 in zero:value=0 if kind=='scalar' else [0]*4 if kind=='vector' else None
            elif kind=='scalar':value=r.read('<f')
            elif kind=='vector':
                value=list(r.read('<4f'))
                if not all(math.isfinite(v) for v in value):raise ValueError('Nonfinite material vector')
            else:
                ref=r.read('<i');obj=imp[ref]
                if obj['class']!='Texture2D':raise ValueError('Parameter is not Texture2D')
                value=obj['resolved']
            if 2 not in zero:r.read('<4I') # expression GUID
            values[key]={'kind':kind,'value':value}
    return {'parent':parent['resolved'],'parameters':values,'parsed_prefix_bytes':r.pos,
            'remaining_native_properties_not_decoded':len(r.data)-4-r.pos,'source_sha256':hashlib.sha256(r.data).hexdigest()}


def decode_texture(path):
    b=path.read_bytes();data=path.with_suffix('.uexp').read_bytes();n=struct.unpack_from('<i',b,32)[0]
    name_offset=struct.unpack_from('<i',b,36+n+8)[0];resource_offset=struct.unpack_from('<i',b,name_offset-4)[0]
    version,count=struct.unpack_from('<2I',b,resource_offset)
    if version!=1 or not 1<=count<=32 or resource_offset+8+44*count!=len(b):raise ValueError('Unsupported data-resource table')
    resources=[struct.unpack_from('<IqqqqiI',b,resource_offset+8+44*i) for i in range(count)]
    hits=[]
    for fmt,code,block in [('PF_DXT1',1,8),('PF_DXT5',3,16),('PF_BC5',5,16)]:
        token=struct.pack('<i',len(fmt)+1)+fmt.encode()+b'\0';start=data.find(token)
        if start>=0:hits.append((start,fmt,code,block))
    if len(hits)!=1:raise ValueError('Expected one supported cooked pixel format')
    start,fmt,code,block=hits[0];width,height,packed=struct.unpack_from('<3I',data,start-12)
    if packed!=1 or not 1<=width<=8192 or not 1<=height<=8192:raise ValueError('Unsupported texture dimensions/slices')
    pos=start+4+len(fmt)+1;first,mips=struct.unpack_from('<2i',data,pos);pos+=8
    if first!=0 or mips!=count:raise ValueError('Mip/resource mismatch')
    decoded=None;metadata=[]
    for level in range(mips):
        index=struct.unpack_from('<i',data,pos)[0];pos+=4
        if index!=level:raise ValueError('Unexpected resource index')
        flags,offset,duplicate,size,raw,outer,legacy=resources[index]
        if size!=raw or outer!=0 or duplicate!=-1:raise ValueError('Unsupported bulk resource')
        if legacy&0x100: # BULKDATA_PayloadInSeperateFile
            bulk=path.with_suffix('.ubulk').read_bytes()
            if not 0<=offset<=len(bulk)-size:raise ValueError('External bulk bounds')
            payload=bulk[offset:offset+size]
        elif legacy&0x40: # ForceInlinePayload
            if offset!=pos:raise ValueError('Inline export-relative offset mismatch')
            payload=data[pos:pos+size];pos+=size
        else:raise ValueError(f'Unsupported bulk flags {legacy:#x}')
        w,h,z=struct.unpack_from('<3I',data,pos);pos+=12
        if (w,h,z)!=(max(1,width>>level),max(1,height>>level),1):raise ValueError('Mip dimensions mismatch')
        expected=((w+3)//4)*((h+3)//4)*block
        if len(payload)!=expected or size!=expected:raise ValueError('Block-compressed payload size mismatch')
        if level==0:decoded=Image.frombytes('RGB' if code==5 else 'RGBA',(w,h),payload,'bcn',(code,fmt[3:]))
        metadata.append({'mip':level,'dimensions':[w,h],'bytes':size,'legacy_flags':legacy,'offset':offset})
    if data[pos:]!=struct.pack('<i',0)+bytes(8)+bytes.fromhex('c1832a9e'):
        # Native tail differs between builds; keep bounded unsupported tail explicit.
        tail=data[pos:]
        if len(tail)>32 or tail[-4:]!=bytes.fromhex('c1832a9e'):raise ValueError('Unexpected texture package tail')
    source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,path.with_suffix('.uexp'),path.with_suffix('.ubulk')) if p.exists()}
    return decoded,{'format':fmt,'dimensions':[width,height],'mips':metadata,'source_sha256':hashlib.sha256(data).hexdigest(),'source_file_hashes':source_hashes}

