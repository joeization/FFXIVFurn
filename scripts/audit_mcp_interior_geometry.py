"""Measure style geometry discrepancies without modifying runtime code."""
import json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture.geometry import read_static_mesh_bounds
from ffxiv_furniture.geometry_mesh import read_static_mesh_triangles
from ffxiv_furniture.deco.core import Room
from shapely.geometry import Polygon
from shapely.ops import unary_union
O=Path(os.environ.get('MCP_AUDIT_OUTPUT', str(ROOT/'outputs/mcp-interior-support-audit')))
B=ROOT/'outputs/interior-direction-audit/legacy/MakePlace/Content/HouseAssets/InteriorStyles'
def poly(p):
    v,t=read_static_mesh_triangles(read_static_mesh_bounds(p))
    return unary_union([p for tri in t if (p:=Polygon([(v[i][0],v[i][1]) for i in tri])).area>1e-8]).buffer(.002).buffer(-.002)
def main():
    out=[];common=poly(B/'SizeCommon/Medium/UpperFloor.uexp')
    for summary in json.loads((O/'summary.json').read_text()):
        s=summary['style'];r=Room(s)
        f=B/s/'Medium/GroundFloor.uexp';u=B/s/'Medium/UpperFloor.uexp'
        if not f.exists(): f=B/'SizeCommon/Medium/GroundFloor.uexp'
        expected=poly(f);expected_u=poly(u) if u.exists() else common
        row=dict(style=s,room_style_label=r.style,ground_area_m2=r.floor.area,upper_area_m2=r.upper.area,ground_native_source=str(f) if f.exists() else None,ground_native_symmetric_difference_m2=r.floor.symmetric_difference(expected).area if expected is not None else None,upper_native_symmetric_difference_m2=r.upper.symmetric_difference(expected_u).area)
        if not summary['errors']:
            renders=ROOT/'outputs/deco-sessions'/summary['session']/'renders'
            manifests=list(renders.glob('*up_overview*-manifest.json')) or list(renders.glob('*up_overview*/manifest.json'));assert len(manifests)==1,'Run the audit render with diagnostics=true'
            m=json.loads(manifests[0].read_text());up=next(v for v in m['objects'].values() if v.get('instance_id')=='up-floor')
            row['rendered_upper_source']=up['source'];row['room_vs_render_upper_difference_m2']=r.upper.symmetric_difference(poly(Path(up['source']))).area
            row['rendered_stair_transforms']={v['instance_id']:v['decoded_actor_transform'] for v in m['objects'].values() if v.get('instance_id') in ('stair-up','stair-down')}
        out.append(row)
    (O/'geometry-evidence.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
