"""Optional description retrieval: FastEmbed E5 + sqlite-vec, never a chat model."""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import sqlite3
import struct
from typing import Iterable

from .database import FurnitureDB, _id, _text

MODEL = 'intfloat/multilingual-e5-small'
DIMENSION = 384
PIPELINE = 'description-e5-passage-query-mean-l2-v1'
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / 'data' / 'model-cache'


class SemanticError(RuntimeError):
    """Optional dependency, native extension, or model inference failure."""


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def vector_blob(vector: Iterable[float]) -> bytes:
    values = [float(v) for v in vector]
    if len(values) != DIMENSION or not all(math.isfinite(v) for v in values):
        raise ValueError(f'Embedding must contain {DIMENSION} finite values')
    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError('Embedding must have a finite non-zero norm')
    return struct.pack(f'<{DIMENSION}f', *(v / norm for v in values))


def load_sqlite_vec(connection: sqlite3.Connection) -> None:
    try:
        import sqlite_vec
    except ImportError as exc:
        raise SemanticError('Semantic search requires optional dependencies: pip install -r requirements-semantic.txt') from exc
    try:
        connection.enable_load_extension(True)
        try:
            sqlite_vec.load(connection)
        finally:
            connection.enable_load_extension(False)
        connection.execute('SELECT vec_version()').fetchone()
    except (sqlite3.Error, OSError, AttributeError) as exc:
        raise SemanticError(f'Cannot load sqlite-vec native extension ({exc}). Check Python/SQLite extension support, DLL architecture and Windows runtime; no fallback was used.') from exc


class E5Embedder:
    """Lazily load the real FastEmbed model; explicit prefixes avoid double prefixing."""

    def __init__(self, model: str = MODEL, cache_dir: str | Path | None = None,
                 local_files_only: bool = False):
        if model != MODEL:
            raise ValueError(f'This index supports only {MODEL} ({DIMENSION} dimensions)')
        self.model_name = model
        self.cache_dir = str(cache_dir or os.environ.get('FASTEMBED_CACHE_PATH') or DEFAULT_CACHE)
        self.local_files_only = local_files_only
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
            supported = TextEmbedding.list_supported_models()
            metadata = next((m for m in supported if m['model'].lower() == MODEL.lower()), None)
            if metadata is None:
                # Official repository supplies onnx/model.onnx. E5 requires attention-mask
                # mean pooling, NOT the generic ONNX implementation's CLS pooling.
                TextEmbedding.add_custom_model(
                    model=MODEL, pooling=PoolingType.MEAN, normalization=True,
                    sources=ModelSource(hf=MODEL), dim=DIMENSION,
                    model_file='onnx/model.onnx', license='mit',
                    description='Multilingual E5 small, masked mean pooling + L2 normalization')
                metadata = next(m for m in TextEmbedding.list_supported_models() if m['model'] == MODEL)
            if metadata['dim'] != DIMENSION:
                raise ValueError(f'FastEmbed model metadata dimension is {metadata["dim"]}, expected {DIMENSION}')
            self._model = TextEmbedding(model_name=MODEL, cache_dir=self.cache_dir,
                                        local_files_only=self.local_files_only)
            if self._model.embedding_size != DIMENSION:
                self._model = None
                raise ValueError('FastEmbed runtime embedding dimension mismatch')
            return self._model
        except ImportError as exc:
            raise SemanticError('FastEmbed is not installed: pip install -r requirements-semantic.txt') from exc
        except Exception as exc:
            raise SemanticError(f'Cannot initialize FastEmbed {MODEL}: {exc}') from exc

    def embed(self, texts: list[str], *, query: bool = False, batch_size: int = 32) -> list[bytes]:
        try:
            model = self._load()
            prefix = 'query: ' if query else 'passage: '
            vectors = [vector_blob(v) for v in model.embed(
                [prefix + text for text in texts], batch_size=batch_size)]
            if len(vectors) != len(texts):
                raise ValueError('FastEmbed returned the wrong number of vectors')
            return vectors
        except SemanticError:
            raise
        except Exception as exc:
            raise SemanticError(f'FastEmbed inference failed: {exc}') from exc


