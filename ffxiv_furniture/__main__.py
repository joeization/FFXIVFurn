"""Run with python -m ffxiv_furniture --db PATH COMMAND."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .database import FurnitureDB

from .config import catalog_path
DEFAULT_DB = catalog_path()


def _furniture_fields(parser, required=False):
    parser.add_argument('--name', required=required)
    parser.add_argument('--description')
    parser.add_argument('--image-path')
    for key in ('length', 'width', 'height'):
        parser.add_argument('--'+key, type=float, help='metres; omit if unknown')
    parser.add_argument('--patch', help='game patch string, e.g. 7.2')
    parser.add_argument('--marketable', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--cash-shop', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--dyeable', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--dye-channels', type=int)
    parser.add_argument('--scope', choices=['interior','exterior'])


def build_parser():
    parser = argparse.ArgumentParser(description='FFXIV furniture catalog; JSON output, dimensions in metres')
    parser.add_argument('--db', default=str(DEFAULT_DB), help='SQLite file (default: project data/furniture.sqlite3)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='initialize empty database')
    p = sub.add_parser('furniture-add')
    p.add_argument('--id', required=True, type=int, help='FFXIV Item RowId')
    _furniture_fields(p, required=True)
    p = sub.add_parser('furniture-update')
    p.add_argument('id', type=int)
    _furniture_fields(p)
    p.add_argument('--clear', action='append', choices=['image_path','length','width','height','patch','marketable','cash_shop','dyeable','dye_channels','scope'], default=[], help='set field to NULL; repeatable')
    for command in ('furniture-get', 'furniture-delete', 'tag-delete'):
        p = sub.add_parser(command)
        p.add_argument('id', type=int)
    p = sub.add_parser('search')
    p.add_argument('--query', help='literal substring in name, description or tags')
    p.add_argument('--name')
    p.add_argument('--description')
    p.add_argument('--tag-id', type=int, action='append', default=[])
    p.add_argument('--tag-mode', choices=['all', 'any'], default='all')
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--offset', type=int, default=0)
    p.add_argument('--scope', choices=['interior','exterior'])
    p.add_argument('--marketable', action=argparse.BooleanOptionalAction, default=None)
    p.add_argument('--cash-shop', action=argparse.BooleanOptionalAction, default=None)
    p = sub.add_parser('tag-add')
    p.add_argument('--category', required=True)
    p.add_argument('--name', required=True)
    p = sub.add_parser('tag-update')
    p.add_argument('id', type=int)
    p.add_argument('--category')
    p.add_argument('--name')
    p = sub.add_parser('tag-list')
    p.add_argument('--category')
    for command in ('tag-attach', 'tag-detach'):
        p = sub.add_parser(command)
        p.add_argument('furniture_id', type=int)
        p.add_argument('tag_id', type=int)
        if command == 'tag-attach':
            p.add_argument('--source', default='manual')
            p.add_argument('--confidence', type=float)
    p = sub.add_parser('embed-index', help='refresh description vectors (optional dependencies)')
    p.add_argument('--batch-size', type=int, default=32)
    p.add_argument('--model', default='intfloat/multilingual-e5-small')
    p.add_argument('--model-cache', help='FastEmbed cache directory')
    p.add_argument('--local-files-only', action='store_true', help='never download model files')
    p = sub.add_parser('semantic-search', help='description semantic retrieval with hard filters')
    p.add_argument('--scope', choices=['interior','exterior'])
    p.add_argument('--query', required=True)
    p.add_argument('--top-k', type=int, default=10)
    p.add_argument('--tag-id', type=int, action='append', default=[])
    p.add_argument('--tag-mode', choices=['all', 'any'], default='all')
    p.add_argument('--marketable', action=argparse.BooleanOptionalAction, default=None)
    p.add_argument('--cash-shop', action=argparse.BooleanOptionalAction, default=None)
    p.add_argument('--model', default='intfloat/multilingual-e5-small')
    p.add_argument('--model-cache', help='FastEmbed cache directory')
    p.add_argument('--local-files-only', action='store_true')
    return parser


def main(argv=None):
    parser = build_parser()
    a = parser.parse_args(argv)
    try:
        with FurnitureDB(a.db) as db:
            command = a.command
            if command == 'init':
                result = {'database': str(Path(a.db).resolve()) if a.db != ':memory:' else ':memory:', 'schema_version': 4}
            elif command in ('furniture-add', 'furniture-update'):
                fields = {key: getattr(a, key) for key in
                          ('name','description','image_path','length','width','height','patch','marketable','cash_shop','dyeable','dye_channels','scope')
                          if getattr(a, key) is not None}
                if command == 'furniture-add':
                    result = db.add_furniture(a.id, **fields)
                else:
                    for key in a.clear:
                        if key in fields:
                            raise ValueError(f'Cannot set and clear {key} together')
                        fields[key] = None
                    result = db.update_furniture(a.id, **fields)
            elif command == 'furniture-get':
                result = db.get_furniture(a.id)
                if result is None:
                    raise KeyError(f'Furniture {a.id} not found')
            elif command == 'furniture-delete':
                result = {'deleted': db.delete_furniture(a.id)}
            elif command == 'search':
                result = db.search_furniture(query=a.query, name=a.name, description=a.description,
                    tag_ids=a.tag_id, tag_mode=a.tag_mode, limit=a.limit, offset=a.offset,
                    marketable=a.marketable, cash_shop=a.cash_shop, scope=a.scope)
            elif command in ('embed-index', 'semantic-search'):
                from .semantic import SemanticIndex
                index = SemanticIndex(db, model=a.model, cache_dir=a.model_cache,
                                      local_files_only=a.local_files_only)
                if command == 'embed-index':
                    result = index.refresh(batch_size=a.batch_size)
                else:
                    result = index.search(a.query, top_k=a.top_k, tag_ids=a.tag_id,
                                          tag_mode=a.tag_mode, marketable=a.marketable,
                                          cash_shop=a.cash_shop, scope=a.scope)
            elif command == 'tag-add':
                result = db.add_tag(a.category, a.name)
            elif command == 'tag-update':
                fields = {k: getattr(a,k) for k in ('name','category') if getattr(a,k) is not None}
                result = db.update_tag(a.id, **fields)
            elif command == 'tag-list':
                result = db.list_tags(a.category)
            elif command == 'tag-delete':
                result = {'deleted': db.delete_tag(a.id)}
            elif command == 'tag-attach':
                result = db.add_furniture_tag(a.furniture_id, a.tag_id, source=a.source, confidence=a.confidence)
            elif command == 'tag-detach':
                result = {'removed': db.remove_furniture_tag(a.furniture_id, a.tag_id)}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, KeyError, sqlite3.Error, OSError, RuntimeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
