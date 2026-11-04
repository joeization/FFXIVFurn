"""Build the REAL catalog DB (data/furniture.sqlite3) from the frozen final classification.

Sources (all read-only):
  - runs/round1/finalization/final-predictions.json + frozen-vocab.json (round 006, 1922 images / 1940 assets)
  - outputs/item-id-match/*.json (Item RowIds from public Item.csv; validated 57/57 + 6/6 vs real layouts)
  - data/furniture-test.sqlite3 (57 verified geometry rows only)
  - runs/round1/house-materials-agy/predictions.json (Flash tags for building materials; advisory, source recorded)
Review suggestions (Qwen 41 / agy 24) are stored in tag_review_suggestions with status 'unadopted'; they never alter tags.
Existing DB is backed up and replaced atomically; a pre-existing non-empty furniture table is refused.
"""
from pathlib import Path
from contextlib import closing
import argparse, datetime, hashlib, json, sqlite3, sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ffxiv_furniture import FurnitureDB

rd = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
F = ROOT / 'runs/round1/finalization'


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db', default=str(ROOT / 'data/furniture.sqlite3'))
    ap.add_argument('--allow-partial-materials', action='store_true')
    a = ap.parse_args(); target = Path(a.db).resolve()
    if target.exists():
        with closing(sqlite3.connect(target)) as c:
            if c.execute("SELECT name FROM sqlite_master WHERE name='furniture'").fetchone() and c.execute('SELECT COUNT(*) FROM furniture').fetchone()[0]:
                raise SystemExit('Refusing: target furniture table is not empty')
    vocab = rd(F / 'frozen-vocab.json'); assert vocab['frozen'] is True
    final = rd(F / 'final-predictions.json'); manifest = rd(ROOT / 'runs/round1/manifest.json')['assets']
    match = {r['asset_key']: r for r in rd(ROOT / 'outputs/item-id-match/candidates.json')['results']}
    hmatch = {r['asset_key']: r for r in rd(ROOT / 'outputs/item-id-match/house-material-candidates.json')['results']}
    assert len(manifest) == 1940 and set(x['image_hash'] for x in manifest) == set(final)
    concepts = {c['key']: c for c in vocab['concepts'] if c['status'] == 'accepted'}
    assert len(concepts) == 359
    hm_images = rd(ROOT / 'data/house-material-images/manifest.json')['images']
    hm_pred_path = ROOT / 'runs/round1/house-materials-agy/predictions.json'
    hm_pred = rd(hm_pred_path) if hm_pred_path.exists() else {}
    if len(hm_pred) < len(hm_images) and not a.allow_partial_materials:
        raise SystemExit(f'House-material tagging incomplete ({len(hm_pred)}/{len(hm_images)}); wait or pass --allow-partial-materials')
    from ffxiv_furniture.classification.state import digest
    stage = target.with_suffix('.building.sqlite3')
    if stage.exists(): raise SystemExit('Stale stage file; inspect and remove: ' + str(stage))
    test = sqlite3.connect('file:' + str(ROOT / 'data/furniture-test.sqlite3') + '?mode=ro', uri=True); test.row_factory = sqlite3.Row
    with FurnitureDB(stage) as db:
        c = db.connection
        c.executescript('''
        CREATE TABLE candidate_assets(asset_key TEXT PRIMARY KEY,item_id INTEGER REFERENCES furniture(id),name TEXT NOT NULL,source_category TEXT NOT NULL,
          scope TEXT NOT NULL,image_path TEXT NOT NULL,image_hash TEXT NOT NULL,visual_description TEXT NOT NULL,source_round INTEGER NOT NULL,
          source_vocab_hash TEXT NOT NULL,item_id_evidence TEXT NOT NULL,metadata_status TEXT NOT NULL,length REAL,width REAL,height REAL);
        CREATE TABLE candidate_tags(asset_key TEXT NOT NULL REFERENCES candidate_assets(asset_key),tag_id INTEGER NOT NULL REFERENCES tags(id),
          confidence REAL,evidence TEXT NOT NULL,source_concept TEXT NOT NULL,PRIMARY KEY(asset_key,tag_id));
        CREATE TABLE classification_records(image_hash TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE tag_concepts(concept_id TEXT PRIMARY KEY,tag_id INTEGER REFERENCES tags(id),status TEXT NOT NULL,data TEXT NOT NULL);
        CREATE TABLE tag_review_suggestions(image_hash TEXT NOT NULL,reviewer TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'unadopted',data TEXT NOT NULL,PRIMARY KEY(image_hash,reviewer));
        CREATE TABLE asset_geometry(asset_key TEXT PRIMARY KEY REFERENCES candidate_assets(asset_key),item_id INTEGER REFERENCES furniture(id),
          min_x REAL NOT NULL,min_y REAL NOT NULL,min_z REAL NOT NULL,max_x REAL NOT NULL,max_y REAL NOT NULL,max_z REAL NOT NULL,
          center_x REAL NOT NULL,center_y REAL NOT NULL,center_z REAL NOT NULL,source TEXT NOT NULL,source_sha256 TEXT NOT NULL,method TEXT NOT NULL,evidence TEXT NOT NULL);
        CREATE VIEW furniture_bounds AS SELECT f.*,g.min_x,g.min_y,g.min_z,g.max_x,g.max_y,g.max_z,g.center_x,g.center_y,g.center_z,
          f.length*f.width*f.height AS bounding_box_volume_m3 FROM furniture f JOIN asset_geometry g ON g.item_id=f.id;
        CREATE TABLE house_materials(asset_key TEXT PRIMARY KEY,item_id INTEGER UNIQUE,category TEXT NOT NULL,slot TEXT NOT NULL,scope TEXT,
          name TEXT NOT NULL,name_source TEXT NOT NULL,image_path TEXT,image_sha256 TEXT,image_kind TEXT,item_id_evidence TEXT,tag_source TEXT,visual_description TEXT,proposed_tags TEXT,uncertain TEXT);
        CREATE TABLE house_material_tags(asset_key TEXT NOT NULL REFERENCES house_materials(asset_key),tag_id INTEGER NOT NULL REFERENCES tags(id),
          confidence REAL,evidence TEXT NOT NULL,source TEXT NOT NULL,PRIMARY KEY(asset_key,tag_id));
        CREATE TABLE build_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE INDEX candidate_category_scope ON candidate_assets(source_category,scope);
        CREATE INDEX candidate_tags_tag ON candidate_tags(tag_id,asset_key);
        CREATE INDEX house_material_tags_tag ON house_material_tags(tag_id,asset_key);
        ''')
        tagid = {}
        with c:
            for key, con in sorted(concepts.items()):
                tagid[key] = c.execute('INSERT INTO tags(category,name) VALUES(?,?)', (con['category'], con['name'])).lastrowid
            for con in vocab['concepts']:
                c.execute('INSERT INTO tag_concepts VALUES(?,?,?,?)', (con['concept_id'], tagid.get(con['key']) if con['status'] == 'accepted' else None, con['status'], json.dumps(con, ensure_ascii=False)))
        vocab_hash = digest(vocab); source_job = 'round006-final'; ncand_tags = 0
        with c:
            for x in sorted(manifest, key=lambda r: r['asset_key']):
                m = match[x['asset_key']]; assert m['status'] == 'unique', x['asset_key']
                cand = m['candidates'][0]; iid = cand['item_id']; pred = final[x['image_hash']]
                evidence = json.dumps({'method': 'exact compact-name match to public Item.csv', 'item_csv_name': cand['name'], 'ui_category': m['ui_names'][0],
                                       'source': 'xivapi/ffxiv-datamining Item.csv', 'validated_against_known_layout_ids': 57}, ensure_ascii=False)
                c.execute('INSERT INTO furniture(id,name,description,image_path,scope) VALUES(?,?,?,?,?)', (iid, cand['name'], pred['visual_description'], x['image_path'], x['scope']))
                c.execute('INSERT INTO candidate_assets(asset_key,item_id,name,source_category,scope,image_path,image_hash,visual_description,source_round,source_vocab_hash,item_id_evidence,metadata_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                          (x['asset_key'], iid, cand['name'], x['source_category'], x['scope'], x['image_path'], x['image_hash'], pred['visual_description'], 6, vocab_hash, evidence,
                           'Item ID by name match; app placement untested; dimensions/patch/dye unknown unless filled'))
                for t in pred['tags']:
                    tid = tagid[t['key']]
                    c.execute('INSERT INTO candidate_tags VALUES(?,?,?,?,?)', (x['asset_key'], tid, t['confidence'], t['evidence'], concepts[t['key']]['concept_id']))
                    c.execute('INSERT INTO furniture_tags(furniture_id,tag_id,source,confidence) VALUES(?,?,?,?)', (iid, tid, 'qwen-visual:' + source_job, t['confidence'])); ncand_tags += 1
                for cat, name in (('function', x['source_category']), ('scope', x['scope'])):
                    r = c.execute('SELECT id FROM tags WHERE category=? AND name=?', (cat, name)).fetchone()
                    tid = r[0] if r else c.execute('INSERT INTO tags(category,name) VALUES(?,?)', (cat, name)).lastrowid
                    c.execute('INSERT OR IGNORE INTO furniture_tags(furniture_id,tag_id,source,confidence) VALUES(?,?,?,NULL)', (iid, tid, 'packaged-asset-path'))
            for h, pred in final.items():
                c.execute('INSERT INTO classification_records VALUES(?,?)', (h, json.dumps(pred, ensure_ascii=False)))
            # review suggestions: stored, never applied
            q = rd(F / 'qwen-flagged-review/report.json')
            for ch in q['changes']: c.execute('INSERT INTO tag_review_suggestions VALUES(?,?,?,?)', (ch['image_hash'], 'qwen-trial117', 'unadopted', json.dumps(ch['after'], ensure_ascii=False)))
            ap_ = F / 'agy-flash-review/agy-flash-predictions.json'
            if ap_.exists():
                for h, p in rd(ap_).items(): c.execute('INSERT INTO tag_review_suggestions VALUES(?,?,?,?)', (h, 'agy-gemini-3.8-flash-medium', 'unadopted', json.dumps(p, ensure_ascii=False)))
            # verified geometry (57)
            for col in ('length', 'width', 'height'): pass
            for g in test.execute('SELECT * FROM asset_geometry'):
                row = test.execute('SELECT length,width,height FROM candidate_assets WHERE asset_key=?', (g['asset_key'],)).fetchone()
                assert c.execute('SELECT item_id FROM candidate_assets WHERE asset_key=?', (g['asset_key'],)).fetchone()[0] == g['item_id'], 'Item ID disagrees with verified test DB'
                c.execute('UPDATE furniture SET length=?,width=?,height=? WHERE id=?', (*row, g['item_id']))
                c.execute('UPDATE candidate_assets SET length=?,width=?,height=? WHERE asset_key=?', (*row, g['asset_key']))
                c.execute('INSERT INTO asset_geometry VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', tuple(g))
            # house materials
            imgs = {r['asset_key']: r for r in hm_images}
            for it in rd(ROOT / 'outputs/house-materials/catalog.json')['items']:
                k = it['asset_key']; m = hmatch[k]; iid = m['candidates'][0]['item_id'] if m['status'] == 'unique' else None
                im = imgs.get(k); p = hm_pred.get(k)
                c.execute('INSERT INTO house_materials VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (k, iid, it['category'], it['slot'], it['scope'], m['candidates'][0]['name'] if iid else it['display_guess'],
                     'Item.csv Name' if iid else 'inferred from folder name; no Item match',
                     im['image_path'] if im else None, im['image_sha256'] if im else None, im['image_kind'] if im else None,
                     json.dumps({'method': 'exact compact-name match to public Item.csv', 'ui_category': m['ui_names'][0]}) if iid else None,
                     'agy-gemini-3.8-flash-medium (advisory)' if p else None, p['visual_description'] if p else None,
                     json.dumps(p.get('proposed', []), ensure_ascii=False) if p else None, json.dumps(p.get('uncertain', []), ensure_ascii=False) if p else None))
                for t in (p or {}).get('tags', []):
                    c.execute('INSERT INTO house_material_tags VALUES(?,?,?,?,?)', (k, tagid[t['key']], t['confidence'], t['evidence'], 'agy-gemini-3.8-flash-medium'))
            meta = {'vocab_hash': vocab_hash, 'final_round_hash': 'fb2b29613df990888ea1bdc5b0d9d6c4255445112e880b63766bc10ae11b7e2d', 'final_predictions_sha256': sha(F / 'final-predictions.json'),
                    'item_csv_sha256': sha(ROOT / 'data/external/Item.csv'), 'item_csv_source': 'xivapi/ffxiv-datamining master csv/en/Item.csv (commit 44948e4)',
                    'built_at': datetime.datetime.now().isoformat(timespec='seconds'),
                    'description_source': 'furniture.description is Qwen visual_description, not game flavor text',
                    'tags_note': 'review suggestions (qwen 41 / agy 24) not adopted; see tag_review_suggestions',
                    'unknown': 'patch, dye, marketable, cash_shop and most dimensions are NULL; geometry only for 57 verified assets'}
            for k, v in meta.items(): c.execute('INSERT INTO build_metadata VALUES(?,?)', (k, v))
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
        counts = {t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('furniture', 'tags', 'furniture_tags', 'candidate_assets', 'candidate_tags', 'classification_records', 'tag_concepts', 'tag_review_suggestions', 'asset_geometry', 'house_materials', 'house_material_tags')}
        counts['materials_with_item_id'] = c.execute('SELECT COUNT(*) FROM house_materials WHERE item_id IS NOT NULL').fetchone()[0]
        counts['materials_tagged'] = c.execute('SELECT COUNT(DISTINCT asset_key) FROM house_material_tags').fetchone()[0]
    if target.exists():
        backup = target.parent / 'backups' / ('pre-real-build-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3'); backup.parent.mkdir(exist_ok=True)
        with closing(sqlite3.connect(target)) as s, closing(sqlite3.connect(backup)) as d: s.backup(d)
        print('backup', backup)
    test.close(); stage.replace(target)
    print(json.dumps(counts, indent=1))


if __name__ == '__main__': main()
