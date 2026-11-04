"""Apply manual (assistant visual) review decisions for the 15 items both Qwen and agy still disputed.

Real DB only: replaces the model-derived tags of those 15 furniture rows, keeps the previous tags in tag_manual_review.previous_tags,
leaves classification_records (raw) and final-predictions.json untouched. Vocabulary: frozen accepted keys only.
"""
from pathlib import Path
from contextlib import closing
import datetime, json, sqlite3
ROOT = Path(__file__).resolve().parents[1]
F = ROOT / 'runs/round1/finalization'
DB = ROOT / 'data/furniture.sqlite3'

D = {  # name -> (tags, rationale / acknowledged rule)
 'Manor Bookshelf': (['form:tall cabinet', 'form:shelving unit', 'form:arched panel', 'material:dark wood appearance', 'ornament:carved trim', 'style:antique'],
    'Arched bookcase with lower doors: both bookshelf and cabinet are true; name/form rule acknowledged.'),
 'Used Banquet Table': (['form:rectangular table', 'form:bench', 'material:wooden planks', 'color:medium brown', 'style:rustic'],
    'Table with attached benches; bench tag is a real component, category rule acknowledged.'),
 'Floating Kitchen Cabinet': (['form:cabinet', 'form:shelving unit', 'material:wood-like appearance', 'color:medium brown'],
    'Wall-mounted cabinet with open shelf; cabinet-in-wall-category rule acknowledged.'),
 'Hingan Bookshelf': (['form:tall cabinet', 'ornament:vertical slats', 'ornament:lattice', 'style:japanese', 'material:dark wood appearance', 'color:reddish brown'],
    'Lattice-door tall cabinet with drawers; name bookshelf not visually confirmed.'),
 'Pastry Cupboard': (['form:shelving unit', 'form:curved', 'theme:food', 'material:wood-like appearance', 'color:brown'],
    'Curved display cupboard holding pastries; shelving form kept, cupboard name rule acknowledged.'),
 'Leatherworking Bench': (['form:table', 'form:shelving unit', 'material:dark wood appearance', 'color:dark brown'],
    'Craft workbench with back shelves, not a seat; bench-name rule acknowledged.'),
 'Camping Furniture': (['form:table', 'form:bench', 'form:seat-like object', 'material:dark wood appearance', 'material:white fabric appearance', 'color:dark brown', 'color:white'],
    'Camp set of table, bench and chair on white mat; bench component acknowledged.'),
 'Goldsmithing Bench': (['form:table', 'form:shelving unit', 'form:curved', 'material:dark frame appearance', 'color:dark'],
    'Curved craft workbench with tall rack; not a seat.'),
 "Merchant's Shelf": (['form:tall cabinet', 'form:shelving unit', 'material:wood-like appearance', 'color:dark brown', 'theme:market goods'],
    'Shelves above, doors below; both forms true.'),
 'Woodworking Bench': (['form:table', 'form:rectangular', 'material:dark wood appearance', 'color:dark brown'],
    'Craft workbench, not a seat.'),
 'Oasis Cupboard': (['form:cabinet', 'form:shelving unit', 'material:wood-like appearance', 'color:brown'],
    'Open upper shelves over lower cabinet; both forms true.'),
 'Manor Counter': (['form:tall cabinet', 'form:shelving unit', 'material:dark wood appearance', 'color:dark brown'],
    'Counter with sink basin under tall shelf hutch; table-name rule acknowledged.'),
 'Classic Dresser': (['form:table', 'form:curved back', 'style:ornate', 'style:antique', 'ornament:scrollwork', 'material:dark wood appearance', 'color:dark brown'],
    'Vanity-style dresser with oval mirror; table form real, no vanity key in vocabulary.'),
 "Mummer's Wardrobe": (['form:open rectangular shelving', 'form:shelving unit', 'material:wood-like appearance', 'color:brown'],
    'Open shelf frame holding footwear; wardrobe name rule acknowledged.'),
 'Dartboard Cabinet': (['form:cabinet', 'theme:dartboard', 'material:wood-like appearance', 'color:dark brown', 'color:black'],
    'Wall cabinet with dartboard; cabinet-in-wall-category rule acknowledged.'),
}


