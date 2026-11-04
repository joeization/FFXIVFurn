"""SQLite catalog. IDs are FFXIV Item RowIds; dimensions are metres."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS furniture (
 id INTEGER PRIMARY KEY CHECK(id > 0),
 name TEXT NOT NULL CHECK(length(trim(name)) > 0),
 description TEXT NOT NULL DEFAULT '',
 image_path TEXT,
 length REAL CHECK(length IS NULL OR length > 0),
 width REAL CHECK(width IS NULL OR width > 0),
 height REAL CHECK(height IS NULL OR height > 0),
 patch TEXT,
 marketable INTEGER CHECK(marketable IS NULL OR marketable IN (0,1)),
 cash_shop INTEGER CHECK(cash_shop IS NULL OR cash_shop IN (0,1)),
 dyeable INTEGER CHECK(dyeable IS NULL OR dyeable IN (0,1)),
 dye_channels INTEGER CHECK(dye_channels IS NULL OR (typeof(dye_channels)='integer' AND dye_channels >= 0)),
 scope TEXT CHECK(scope IS NULL OR scope IN ('interior','exterior'))
);
CREATE TABLE IF NOT EXISTS tags (
 id INTEGER PRIMARY KEY,
 category TEXT NOT NULL CHECK(length(trim(category)) > 0),
 name TEXT NOT NULL CHECK(length(trim(name)) > 0),
 UNIQUE(category, name)
);
CREATE TABLE IF NOT EXISTS furniture_tags (
 furniture_id INTEGER NOT NULL REFERENCES furniture(id) ON DELETE CASCADE,
 tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
 source TEXT NOT NULL DEFAULT 'manual',
 confidence REAL CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1),
 PRIMARY KEY(furniture_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_furniture_tags_tag ON furniture_tags(tag_id, furniture_id);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
"""


def _id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('ID must be a positive integer')
    return value


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a non-empty string')
    return value.strip()


