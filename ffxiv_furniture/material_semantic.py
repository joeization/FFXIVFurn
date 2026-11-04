"""Optional E5 semantic index for house_materials (wallpaper/flooring/lights/exterior parts).

Same model/pipeline as the furniture index; text = visual_description (English). Separate vec0 table keyed by
house_materials.rowid, so furniture indexing is unaffected. English-only queries.
"""
from __future__ import annotations
from .semantic import (DIMENSION, PIPELINE, SemanticError, SemanticIndex, load_sqlite_vec, text_hash)


class MaterialIndex(SemanticIndex):
    def __init__(self, db, **kw):
        super().__init__(db, **kw)
        c = db.connection
        with c:
            c.execute('CREATE VIRTUAL TABLE IF NOT EXISTS material_vectors USING vec0(embedding float[384] distance_metric=cosine)')
            c.execute('''CREATE TABLE IF NOT EXISTS material_embedding_metadata(material_rowid INTEGER PRIMARY KEY,
                model TEXT NOT NULL,dimension INTEGER NOT NULL,pipeline TEXT NOT NULL,text_hash TEXT NOT NULL)''')

    def refresh_materials(self, batch_size: int = 32) -> dict:
        c = self.db.connection
        stats = dict(indexed=0, unchanged=0, removed=0)
        rows = c.execute("SELECT rowid,visual_description FROM house_materials WHERE trim(coalesce(visual_description,''))!=''").fetchall()
        valid = {r[0] for r in rows}
        with c:
            for (rid,) in c.execute('SELECT material_rowid FROM material_embedding_metadata').fetchall():
                if rid not in valid:
                    c.execute('DELETE FROM material_vectors WHERE rowid=?', (rid,))
                    c.execute('DELETE FROM material_embedding_metadata WHERE material_rowid=?', (rid,)); stats['removed'] += 1
        done = {r[0]: r[1] for r in c.execute('SELECT material_rowid,text_hash FROM material_embedding_metadata')}
        todo = [r for r in rows if done.get(r[0]) != text_hash(r[1])]
        stats['unchanged'] = len(rows) - len(todo)
        for i in range(0, len(todo), batch_size):
            part = todo[i:i + batch_size]
            blobs = self.embedder.embed([r[1] for r in part], batch_size=batch_size)
            with c:
                for r, b in zip(part, blobs, strict=True):
                    c.execute('DELETE FROM material_vectors WHERE rowid=?', (r[0],))
                    c.execute('INSERT INTO material_vectors(rowid,embedding) VALUES(?,?)', (r[0], b))
                    c.execute('INSERT OR REPLACE INTO material_embedding_metadata VALUES(?,?,?,?,?)', (r[0], self.model, DIMENSION, PIPELINE, text_hash(r[1])))
                    stats['indexed'] += 1
        return stats

    def search_materials(self, query: str, *, top_k: int = 10, category: str | None = None,
                         slot: str | None = None, scope: str | None = None, tag_ids=(), require_item_id: bool = True) -> list[dict]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query must be non-empty text')
        if any(ch.isalpha() and ord(ch) > 0x24F for ch in query):
            raise SemanticError('Semantic queries must be English (non-Latin script rejected); translate first')
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 1000:
            raise ValueError('top_k must be an integer between 1 and 1000')
        c = self.db.connection
        where = ['m.model=?', 'm.pipeline=?', 'm.text_hash=semantic_text_hash(h.visual_description)']; args = [self.model, PIPELINE]
        for col, v in (('category', category), ('slot', slot), ('scope', scope)):
            if v is not None: where.append(f'h.{col}=?'); args.append(v)
        if require_item_id: where.append('h.item_id IS NOT NULL')
        for t in dict.fromkeys(int(x) for x in tag_ids):
            where.append('EXISTS(SELECT 1 FROM house_material_tags t WHERE t.asset_key=h.asset_key AND t.tag_id=?)'); args.append(t)
        blob = self.embedder.embed([query], query=True)[0]
        rows = c.execute('SELECT h.asset_key,h.item_id,h.category,h.slot,h.scope,h.name,vec_distance_cosine(v.embedding,?) AS d '
                         'FROM material_vectors v JOIN house_materials h ON h.rowid=v.rowid JOIN material_embedding_metadata m ON m.material_rowid=v.rowid '
                         'WHERE ' + ' AND '.join(where) + ' ORDER BY d LIMIT ?', [blob, *args, top_k]).fetchall()
        return [dict(asset_key=r[0], item_id=r[1], category=r[2], slot=r[3], scope=r[4], name=r[5], similarity=1 - float(r[6])) for r in rows]