def main():
    vocab = json.loads((F / 'frozen-vocab.json').read_text(encoding='utf-8')); acc = {c['key'] for c in vocab['concepts'] if c['status'] == 'accepted'}
    p15 = json.loads((F / 'problem15.json').read_text(encoding='utf-8'))
    names = {o['name'].replace('_s', "'s"): o for o in p15}
    assert set(names) == set(D), set(names) ^ set(D)
    for n, (tags, _) in D.items(): assert all(t in acc for t in tags), (n, [t for t in tags if t not in acc])
    backup = ROOT / 'data/backups' / ('pre-manual-review-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
    with closing(sqlite3.connect(DB)) as s, closing(sqlite3.connect(backup)) as d: s.backup(d)
    out = []
    with closing(sqlite3.connect(DB)) as c:
        c.execute('PRAGMA foreign_keys=ON')
        with c:
            c.execute('''CREATE TABLE IF NOT EXISTS tag_manual_review(asset_key TEXT PRIMARY KEY,image_hash TEXT NOT NULL,reviewer TEXT NOT NULL,decided_tags TEXT NOT NULL,
                previous_tags TEXT NOT NULL,rationale TEXT NOT NULL,decided_at TEXT NOT NULL)''')
            for n, (tags, why) in D.items():
                o = names[n]; key = o['asset_key']
                iid, h = c.execute('SELECT item_id,image_hash FROM candidate_assets WHERE asset_key=?', (key,)).fetchone()
                prev = [r[0] for r in c.execute("SELECT t.category||':'||t.name FROM candidate_tags ct JOIN tags t ON t.id=ct.tag_id WHERE ct.asset_key=?", (key,))]
                c.execute('DELETE FROM candidate_tags WHERE asset_key=?', (key,))
                c.execute("DELETE FROM furniture_tags WHERE furniture_id=? AND source LIKE 'qwen-visual:%'", (iid,))
                for t in tags:
                    cat, name = t.split(':', 1); tid = c.execute('SELECT id FROM tags WHERE category=? AND name=?', (cat, name)).fetchone()[0]
                    cid = c.execute("SELECT concept_id FROM tag_concepts WHERE tag_id=? AND status='accepted'", (tid,)).fetchone()[0]
                    c.execute('INSERT INTO candidate_tags VALUES(?,?,?,?,?)', (key, tid, 0.8, 'manual visual review (see tag_manual_review)', cid))
                    c.execute('INSERT INTO furniture_tags(furniture_id,tag_id,source,confidence) VALUES(?,?,?,?) ON CONFLICT(furniture_id,tag_id) DO UPDATE SET source=excluded.source,confidence=excluded.confidence', (iid, tid, 'manual-review', 0.8))
                c.execute('INSERT OR REPLACE INTO tag_manual_review VALUES(?,?,?,?,?,?,?)', (key, h, 'assistant-visual', json.dumps(tags), json.dumps(sorted(prev)), why, datetime.datetime.now().isoformat(timespec='seconds')))
                c.execute("UPDATE tag_review_suggestions SET status='considered' WHERE image_hash=?", (h,))
                out.append({'name': n, 'asset_key': key, 'previous': sorted(prev), 'decided': tags, 'rationale': why})
        assert not c.execute('PRAGMA foreign_key_check').fetchall() and c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        print('manual rows', c.execute('SELECT COUNT(*) FROM tag_manual_review').fetchone()[0], 'furniture_tags manual', c.execute("SELECT COUNT(*) FROM furniture_tags WHERE source='manual-review'").fetchone()[0])
    (F / 'manual-review-15.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print('backup', backup)


if __name__ == '__main__': main()