def _fields(fields: dict[str, Any]) -> dict[str, Any]:
    allowed = {'name', 'description', 'image_path', 'length', 'width', 'height', 'patch', 'marketable', 'cash_shop', 'dyeable', 'dye_channels', 'scope'}
    if fields.keys() - allowed:
        raise ValueError(f'Unknown fields: {sorted(fields.keys() - allowed)}')
    fields = dict(fields)
    if 'name' in fields:
        fields['name'] = _text(fields['name'], 'name')
    for key in ('description', 'image_path', 'patch'):
        if key in fields and not isinstance(fields[key], str):
            if key == 'description' or fields[key] is not None:
                raise ValueError(f'{key} must be a string' + (' or None' if key != 'description' else ''))
    for key in ('length', 'width', 'height'):
        if key in fields and fields[key] is not None:
            value = fields[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{key} must be a finite positive number in metres or None')
    for key in ('marketable', 'cash_shop', 'dyeable'):
        if key in fields and fields[key] is not None and not isinstance(fields[key], bool):
            raise ValueError(f'{key} must be bool or None')
    if 'dye_channels' in fields and fields['dye_channels'] is not None:
        value = fields['dye_channels']
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError('dye_channels must be a non-negative integer or None')
    if 'scope' in fields and fields['scope'] is not None and fields['scope'] not in ('interior','exterior'):
        raise ValueError('scope must be interior, exterior or None (unknown)')
    return fields


def _like(value: str) -> str:
    # Search terms are literal substrings, not SQL wildcard patterns.
    if not isinstance(value, str):
        raise ValueError('Search text must be a string')
    return '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


class FurnitureDB:
    """One connection per instance; use one instance per MCP request/thread.

    Every mutating method commits atomically. get_* returns None for missing IDs;
    update_* raises KeyError; delete_* returns whether a row was removed.
    """

    def __init__(self, path: str | Path = 'data/furniture.sqlite3'):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys = ON')
        version = self.connection.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1, 2, 3, 4):
            self.close()
            raise ValueError(f'Unsupported database schema version: {version}')
        try:
            with self.connection:
                self.connection.execute('BEGIN IMMEDIATE')
                for statement in SCHEMA.split(';'):
                    if statement.strip():
                        self.connection.execute(statement)
                columns = {r['name'] for r in self.connection.execute('PRAGMA table_info(furniture)')}
                for field in ('marketable', 'cash_shop', 'dyeable'):
                    if field not in columns:
                        self.connection.execute(f'ALTER TABLE furniture ADD COLUMN {field} INTEGER CHECK({field} IS NULL OR {field} IN (0,1))')
                if 'dye_channels' not in columns:
                    self.connection.execute("ALTER TABLE furniture ADD COLUMN dye_channels INTEGER CHECK(dye_channels IS NULL OR (typeof(dye_channels)='integer' AND dye_channels >= 0))")
                if 'scope' not in columns:
                    self.connection.execute("ALTER TABLE furniture ADD COLUMN scope TEXT CHECK(scope IS NULL OR scope IN ('interior','exterior'))")
                self.connection.execute('PRAGMA user_version = 4')
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> FurnitureDB:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def add_furniture(self, id: int, name: str, description: str = '',
                      image_path: str | None = None, length: float | None = None,
                      width: float | None = None, height: float | None = None,
                      patch: str | None = None, marketable: bool | None = None,
                      cash_shop: bool | None = None, dyeable: bool | None = None,
                      dye_channels: int | None = None, scope: str | None = None) -> dict:
        _id(id)
        values = _fields(dict(name=name, description=description, image_path=image_path,
                              length=length, width=width, height=height, patch=patch,
                              marketable=marketable, cash_shop=cash_shop,
                              dyeable=dyeable, dye_channels=dye_channels, scope=scope))
        with self.connection:
            self.connection.execute(
                f"INSERT INTO furniture (id,{','.join(values)}) VALUES ({','.join('?' for _ in range(len(values)+1))})",
                [id, *values.values()])
        return self.get_furniture(id)

    def get_furniture(self, id: int) -> dict | None:
        row = self.connection.execute('SELECT * FROM furniture WHERE id=?', (_id(id),)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for field in ('marketable', 'cash_shop', 'dyeable'):
            if result[field] is not None:
                result[field] = bool(result[field])
        result['tags'] = [dict(t) for t in self.connection.execute('''
            SELECT t.*, ft.source, ft.confidence FROM tags t
            JOIN furniture_tags ft ON ft.tag_id=t.id WHERE ft.furniture_id=?
            ORDER BY t.category, t.name, t.id''', (id,))]
        return result

    def update_furniture(self, id: int, **changes: Any) -> dict:
        _id(id)
        values = _fields(changes)
        with self.connection:
            if values:
                cursor = self.connection.execute(
                    f"UPDATE furniture SET {','.join(k+'=?' for k in values)} WHERE id=?",
                    [*values.values(), id])
                if not cursor.rowcount:
                    raise KeyError(f'Furniture {id} not found')
            elif not self.get_furniture(id):
                raise KeyError(f'Furniture {id} not found')
        return self.get_furniture(id)

    def delete_furniture(self, id: int) -> bool:
        with self.connection:
            return bool(self.connection.execute('DELETE FROM furniture WHERE id=?', (_id(id),)).rowcount)

    def add_tag(self, category: str, name: str) -> dict:
        with self.connection:
            cursor = self.connection.execute('INSERT INTO tags(category,name) VALUES (?,?)',
                                             (_text(category, 'category'), _text(name, 'name')))
        return self.get_tag(cursor.lastrowid)

    def get_tag(self, id: int) -> dict | None:
        row = self.connection.execute('SELECT * FROM tags WHERE id=?', (_id(id),)).fetchone()
        return dict(row) if row else None

    def list_tags(self, category: str | None = None) -> list[dict]:
        sql = 'SELECT * FROM tags'
        args = []
        if category is not None:
            sql += ' WHERE category=?'
            args.append(category)
        return [dict(r) for r in self.connection.execute(sql+' ORDER BY category,name,id', args)]

    def update_tag(self, id: int, **changes: str) -> dict:
        _id(id)
        if changes.keys() - {'category', 'name'}:
            raise ValueError('Only category and name can be updated')
        values = {k: _text(v, k) for k, v in changes.items()}
        with self.connection:
            if values:
                cursor = self.connection.execute(
                    f"UPDATE tags SET {','.join(k+'=?' for k in values)} WHERE id=?",
                    [*values.values(), id])
                if not cursor.rowcount:
                    raise KeyError(f'Tag {id} not found')
            elif not self.get_tag(id):
                raise KeyError(f'Tag {id} not found')
        return self.get_tag(id)

    def delete_tag(self, id: int) -> bool:
        with self.connection:
            return bool(self.connection.execute('DELETE FROM tags WHERE id=?', (_id(id),)).rowcount)

    def add_furniture_tag(self, furniture_id: int, tag_id: int, *,
                          source: str = 'manual', confidence: float | None = None) -> dict:
        _id(furniture_id)
        _id(tag_id)
        source = _text(source, 'source')
        if confidence is not None and (isinstance(confidence, bool) or
            not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or
            not 0 <= confidence <= 1):
            raise ValueError('confidence must be between 0 and 1 or None')
        with self.connection:
            self.connection.execute('''INSERT INTO furniture_tags(furniture_id,tag_id,source,confidence)
                VALUES (?,?,?,?) ON CONFLICT(furniture_id,tag_id)
                DO UPDATE SET source=excluded.source,confidence=excluded.confidence''',
                (furniture_id, tag_id, source, confidence))
        return {'furniture_id': furniture_id, 'tag_id': tag_id, 'source': source, 'confidence': confidence}

    def remove_furniture_tag(self, furniture_id: int, tag_id: int) -> bool:
        with self.connection:
            return bool(self.connection.execute(
                'DELETE FROM furniture_tags WHERE furniture_id=? AND tag_id=?',
                (_id(furniture_id), _id(tag_id))).rowcount)

    def search_furniture(self, *, query: str | None = None, name: str | None = None,
                         description: str | None = None, tag_ids: Iterable[int] = (),
                         tag_mode: str = 'all', limit: int = 50, offset: int = 0,
                         marketable: bool | None = None, cash_shop: bool | None = None,
                         scope: str | None = None) -> list[dict]:
        """query matches name OR description OR tag name/category.

        Explicit name/description and tag filters combine with AND. Tag IDs use
        all (intersection) by default, or any (union). Stable ID ordering.
        """
        ids = list(dict.fromkeys(_id(i) for i in tag_ids))
        if tag_mode not in ('all', 'any'):
            raise ValueError('tag_mode must be all or any')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError('limit must be an integer between 1 and 1000')
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError('offset must be a non-negative integer')
        _fields({'scope':scope})
        clauses, args = [], []
        if scope is not None:
            clauses.append('f.scope=?')
            args.append(scope)
        for field, value in [('marketable', marketable), ('cash_shop', cash_shop)]:
            if value is not None:
                if not isinstance(value, bool):
                    raise ValueError(f'{field} must be bool or None')
                clauses.append(f'f.{field}=?')
                args.append(value)
        if query is not None:
            pattern = _like(query)
            clauses.append("""(f.name LIKE ? ESCAPE '\\' OR f.description LIKE ? ESCAPE '\\'
                OR EXISTS (SELECT 1 FROM furniture_tags ft JOIN tags t ON t.id=ft.tag_id
                WHERE ft.furniture_id=f.id AND (t.name LIKE ? ESCAPE '\\' OR t.category LIKE ? ESCAPE '\\')))""")
            args.extend([pattern]*4)
        for field, value in [('name', name), ('description', description)]:
            if value is not None:
                clauses.append(f"f.{field} LIKE ? ESCAPE '\\'")
                args.append(_like(value))
        if ids:
            placeholders = ','.join('?' for _ in ids)
            if tag_mode == 'all':
                clauses.append(f'''(SELECT COUNT(*) FROM furniture_tags ft
                    WHERE ft.furniture_id=f.id AND ft.tag_id IN ({placeholders}))=?''')
                args.extend([*ids, len(ids)])
            else:
                clauses.append(f'''EXISTS (SELECT 1 FROM furniture_tags ft
                    WHERE ft.furniture_id=f.id AND ft.tag_id IN ({placeholders}))''')
                args.extend(ids)
        sql = 'SELECT f.id FROM furniture f'
        if clauses:
            sql += ' WHERE '+' AND '.join(clauses)
        rows = self.connection.execute(sql+' ORDER BY f.id LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
        return [self.get_furniture(r['id']) for r in rows]
