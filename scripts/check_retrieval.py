"""Smoke/accuracy check of tag and semantic retrieval on the real DB (read-only use of results)."""
from pathlib import Path
import sys, json, sqlite3
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.semantic import SemanticIndex
import inspect

db = FurnitureDB(ROOT / 'data/furniture.sqlite3')
c = db.connection
cat = lambda iid: c.execute("SELECT source_category FROM candidate_assets WHERE item_id=?", (iid,)).fetchone()[0]
tid = lambda category, name: c.execute('SELECT id FROM tags WHERE category=? AND name=?', (category, name)).fetchone()[0]
print('search_furniture params:', list(inspect.signature(db.search_furniture).parameters))

# 1) Tag queries
tests = [
    ([('form', 'tall cabinet')], 'interior', 'Furniture/Cabinet|Furniture/Shelf'),
    ([('form', 'rectangular table')], 'interior', 'Furniture/Table'),
    ([('color', 'red'), ('material', 'wood-like appearance')], 'interior', None),
]
print('\n== TAG QUERIES (mode=all)')
for tags, scope, expect in tests:
    ids = [tid(*t) for t in tags]
    rows = db.search_furniture(tag_ids=ids, tag_mode='all', scope=scope, limit=1000)
    cats = {}
    for r in rows: k = cat(r['id']); cats[k] = cats.get(k, 0) + 1
    hit = sum(v for k, v in cats.items() if expect and k in expect.split('|')) if expect else None
    print(tags, scope, 'n=', len(rows), 'top categories', sorted(cats.items(), key=lambda x: -x[1])[:4], 'expected-category hits', hit)
    print('   sample:', [r['name'] for r in rows[:6]])

# 2) Semantic queries with expected source_category prefix (independent: path-derived)
sem = SemanticIndex(db, cache_dir=ROOT / 'data/model-cache', local_files_only=True)
Q = [('a round wooden dining table', 'Furniture/Table'), ('a tall bookshelf full of books', 'Furniture/Shelf'),
     ('a soft sofa with cushions', 'Furniture/Chair'), ('a hanging lantern light', 'Lighting'),
     ('a rug on the floor', 'Furniture/Rug'), ('a potted plant', 'Greenery'),
     ('a painting hanging on a wall', 'Furniture/Wall-Mounted'), ('a cabinet with doors and drawers', 'Furniture/Cabinet'),
     ('stuffed toy doll', 'Item/Stuffed'), ('plate of food on a table', 'Item/Food'),
     ('紅色的木製櫃子', 'Furniture/Cabinet'), ('舒適的沙發', 'Furniture/Chair'), ('吊燈', 'Lighting')]
tot = hit = 0
print('\n== SEMANTIC (top-10, interior unless noted)')
for q, exp in Q:
    res = [dict(r['furniture'], similarity=r['similarity']) for r in sem.search(q, top_k=10, scope='interior')]
    cs = [cat(r['id']) for r in res]
    h = sum(x.startswith(exp) for x in cs); tot += len(cs); hit += h
    print(f'{q!r:40} hits {h}/{len(cs)} expect {exp}; top3: {[r["name"] for r in res[:3]]}')
print('overall top-10 precision vs path category:', round(hit / tot, 2))

# 3) hybrid: semantic + tag + scope hard filter
ids = [tid('color', 'red')]
res = [dict(r['furniture'], similarity=r['similarity']) for r in sem.search('a chair', top_k=8, scope='interior', tag_ids=ids)]
print('\nhybrid "a chair" + color:red:', [(r['name'], cat(r['id'])) for r in res])
res = [dict(r['furniture'], similarity=r['similarity']) for r in sem.search('a bench', top_k=5, scope='exterior')]
print('exterior scope "a bench":', [(r['name'], c.execute('SELECT scope FROM furniture WHERE id=?', (r['id'],)).fetchone()[0]) for r in res])
db.close()
