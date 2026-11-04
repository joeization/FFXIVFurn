"""Store each furniture item's default dye (ItemData `Dye`, unique-name match) in table item_default_dye. Colours come from public Stain.csv at render time.

The app shows an undyed placed item in its default dye; measured against the user's app screenshot (Flooring Mat / Cork Brown, Oriental Round Table /
Qiqirn Brown) base x StainColour matches within ~10/255 while the material's own `Tint` parameter does not.
"""
from pathlib import Path
from contextlib import closing
import collections, csv, datetime, sqlite3, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from fill_item_metadata import parse_itemdata, ITEMDATA

DB = ROOT / 'data/furniture.sqlite3'


def main():
    stain = {r['Name'].lower(): r['Name'] for r in csv.DictReader(open(ROOT / 'data/external/Stain.csv', encoding='utf-8')) if r['Color'] != '0'}
    by = collections.defaultdict(list)
    for n, i in parse_itemdata(ITEMDATA.read_bytes()): by[n.lower()].append(i.get('Dye'))
    backup = ROOT / 'data/backups' / ('pre-default-dye-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
    with closing(sqlite3.connect(DB)) as s, closing(sqlite3.connect(backup)) as d: s.backup(d)
    stat = collections.Counter(); unknown = collections.Counter()
    with closing(sqlite3.connect(DB)) as c:
        with c:
            c.execute('DROP TABLE IF EXISTS item_default_dye')
            c.execute('CREATE TABLE item_default_dye(item_id INTEGER PRIMARY KEY REFERENCES furniture(id),dye_name TEXT NOT NULL,source TEXT NOT NULL)')
            for iid, name in c.execute('SELECT id,name FROM furniture').fetchall():
                vals = by.get(name.lower(), [])
                if len(vals) != 1: stat['no unique ItemData record'] += 1; continue
                dye = vals[0]
                if not dye: stat['no default dye'] += 1; continue
                if dye.lower() not in stain: unknown[dye] += 1; stat['dye name not in Stain.csv'] += 1; continue
                c.execute('INSERT INTO item_default_dye VALUES(?,?,?)', (iid, stain[dye.lower()], 'ItemData.uexp Dye (unique-name match, case-insensitive to Stain.csv)')); stat['stored'] += 1
        print(dict(stat), dict(unknown))
        print(c.execute('SELECT f.name,d.dye_name FROM item_default_dye d JOIN furniture f ON f.id=d.item_id ORDER BY random() LIMIT 6').fetchall())
    print('backup', backup.name)


if __name__ == '__main__': main()
