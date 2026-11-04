"""python -m ffxiv_furniture.rendering --layout ... --output-dir ..."""
import argparse
import json
from pathlib import Path
import sys
import sqlite3
from .pipeline import run_pipeline


def main():
    p=argparse.ArgumentParser(description='Measured native-mesh multiview preview. No app/DB/model writes.')
    p.add_argument('--layout',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--db',type=Path)
    p.add_argument('--cameras',type=Path,help='JSON array,1..8 cameras; position,target in model-local metres')
    p.add_argument('--patch',type=Path,help='Exact source-hash-bound per-instance transform changes')
    p.add_argument('--room-context',action='store_true',help='Include measured local frame/ceiling; actor transforms are NOT app calibrated')
    p.add_argument('--rough-room-finish',action='store_true',help='Flat average wallpaper/flooring colour on room meshes (rough, needs extracted fixtures)')
    p.add_argument('--dye-mode',choices=['default','none','mi'],default='default',help='mi: native material Tint and instance dye (MCP default); default: furniture default dye; none: raw Base')
    p.add_argument('--display-gamma',type=float,default=0.7,help='display lift fitted to app screenshot samples; 1.0 disables')
    p.add_argument('--no-mirror',action='store_true',help='raw projection; default mirrors the picture horizontally to match the app as observed by the user')
    p.add_argument('--three-view',action='store_true',help='Top/front/side near-orthographic cutaway views (no world-transform calibration needed)')
    p.add_argument('--approximate-tint',action='store_true',help='Opt-in Base*Tint approximation; not original shader reconstruction')
    p.add_argument('--labels',action='store_true',help='Write the labeled image only (default: plain image only)')
    p.add_argument('--debug-buffers',action='store_true',help='Opt in to 16-bit IDs PNG and depth NPY for debugging')
    p.add_argument('--artifacts',action='store_true',help='Explicitly save layout/manifest/review-request JSONs (default: PNGs only)')
    p.add_argument('--image-prefix',help='Distinct filename prefix for multiple renders sharing one output directory')
    p.add_argument('--scope',choices=['interior','exterior'],default='interior',help='Explicit scene scope; exterior uses native yard and exteriorFurniture/exteriorScale')
    p.add_argument('--width',type=int,default=960);p.add_argument('--height',type=int,default=640)
    a=p.parse_args()
    try:
        if not 64<=a.width<=1920 or not 64<=a.height<=1440:raise ValueError('Resolution guard: width64..1920,height64..1440')
        result=run_pipeline(a.layout,a.output_dir,db_path=a.db,
            cameras=json.loads(a.cameras.read_text(encoding='utf-8')) if a.cameras else None,
            patch=json.loads(a.patch.read_text(encoding='utf-8')) if a.patch else None,
            room_context=a.room_context,approximate_tint=a.approximate_tint,rough_room_finish=a.rough_room_finish,three_view=a.three_view,mirror_view=not a.no_mirror,dye_mode=a.dye_mode,display_gamma=a.display_gamma,size=(a.width,a.height),labels=a.labels,debug_buffers=a.debug_buffers,artifacts=a.artifacts,image_prefix=a.image_prefix,scope=a.scope)
        print(json.dumps({k:result[k] for k in ['geometry_assets','material_slots','textured_slots','untextured_slots','warnings','elapsed_seconds','outside_floor_projection']},ensure_ascii=False,indent=2))
        return 0
    except (ValueError,KeyError,OSError,sqlite3.Error) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
