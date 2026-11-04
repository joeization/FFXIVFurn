"""Private run storage; no imports of the furniture database."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode('utf-8')).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def connect(run_dir):
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'state.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    # Additive staging migration. Back up pre-history databases before schema writes.
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone() and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rounds'").fetchone():
        backup = root / 'state.pre-history.sqlite3'
        if not backup.exists():
            target = sqlite3.connect(backup)
            try:
                db.backup(target)
            finally:
                target.close()
    db.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS rounds (
      number INTEGER PRIMARY KEY, hash TEXT NOT NULL UNIQUE, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, phase TEXT NOT NULL,
      model TEXT NOT NULL, input_hash TEXT NOT NULL, prompt_version TEXT NOT NULL,
      status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
      started_at REAL, finished_at REAL, error TEXT, result TEXT, input TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS responses (
      job_id TEXT NOT NULL REFERENCES jobs(id), attempt INTEGER NOT NULL,
      elapsed REAL NOT NULL, raw TEXT NOT NULL, usage TEXT, error TEXT,
      PRIMARY KEY(job_id,attempt));
    CREATE TABLE IF NOT EXISTS predictions (
      job_id TEXT NOT NULL REFERENCES jobs(id), anon_id TEXT NOT NULL,
      image_hash TEXT NOT NULL, data TEXT NOT NULL,
      PRIMARY KEY(job_id,anon_id));
    CREATE TABLE IF NOT EXISTS vocab_versions (
      hash TEXT PRIMARY KEY, version INTEGER NOT NULL, created_at REAL NOT NULL, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS tag_decisions (
      id TEXT PRIMARY KEY, created_at REAL NOT NULL, data TEXT NOT NULL);
    ''')
    return db


def cached_job(db, job_id):
    row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    if row and row['status'] == 'succeeded':
        return json.loads(row['result'])
    return None


def claim(db, job_id, kind, phase, model, input_value, prompt_version, lease=900):
    now = time.time()
    # Claim under a write lock. Interrupted jobs become reclaimable after lease expiry.
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row and row['status'] == 'running' and now - row['started_at'] < lease:
            raise RuntimeError(f'Job {job_id} still leased; wait for lease expiry')
        if row and row['status'] == 'succeeded':
            return False
        db.execute('''INSERT INTO jobs(id,kind,phase,model,input_hash,prompt_version,status,started_at,input)
          VALUES(?,?,?,?,?,?, 'running',?,?) ON CONFLICT(id) DO UPDATE SET
          status='running',started_at=excluded.started_at,error=NULL,finished_at=NULL''',
                   (job_id, kind, phase, model, digest(input_value), prompt_version, now, dumps(input_value)))
    return True
