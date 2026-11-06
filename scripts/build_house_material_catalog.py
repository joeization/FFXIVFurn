"""Path-level inventory of native HouseAssets (wallpaper/flooring/ceiling light/...).

Not a classification: no tags, no Item IDs, no dimensions. Source = retoc listing only.
"""
from pathlib import Path
import csv, json, re, hashlib, collections, urllib.parse, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture.config import local_input


def listing():
    return local_input('FFXIVFURN_INSPECTION_DIR', 'your ReMakePlace inspection directory') / 'asset-paths.txt'


OUT = ROOT / 'outputs/house-materials'
INTERIOR = {'Wallpaper': 'wall', 'Flooring': 'floor', 'CeilingLight': 'ceiling_light'}


def human(n):
    n = re.sub(r'0x([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), n)
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', n)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = collections.defaultdict(lambda: collections.defaultdict(list))
    for line in listing().read_text(encoding='utf-8').splitlines():
        m = re.search(r'Content/HouseAssets/([^/]+)/([^/]+)/([^/\s]+)$', line.strip())
        if m:
            items[m.group(1)][m.group(2)].append(m.group(3))
    rows = []
    for cat, names in sorted(items.items()):
        for name, files in sorted(names.items()):
            ext = collections.Counter(f.rsplit('.', 1)[-1] for f in files)
            rows.append({
                'asset_key': f'MakePlace/Content/HouseAssets/{cat}/{name}',
                'category': cat,
                'slot': INTERIOR.get(cat) or ('exterior_' + cat.lower()),
                'scope': 'interior' if cat in INTERIOR else ('exterior' if cat != 'Others' else None),
                'folder_name': name,
                'display_guess': human(name),
                'display_source': 'inferred from folder name; not a game string',
                'has_thumbnail_T': any(f.startswith(name + '_T.') for f in files),
                'has_main_asset': f'{name}.uasset' in files,
                'texture_files_d_n_s': sum(bool(re.search(r'_[dns]\.uasset$', f)) for f in files),
                'material_instances': sum(f.startswith('MI_') for f in files),
                'file_count': len(files),
                'item_id': None, 'tags': [],
            })
    src = hashlib.sha256(listing().read_bytes()).hexdigest()
    summ = collections.Counter(r['category'] for r in rows)
    (OUT / 'catalog.json').write_text(json.dumps({'source_listing': str(listing()), 'source_sha256': src,
        'counts_by_category': summ, 'note': 'path inventory only; unclassified; item_id NULL', 'items': rows},
        ensure_ascii=False, indent=1), encoding='utf-8')
    with (OUT / 'catalog.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=[k for k in rows[0] if k != 'tags']); w.writeheader()
        for r in rows:
            w.writerow({k: v for k, v in r.items() if k != 'tags'})
    print(dict(summ), len(rows), 'with _T thumbnail:', {c: sum(r['has_thumbnail_T'] for r in rows if r['category'] == c) for c in summ})


if __name__ == '__main__':
    main()
