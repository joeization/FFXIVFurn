"""Import agy Flash building-material tags into the real DB (house_materials / house_material_tags only)."""
from pathlib import Path
from contextlib import closing
import datetime, json, sqlite3
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'data/furniture.sqlite3'
SRC = 'agy-gemini-3.8-flash-medium'


def main():
    pred = json.loads((ROOT / 'runs/round1/house-materials-agy/predictions.json').read_text(encoding='utf-8'))
    backup = ROOT / 'data/backups' / ('pre-material-tags-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
    with closing(sqlite3.connect(DB)) as s, closing(sqlite3.connect(backup)) as d: s.backup(d)
    with closing(sqlite3.connect(DB)) as c:
        c.execute('PRAGMA foreign_keys=ON')
        with c:
            for k, p in pred.items():
                assert c.execute('SELECT 1 FROM house_materials WHERE asset_key=?', (k,)).fetchone(), k
                c.execute('DELETE FROM house_material_tags WHERE asset_key=?', (k,))
                for t in p['tags']:
                    cat, name = t['key'].split(':', 1)
                    tid = c.execute('SELECT id FROM tags WHERE category=? AND name=?', (cat, name)).fetchone()[0]
                    c.execute('INSERT OR REPLACE INTO house_material_tags VALUES(?,?,?,?,?)', (k, tid, t['confidence'], t['evidence'], SRC))
                c.execute('UPDATE house_materials SET tag_source=?,visual_description=?,proposed_tags=?,uncertain=? WHERE asset_key=?',
                          (SRC + ' (advisory)', p['visual_description'], json.dumps(p.get('proposed', []), ensure_ascii=False), json.dumps(p.get('uncertain', []), ensure_ascii=False), k))
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
        print('tagged', c.execute('SELECT COUNT(DISTINCT asset_key) FROM house_material_tags').fetchone()[0], 'tags', c.execute('SELECT COUNT(*) FROM house_material_tags').fetchone()[0])
        print(c.execute("SELECT category,COUNT(*),SUM(item_id IS NOT NULL),SUM(tag_source IS NOT NULL) FROM house_materials GROUP BY category").fetchall())
        print(c.execute("SELECT asset_key FROM house_materials WHERE tag_source IS NULL").fetchall())
        print(c.execute("SELECT hm.name,group_concat(t.category||':'||t.name,', ') FROM house_materials hm JOIN house_material_tags h ON h.asset_key=hm.asset_key JOIN tags t ON t.id=h.tag_id WHERE hm.name IN ('Glade Flooring','Alpine Inner Wall','Crystal Chandelier') GROUP BY hm.name").fetchall())
        print('top proposed (not tags):', c.execute("SELECT proposed_tags FROM house_materials WHERE proposed_tags!='[]' LIMIT 3").fetchall())


if __name__ == '__main__': main()
