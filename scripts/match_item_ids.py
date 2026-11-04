"""Match local furniture/house-material candidates to FFXIV Item RowIds via public Item.csv.

Evidence only: exact (case/punctuation-insensitive) Item name match. Ambiguous or missing -> NULL.
Validated against the 57 independently known layout IDs. Writes outputs/item-id-match/*.
"""
from pathlib import Path
import csv, json, re, hashlib, collections, sys
ROOT = Path(__file__).resolve().parents[1]
INSP = Path('D:/Downloads/ReMakePlace-agent-inspection')
OUT = ROOT / 'outputs/item-id-match'


def decode(s):
    # asset/folder names escape punctuation as 0xHH (sometimes with an inserted space)
    return re.sub(r'0x([0-9A-Fa-f])[ ]?([0-9A-Fa-f])', lambda m: chr(int(m.group(1) + m.group(2), 16)), s)


def compact(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', decode(s))
    return re.sub('[^a-z0-9]', '', s.lower())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    src = ROOT / 'data/external/Item.csv'
    rows = list(csv.reader(src.open(encoding='utf-8'))); h = rows[0]
    col = {n: h.index(n) for n in ('#', 'Name', 'ItemUICategory', 'ItemSearchCategory', 'IsUntradable')}
    items = [(int(r[col['#']]), r[col['Name']], r[col['ItemUICategory']], r[col['ItemSearchCategory']]) for r in rows[1:] if r and r[col['#']].isdigit() and r[col['Name']]]
    by = collections.defaultdict(list)
    for iid, name, ui, sc in items: by[compact(name)].append({'item_id': iid, 'name': name, 'ui_category': ui, 'search_category': sc})
    catalog = json.loads((INSP / 'asset-folder-catalog.json').read_text(encoding='utf-8'))
    manifest = {a['asset_key']: a for a in json.loads((ROOT / 'runs/round1/manifest.json').read_text(encoding='utf-8'))['assets']}
    known = {}
    import sqlite3
    d = sqlite3.connect('file:' + str(ROOT / 'data/furniture-test.sqlite3') + '?mode=ro', uri=True)
    for k, iid in d.execute('SELECT asset_key,item_id FROM candidate_assets WHERE item_id IS NOT NULL'): known[k] = iid
    uicat = {r[0]: r[1] for r in csv.reader((ROOT / 'data/external/ItemUICategory.csv').open(encoding='utf-8')) if r and r[0].isdigit()}
    res = []; stat = collections.Counter()
    for row in catalog:
        key = row['asset_folder']; name = (manifest.get(key) or {}).get('name') or row['name_key_candidate']
        cands = by.get(compact(name), [])
        # prefer candidates in a housing UI category? keep all, flag ambiguity
        if len(cands) == 1: st = 'unique'
        elif len(cands) == 0: st = 'none'
        else: st = 'ambiguous'
        stat[st] += 1
        res.append({'asset_key': key, 'name': name, 'scope': row['scope'], 'status': st, 'candidates': cands})
        res[-1]['ui_names'] = [uicat.get(c['ui_category']) for c in cands]
    # validation vs known 57
    ok = bad = miss = 0; wrong = []
    for r in res:
        if r['asset_key'] in known:
            if r['status'] == 'unique':
                if r['candidates'][0]['item_id'] == known[r['asset_key']]: ok += 1
                else: bad += 1; wrong.append((r['name'], r['candidates'][0]['item_id'], known[r['asset_key']]))
            else:
                if any(c['item_id'] == known[r['asset_key']] for c in r['candidates']): ok += 0
                miss += 1; wrong.append((r['name'], r['status'], known[r['asset_key']], [c['item_id'] for c in r['candidates']]))
    # building materials (same method; names are folder-name guesses -> extra caution flagged)
    hm = json.loads((ROOT / 'outputs/house-materials/catalog.json').read_text(encoding='utf-8'))['items']
    hres = []
    for it in hm:
        cands = by.get(compact(it['display_guess']), [])
        hres.append({'asset_key': it['asset_key'], 'category': it['category'], 'name': it['display_guess'], 'status': 'unique' if len(cands) == 1 else ('none' if not cands else 'ambiguous'),
                     'candidates': cands, 'ui_names': [uicat.get(c['ui_category']) for c in cands]})
    (OUT / 'house-material-candidates.json').write_text(json.dumps({'method': 'exact compact-name match to Item.csv Name; names inferred from folder names', 'results': hres}, ensure_ascii=False, indent=1), encoding='utf-8')
    print('house materials', dict(collections.Counter(r['status'] for r in hres)), dict(collections.Counter((r['category'], r['status']) for r in hres if r['status'] != 'unique')))
    print(collections.Counter(r['ui_names'][0] for r in hres if r['status'] == 'unique'))
    (OUT / 'candidates.json').write_text(json.dumps({'source': str(src), 'source_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
        'method': 'exact compact-name match to Item.csv Name', 'status_counts': stat, 'validation_vs_57_known': {'agree': ok, 'conflict': bad, 'not_unique_or_missing': miss},
        'results': res}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(dict(stat), 'validation', {'agree': ok, 'conflict': bad, 'not_unique_or_missing': miss})
    for w in wrong[:20]: print(w)


if __name__ == '__main__': main()
