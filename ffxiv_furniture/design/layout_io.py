"""Reading / exporting ReMakePlace layouts for the refinement loop."""
from __future__ import annotations
import json
import math
from pathlib import Path


def read_layout(p):
    b = Path(p).read_bytes(); u16 = b[:2] in (b'\xff\xfe', b'\xfe\xff'); return json.loads(b.decode('utf-16' if u16 else 'utf-8-sig')), u16


def export_layout(src_layout, objs, scale):
    """Copy of the source layout with every non-removed object at its current pose (objs are in the same order as src_layout['interiorFurniture'])."""
    out = json.loads(json.dumps(src_layout)); items = []
    for o, it in zip(objs, src_layout['interiorFurniture']):
        if o.removed: continue
        it = json.loads(json.dumps(it)); a = math.radians(o.yaw) / 2
        it['transform']['location'] = [o.pivot[0] * scale, o.pivot[1] * scale, o.z * scale]; it['transform']['rotation'] = [0, 0, math.sin(a), math.cos(a)]
        items.append(it)
    out['interiorFurniture'] = items; return out


def write_layout(path, layout, u16):
    Path(path).write_bytes((json.dumps(layout, ensure_ascii=False, indent='\t') + '\n').encode('utf-16' if u16 else 'utf-8'))
