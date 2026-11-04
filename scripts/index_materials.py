"""Back up and build the material embedding index in the real DB, then run sample queries."""
from pathlib import Path
import datetime, shutil, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.material_semantic import MaterialIndex

shutil.copy(ROOT / 'data/furniture.sqlite3', ROOT / 'data/backups' / ('pre-material-embed-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3'))
db = FurnitureDB(ROOT / 'data/furniture.sqlite3')
ix = MaterialIndex(db, cache_dir=ROOT / 'data/model-cache', local_files_only=True)
print(ix.refresh_materials(), ix.refresh_materials())
for q, kw in [('dark brown wooden planks floor', dict(category='Flooring')), ('blue wallpaper with floral pattern', dict(category='Wallpaper')),
              ('crystal chandelier with hanging glass', dict(category='CeilingLight')), ('red tiled roof', dict(category='Roof')),
              ('white stone exterior wall', dict(category='ExteriorWall')), ('iron fence', dict(category='Fence')), ('warm lantern light', {})]:
    r = ix.search_materials(q, top_k=4, **kw)
    print(q, '->', [(x['name'], x['category'], round(x['similarity'], 2)) for x in r])
print(db.connection.execute('select count(*) from material_vectors').fetchone()[0], db.connection.execute('pragma integrity_check').fetchone()[0])
db.close()
