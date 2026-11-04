"""Adopt Qwen uncertain-retag results (clean ones) into the real DB, keeping previous tags in tag_revisions.

Usage: apply_retag.py adopt            -> 89 images with no uncertain note and no rule flag
       apply_retag.py manual FILE.json -> {image_hash: {"tags":[keys], "note": "..."}} assistant-visual decisions
Never touches classification_records or final-predictions.json. Assets in tag_manual_review are skipped.
"""
from pathlib import Path
from contextlib import closing
import datetime, json, sqlite3, sys
ROOT = Path(__file__).resolve().parents[1]
F = ROOT / 'runs/round1/finalization'; DB = ROOT / 'data/furniture.sqlite3'


def apply(c, h, assets, tags, source, note):
    """tags: list of (key, confidence, evidence)."""
    for key in assets:
        iid = c.execute('SELECT item_id FROM candidate_assets WHERE asset_key=?', (key,)).fetchone()[0]
        if c.execute('SELECT 1 FROM tag_manual_review WHERE asset_key=?', (key,)).fetchone(): continue
        prev = sorted(r[0] for r in c.execute("SELECT t.category||':'||t.name FROM candidate_tags ct JOIN tags t ON t.id=ct.tag_id WHERE ct.asset_key=?", (key,)))
        c.execute('DELETE FROM candidate_tags WHERE asset_key=?', (key,))
        c.execute("DELETE FROM furniture_tags WHERE furniture_id=? AND source LIKE 'qwen-visual:%'", (iid,))
        for k, conf, ev in tags:
            cat, name = k.split(':', 1); tid = c.execute('SELECT id FROM tags WHERE category=? AND name=?', (cat, name)).fetchone()[0]
            cid = c.execute("SELECT concept_id FROM tag_concepts WHERE tag_id=? AND status='accepted'", (tid,)).fetchone()[0]
            c.execute('INSERT OR REPLACE INTO candidate_tags VALUES(?,?,?,?,?)', (key, tid, conf, ev, cid))
            c.execute('INSERT INTO furniture_tags(furniture_id,tag_id,source,confidence) VALUES(?,?,?,?) ON CONFLICT(furniture_id,tag_id) DO UPDATE SET source=excluded.source,confidence=excluded.confidence', (iid, tid, source, conf))
        c.execute('INSERT INTO tag_revisions(asset_key,image_hash,source,previous_tags,new_tags,note,at) VALUES(?,?,?,?,?,?,?)',
                  (key, h, source, json.dumps(prev), json.dumps([t[0] for t in tags]), note, datetime.datetime.now().isoformat(timespec='seconds')))
        c.execute("UPDATE tag_review_suggestions SET status='considered' WHERE image_hash=?", (h,))


def main():
    mode = sys.argv[1]
    vocab = json.loads((F / 'frozen-vocab.json').read_text(encoding='utf-8')); acc = {c['key'] for c in vocab['concepts'] if c['status'] == 'accepted'}
    ch = json.loads((F / 'qwen-uncertain-retag/report.json').read_text(encoding='utf-8'))['changes']
    jobs = []
    if mode == 'adopt':
        for x in ch:
            if not x['after'].get('uncertain') and not any(i['issues'] for i in x['post_review_checks']):
                jobs.append((x['image_hash'], x['asset_keys'], [(t['key'], t['confidence'], t['evidence']) for t in x['after']['tags']], 'qwen-retag:uncertain', 'adopted: no uncertain note, no rule flag'))
    else:
        dec = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')); by = {x['image_hash']: x for x in ch}
        for h, d in dec.items(): jobs.append((h, by[h]['asset_keys'], [(k, 0.8, 'assistant visual review') for k in d['tags']], 'manual-review', d['note']))
    for _, _, tags, _, _ in jobs: assert all(t[0] in acc for t in tags), [t[0] for t in tags if t[0] not in acc]
    backup = ROOT / 'data/backups' / ('pre-retag-' + mode + '-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
    with closing(sqlite3.connect(DB)) as s, closing(sqlite3.connect(backup)) as d: s.backup(d)
    with closing(sqlite3.connect(DB)) as c:
        c.execute('PRAGMA foreign_keys=ON')
        with c:
            c.execute('CREATE TABLE IF NOT EXISTS tag_revisions(id INTEGER PRIMARY KEY,asset_key TEXT NOT NULL,image_hash TEXT NOT NULL,source TEXT NOT NULL,previous_tags TEXT NOT NULL,new_tags TEXT NOT NULL,note TEXT NOT NULL,at TEXT NOT NULL)')
            for h, assets, tags, src, note in jobs: apply(c, h, assets, tags, src, note)
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
        print(mode, 'jobs', len(jobs), 'revisions', c.execute('SELECT COUNT(*) FROM tag_revisions').fetchone()[0], 'backup', backup.name)


if __name__ == '__main__': main()
