"""Decode a preview PNG per HouseAssets folder: `<name>_T` thumbnail if present, else first albedo `_d` texture."""
from pathlib import Path
import hashlib, json, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture.rendering.native import decode_texture

BASE = ROOT / 'data/house-materials-legacy/MakePlace/Content/HouseAssets'
OUT = ROOT / 'data/house-material-images'


def main():
    cat = json.loads((ROOT / 'outputs/house-materials/catalog.json').read_text(encoding='utf-8'))['items']
    OUT.mkdir(exist_ok=True); rows = []; fails = []
    for it in cat:
        c, n = it['category'], it['folder_name']; d = BASE / c / n
        if not d.exists():
            fails.append({'asset_key': it['asset_key'], 'error': 'folder not extracted'}); continue
        cands = [(d / f'{n}_T.uasset', 'thumbnail')] + [(p, 'albedo-texture') for p in sorted(d.glob('*_d.uasset'))]
        for path, kind in cands:
            if not path.exists(): continue
            try:
                img, meta = decode_texture(path)
                img = img.convert('RGB'); img.thumbnail((512, 512))
                dest = OUT / c / f'{n}.png'; dest.parent.mkdir(exist_ok=True); img.save(dest)
                rows.append({'asset_key': it['asset_key'], 'category': c, 'slot': it['slot'], 'scope': it['scope'], 'name': it['display_guess'],
                             'image_path': str(dest), 'image_sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                             'image_kind': kind, 'source_file': path.name, 'source_sha256': meta['source_sha256']})
                break
            except Exception as e:
                fails.append({'asset_key': it['asset_key'], 'source': path.name, 'error': repr(e)[:200]})
        else:
            fails.append({'asset_key': it['asset_key'], 'error': 'no decodable image'})
    done = {r['asset_key'] for r in rows}
    fails = [f for f in fails if f['asset_key'] not in done or 'source' in f]
    (OUT / 'manifest.json').write_text(json.dumps({'images': rows, 'failures': fails}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(len(rows), 'images;', len({f['asset_key'] for f in fails if f['asset_key'] not in done}), 'items without image;', len(fails), 'decode errors')
    import collections
    print(collections.Counter((r['category'], r['image_kind']) for r in rows))
    for f in fails[:8]: print(f)


if __name__ == '__main__': main()
