"""Validate and snapshot input without assuming assets are placeable items."""
import hashlib
import json
from pathlib import Path
from PIL import Image
from .state import connect, digest, read_json, write_json


def prepare(manifest, run_dir):
    rows, keys, item_ids = [], set(), set()
    source = Path(manifest)
    for number, line in enumerate(source.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        for key in ('asset_key', 'source_category', 'scope', 'image_path'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f'Line {number}: missing/invalid {key}')
        if row['asset_key'] in keys:
            raise ValueError(f'Duplicate asset_key at line {number}')
        keys.add(row['asset_key'])
        item_id = row.get('item_id')
        if item_id is not None:
            if type(item_id) is not int or item_id <= 0 or item_id in item_ids:
                raise ValueError(f'Invalid/duplicate item_id at line {number}')
            item_ids.add(item_id)
        path = Path(row['image_path'])
        if not path.is_absolute():
            raise ValueError(f'Line {number}: image_path must be absolute')
        data = path.read_bytes()
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.format not in ('PNG', 'JPEG', 'WEBP', 'GIF'):
                raise ValueError(f'Unsupported image format: {image.format}')
            mime = Image.MIME[image.format]
            size = list(image.size)
        rows.append({**row, 'item_id': item_id, 'image_hash': hashlib.sha256(data).hexdigest(),
                     'mime_type': mime, 'image_size': size, 'record_hash': digest(row)})
    if not rows:
        raise ValueError('Empty manifest')
    rows.sort(key=lambda row: row['asset_key'])
    snapshot = {'schema_version': 1, 'manifest_hash': digest(rows), 'assets': rows,
                'staging_only': True, 'source_manifest': str(source.resolve())}
    target = Path(run_dir) / 'manifest.json'
    if target.exists():
        old = read_json(target)
        if old['manifest_hash'] != snapshot['manifest_hash']:
            raise ValueError('Run already has a different manifest; use a new run directory')
    else:
        write_json(target, snapshot)
    connect(run_dir).close()
    return {'assets': len(rows), 'unique_images': len({r['image_hash'] for r in rows}),
            'manifest_hash': snapshot['manifest_hash'], 'staging_only': True}