class SemanticIndex:
    """Use an existing FurnitureDB; does not own or close its connection.

    Only this optional class loads the extension. Base catalog schema remains v2.
    One 384-D E5 index per catalog; names/tags are NOT embedding inputs.
    """

    def __init__(self, db: FurnitureDB, *, model: str = MODEL,
                 cache_dir: str | Path | None = None, local_files_only: bool = False):
        self.db = db
        self.embedder = E5Embedder(model, cache_dir, local_files_only)
        self.model = model
        c = db.connection
        load_sqlite_vec(c)
        c.create_function('semantic_text_hash', 1, text_hash, deterministic=True)
        with c:
            c.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS furniture_vectors USING vec0(
                embedding float[384] distance_metric=cosine)''')
            c.execute('''CREATE TABLE IF NOT EXISTS furniture_embedding_metadata (
                furniture_id INTEGER PRIMARY KEY REFERENCES furniture(id) ON DELETE CASCADE,
                model TEXT NOT NULL, dimension INTEGER NOT NULL CHECK(dimension=384),
                pipeline TEXT NOT NULL, text_hash TEXT NOT NULL)''')

    def refresh(self, *, batch_size: int = 32) -> dict:
        """Remove invalid vectors and embed changed descriptions in atomic batches.

        Interrupted runs retain completed batches; unchanged rows are not embedded.
        A concurrent edit during inference is skipped and repaired on the next run.
        """
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise ValueError('batch_size must be an integer between 1 and 1000')
        c = self.db.connection
        stats = dict(model=self.model, dimension=DIMENSION, indexed=0, unchanged=0, removed=0, skipped=0)
        with c:
            stale = c.execute('''SELECT v.rowid FROM furniture_vectors v
                LEFT JOIN furniture f ON f.id=v.rowid
                LEFT JOIN furniture_embedding_metadata m ON m.furniture_id=v.rowid
                WHERE f.id IS NULL OR m.furniture_id IS NULL OR m.model!=? OR m.pipeline!=?
                OR m.dimension!=? OR trim(f.description)='' OR m.text_hash!=semantic_text_hash(f.description)''',
                (self.model, PIPELINE, DIMENSION)).fetchall()
            for row in stale:
                c.execute('DELETE FROM furniture_vectors WHERE rowid=?', (row[0],))
                c.execute('DELETE FROM furniture_embedding_metadata WHERE furniture_id=?', (row[0],))
            stats['removed'] = len(stale)
            c.execute('DELETE FROM furniture_embedding_metadata WHERE furniture_id NOT IN (SELECT rowid FROM furniture_vectors)')
        last_id = 0
        while True:
            rows = c.execute('''SELECT f.id,f.description,m.text_hash FROM furniture f
                LEFT JOIN furniture_embedding_metadata m ON m.furniture_id=f.id
                WHERE f.id>? ORDER BY f.id LIMIT ?''', (last_id, batch_size)).fetchall()
            if not rows:
                break
            last_id = rows[-1]['id']
            pending = []
            for row in rows:
                if not row['description'].strip():
                    continue
                if row['text_hash'] == text_hash(row['description']):
                    stats['unchanged'] += 1
                else:
                    pending.append(row)
            if not pending:
                continue
            blobs = self.embedder.embed([r['description'] for r in pending], batch_size=batch_size)
            with c:
                c.execute('BEGIN IMMEDIATE')
                for row, blob in zip(pending, blobs, strict=True):
                    current = c.execute('SELECT description FROM furniture WHERE id=?', (row['id'],)).fetchone()
                    if current is None or current[0] != row['description']:
                        stats['skipped'] += 1
                        continue
                    c.execute('DELETE FROM furniture_vectors WHERE rowid=?', (row['id'],))
                    c.execute('INSERT INTO furniture_vectors(rowid,embedding) VALUES (?,?)', (row['id'], blob))
                    c.execute('''INSERT OR REPLACE INTO furniture_embedding_metadata
                        (furniture_id,model,dimension,pipeline,text_hash) VALUES (?,?,?,?,?)''',
                        (row['id'], self.model, DIMENSION, PIPELINE, text_hash(row['description'])))
                    stats['indexed'] += 1
        return stats

    def search(self, query: str, *, top_k: int = 10, tag_ids: Iterable[int] = (),
               tag_mode: str = 'all', marketable: bool | None = None,
               cash_shop: bool | None = None, scope: str | None = None) -> list[dict]:
        query = _text(query, 'query')
        if any(ch.isalpha() and ord(ch) > 0x24F for ch in query):
            # Descriptions/tags are English and E5-small cross-lingual retrieval measured unreliable (CJK query: 0/10 category hits).
            raise SemanticError('Semantic queries must be English (non-Latin script rejected); translate first')
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 1000:
            raise ValueError('top_k must be an integer between 1 and 1000')
        if tag_mode not in ('all', 'any'):
            raise ValueError('tag_mode must be all or any')
        ids = list(dict.fromkeys(_id(i) for i in tag_ids))
        clauses = ['m.model=?', 'm.pipeline=?', 'm.dimension=?',
                   "trim(f.description)!=''", 'm.text_hash=semantic_text_hash(f.description)']
        args = [self.model, PIPELINE, DIMENSION]
        if scope is not None:
            if scope not in ('interior','exterior'):
                raise ValueError('scope must be interior, exterior or None')
            clauses.append('f.scope=?')
            args.append(scope)
        for key, value in [('marketable', marketable), ('cash_shop', cash_shop)]:
            if value is not None:
                if not isinstance(value, bool):
                    raise ValueError(f'{key} must be bool or None')
                clauses.append(f'f.{key}=?')
                args.append(value)
        if ids:
            placeholders = ','.join('?' for _ in ids)
            if tag_mode == 'all':
                clauses.append(f'''(SELECT COUNT(*) FROM furniture_tags ft WHERE ft.furniture_id=f.id
                    AND ft.tag_id IN ({placeholders}))=?''')
                args.extend([*ids, len(ids)])
            else:
                clauses.append(f'''EXISTS (SELECT 1 FROM furniture_tags ft WHERE ft.furniture_id=f.id
                    AND ft.tag_id IN ({placeholders}))''')
                args.extend(ids)
        candidates = '''FROM furniture f JOIN furniture_embedding_metadata m ON m.furniture_id=f.id
            JOIN furniture_vectors v ON v.rowid=f.id WHERE ''' + ' AND '.join(clauses)
        c = self.db.connection
        # Empty catalogs/filter results do not cause any model download.
        if c.execute('SELECT 1 ' + candidates + ' LIMIT 1', args).fetchone() is None:
            return []
        blob = self.embedder.embed([query], query=True)[0]
        with c:
            c.execute('BEGIN')
            # Exact sqlite-vec cosine scan of eligible candidates BEFORE LIMIT, not
            # overfetch-then-filter. This prioritizes correct hard filters over ANN.
            rows = c.execute('SELECT f.id,vec_distance_cosine(v.embedding,?) AS distance ' +
                candidates + ' ORDER BY distance,f.id LIMIT ?', [blob, *args, top_k]).fetchall()
            return [dict(distance=float(r['distance']), similarity=1.0-float(r['distance']),
                         furniture=self.db.get_furniture(r['id'])) for r in rows]
