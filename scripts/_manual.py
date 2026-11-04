"""Direct manual iteration helper (user-approved: agent renders and edits the layout JSON itself).
  python scripts/_manual.py render <layout.json> <out_dir>      — unmirrored review renders + rows dump
  python scripts/_manual.py edit <layout.json> <edits.json>     — apply [{id,x,y,yaw,remove}] by instance id (id = index in interiorFurniture)
Renders use the same camera setup as the review loop and are NOT mirrored (matches JSON axes).
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
import numpy as np
from ffxiv_furniture.rendering.pipeline import run_pipeline


def rows_of(layout):
    return [{'id': k, 'name': it['name'], 'x': round(it['transform']['location'][0] / 100, 2), 'y': round(it['transform']['location'][1] / 100, 2),
             'z': round(it['transform']['location'][2] / 100, 2), 'yaw': round(yaw_deg(it['transform']['rotation']), 1)} for k, it in enumerate(layout['interiorFurniture'])]


def yaw_deg(q):
    x, y, z, w = q
    return math.degrees(2 * math.atan2(z, w)) % 360


def q_from_yaw(deg):
    r = math.radians(deg % 360) / 2
    return [0.0, 0.0, round(math.sin(r), 8), round(math.cos(r), 8)]


def main():
    mode = sys.argv[1]
    if mode == 'render':
        src, out = Path(sys.argv[2]), Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
        cam_file = out.parent / 'cams.json'
        cams = json.loads(cam_file.read_text(encoding='utf-8')) if cam_file.exists() else None
        kw = dict(db_path=Path('data/furniture.sqlite3'), room_context=True, rough_room_finish=True, approximate_tint=False, size=(960, 640), mirror_view=False)
        if cams: run_pipeline(src, out, cameras=cams, **kw)
        else: run_pipeline(src, out, **kw)
        lay = json.loads(src.read_bytes().decode('utf-16') if src.read_bytes()[:2] == b'\xff\xfe' else src.read_text(encoding='utf-8-sig'))
        (out / 'rows.json').write_text(json.dumps(rows_of(lay), ensure_ascii=False), encoding='utf-8')
        print('rendered', out, 'items', len(lay['interiorFurniture']))
    elif mode == 'edit':
        src, edits_path = Path(sys.argv[2]), Path(sys.argv[3])
        raw = src.read_bytes(); txt = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8-sig')
        lay = json.loads(txt); edits = json.loads(Path(edits_path).read_text(encoding='utf-8'))
        done = []
        for e in sorted(edits, key=lambda e: -e['id']):
            it = lay['interiorFurniture'][e['id']]
            if e.get('remove'): lay['interiorFurniture'].pop(e['id']); done.append((e['id'], 'removed', it['name'])); continue
            loc = it['transform']['location']
            if 'x' in e: loc[0] = round(e['x'] * 100, 4)
            if 'y' in e: loc[1] = round(e['y'] * 100, 4)
            if 'z' in e: loc[2] = round(e['z'] * 100, 4)
            if 'yaw' in e: it['transform']['rotation'] = q_from_yaw(e['yaw'])
            done.append((e['id'], {k: e[k] for k in ('x', 'y', 'z', 'yaw') if k in e}, it['name']))
        src.write_text(json.dumps(lay, ensure_ascii=False), encoding='utf-8')
        for d in done: print(' ', d)
        print('items now', len(lay['interiorFurniture']))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
