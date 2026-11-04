"""Fill patch / dyeable / dye_channels / marketable in the real DB.

- patch: app ItemData.uexp record `Patch` property, matched by exact Item name; only when exactly one ItemData record carries that name.
- dyeable/dye_channels: public Item.csv DyeCount (0 -> dyeable false, 0 channels). ItemData `Dye` was cross-checked (707/708 agree).
- marketable: Item.csv ItemSearchCategory>0 and not IsUntradable.
- cash_shop stays NULL (no source). Existing non-NULL values are never overwritten. Same for house_materials.
"""
from pathlib import Path
from contextlib import closing
import collections, csv, datetime, json, re, sqlite3, struct, sys
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'data/furniture.sqlite3'
ITEMDATA = Path('D:/Downloads/ReMakePlace-agent-inspection/data-legacy/MakePlace/Content/Data/ItemData.uexp')


def fstr(b, o):
    if o + 4 > len(b): return None
    n = struct.unpack_from('<i', b, o)[0]
    if not 1 < n < 200 or o + 4 + n > len(b): return None
    s = b[o + 4:o + 4 + n]
    if s[-1:] != b'\x00' or not all(32 <= c < 127 for c in s[:-1]): return None
    return s[:-1].decode(), o + 4 + n


def parse_itemdata(d):
    recs = []; prev = 0
    for m in re.finditer(rb'\x06\x00\x00\x00Patch\x00', d):
        pm = m.start(); found = None
        for back in range(4, 120):
            o = pm - back
            if o < prev: break
            if struct.unpack_from('<I', d, o)[0] not in (1, 2, 3, 4): continue
            p = o + 4; items = {}; ok = True
            for _ in range(struct.unpack_from('<I', d, o)[0]):
                k = fstr(d, p); v = k and fstr(d, k[1])
                if not v: ok = False; break
                items[k[0]] = v[0]; p = v[1]
            if ok and 'Patch' in items and p > pm: found = (o, p, items); break
        if not found: continue
        seg = d[prev:found[0]]; name = None
        for mm in re.finditer(rb'[\x02-\x7f]\x00\x00\x00', seg):
            r = fstr(seg, mm.start())
            if r and len(r[0]) >= 2: name = r[0]; break
        if name: recs.append((name, found[2]))
        prev = found[1]
    return recs


def main():
    recs = parse_itemdata(ITEMDATA.read_bytes())
    by = collections.defaultdict(list)
    for n, i in recs: by[n.lower()].append(i['Patch'])
    rows = list(csv.reader((ROOT / 'data/external/Item.csv').open(encoding='utf-8'))); h = rows[0]
    ix = {n: h.index(n) for n in ('#', 'DyeCount', 'IsUntradable', 'ItemSearchCategory')}
    meta = {int(r[ix['#']]): r for r in rows[1:] if r and r[ix['#']].isdigit()}
    backup = ROOT / 'data/backups' / ('pre-item-metadata-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
    with closing(sqlite3.connect(DB)) as s, closing(sqlite3.connect(backup)) as d: s.backup(d)
    stat = collections.Counter()
    with closing(sqlite3.connect(DB)) as c:
        with c:
            cols = {r[1] for r in c.execute('PRAGMA table_info(house_materials)')}
            for col in ('patch TEXT', 'dyeable INTEGER', 'dye_channels INTEGER', 'marketable INTEGER'):
                if col.split()[0] not in cols: c.execute('ALTER TABLE house_materials ADD COLUMN ' + col)
            for table, key in (('furniture', 'id'), ('house_materials', 'item_id')):
                for iid, name, patch, dyeable, channels, mkt in c.execute(f'SELECT {key},name,patch,dyeable,dye_channels,marketable FROM {table} WHERE {key} IS NOT NULL').fetchall():
                    r = meta.get(iid); upd = {}
                    pv = by.get(name.lower(), [])
                    if patch is None and len(pv) == 1: upd['patch'] = pv[0]
                    elif patch is None: stat[table + ':patch-' + ('missing' if not pv else 'ambiguous')] += 1
                    if r:
                        dc = int(r[ix['DyeCount']] or 0)
                        if dyeable is None: upd['dyeable'] = int(dc > 0)
                        if channels is None: upd['dye_channels'] = dc
                        if mkt is None: upd['marketable'] = int(int(r[ix['ItemSearchCategory']] or 0) > 0 and r[ix['IsUntradable']].lower() != 'true')
                    if upd:
                        c.execute(f'UPDATE {table} SET ' + ','.join(f'{k}=?' for k in upd) + f' WHERE {key}=?', [*upd.values(), iid]); stat[table + ':updated'] += 1
            c.execute('INSERT OR REPLACE INTO build_metadata VALUES(?,?)', ('item_metadata_sources',
                'patch=ItemData.uexp Patch (unique-name match); dyeable/dye_channels=Item.csv DyeCount; marketable=Item.csv ItemSearchCategory>0 & !IsUntradable; cash_shop unknown'))
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        print(dict(stat))
        for t in ('furniture', 'house_materials'):
            print(t, c.execute(f'SELECT COUNT(*),COUNT(patch),SUM(dyeable),SUM(marketable) FROM {t}').fetchone())
        print(c.execute("SELECT name,patch,dyeable,dye_channels,marketable FROM furniture WHERE name IN ('Leather Sofa','Riviera Desk','Oasis Pendant Lamp')").fetchall())
    print('parsed', len(recs), 'backup', backup.name)


if __name__ == '__main__': main()
