"""Summarize existing native Base textures; no extraction, network or LLM calls.

Uses the render pipeline's Assets.load and default-dye mapping. One vote per
eligible pixel per unique used material texture (not projected mesh area).
Alpha-zero and near-black (max RGB <= 8/255) pixels are excluded. Dyes are
baked by Assets exactly as in the renderer; its dye mask becomes opaque.
K-means uses a full-count 5-bit RGB histogram, linear-light centres, three
clusters and deterministic weighted farthest-point initialization. Fractions
are normalized over retained pixels. Mean HSV is computed from histogram
means, with saturation-weighted circular hue. No display gamma is applied.
"""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
import argparse
import colorsys
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from ffxiv_furniture.rendering.assets import Assets, _lin, _srgb

COLUMNS = ('c1_hex', 'c1_frac', 'c2_hex', 'c2_frac', 'c3_hex', 'c3_frac',
           'hue_name', 'mean_h', 'mean_s', 'mean_v')
SCHEMA = '''CREATE TABLE IF NOT EXISTS item_colors(
    item_id INTEGER PRIMARY KEY, c1_hex TEXT, c1_frac REAL,
    c2_hex TEXT, c2_frac REAL, c3_hex TEXT, c3_frac REAL,
    hue_name TEXT, mean_h REAL, mean_s REAL, mean_v REAL)'''


def hue_name(rgb):
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    if v < .10:
        return 'black'
    if s < .13:
        return 'white' if v >= .80 else 'grey'
    degrees = h * 360
    if 15 <= degrees < 70 and v < .68:
        return 'brown'
    if degrees < 15 or degrees >= 345:
        return 'red'
    for boundary, name in ((45, 'orange'), (70, 'yellow'), (165, 'green'),
                           (195, 'cyan'), (255, 'blue'), (290, 'purple'), (345, 'pink')):
        if degrees < boundary:
            return name
    return 'red'


def summarize_textures(textures):
    result = dict.fromkeys(COLUMNS)
    counts = np.zeros(32768, dtype=np.float64)
    sums = np.zeros((32768, 3), dtype=np.float64)
    for texture in textures:
        rgba = np.asarray(texture, dtype=np.uint8).reshape(-1, 4)
        # Bounded chunks avoid copying entire multi-megapixel textures at once.
        for offset in range(0, len(rgba), 262144):
            part = rgba[offset:offset+262144]
            rgb = part[(part[:, 3] > 0) & (part[:, :3].max(axis=1) > 8), :3]
            if not len(rgb):
                continue
            q = rgb.astype(np.int32) >> 3
            bins = (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
            counts += np.bincount(bins, minlength=32768)
            for channel in range(3):
                sums[:, channel] += np.bincount(bins, weights=rgb[:, channel], minlength=32768)
    mask = counts > 0
    weights = counts[mask]
    if not len(weights):
        return result
    srgb = sums[mask] / weights[:, None] / 255
    points = _lin(srgb)
    centres = [points[np.argmax(weights)]]
    for _ in range(min(3, len(points))-1):
        distances = ((points[:, None, :] - np.array(centres)[None, :, :])**2).sum(axis=2).min(axis=1)
        index = np.argmax(distances * weights)
        if distances[index] < 1e-14:
            break
        centres.append(points[index])
    centres = np.array(centres)
    for _ in range(40):
        labels = ((points[:, None, :] - centres[None, :, :])**2).sum(axis=2).argmin(axis=1)
        updated = centres.copy()
        for i in range(len(centres)):
            selected = labels == i
            if selected.any():
                updated[i] = np.average(points[selected], weights=weights[selected], axis=0)
        if np.max(abs(updated-centres)) < 1e-7:
            centres = updated
            break
        centres = updated
    labels = ((points[:, None, :] - centres[None, :, :])**2).sum(axis=2).argmin(axis=1)
    masses = np.bincount(labels, weights=weights, minlength=len(centres))
    order = sorted(range(len(centres)), key=lambda i: (-masses[i], i))
    main = None
    for slot, i in enumerate((i for i in order if masses[i] > 0), 1):
        rgb = np.clip(_srgb(centres[i]), 0, 1)
        if main is None:
            main = rgb
        result[f'c{slot}_hex'] = '#' + ''.join(f'{int(c):02x}' for c in np.floor(rgb*255+.5))
        result[f'c{slot}_frac'] = float(masses[i]/weights.sum())
    hsv = np.array([colorsys.rgb_to_hsv(*c) for c in srgb])
    angles = hsv[:, 0]*2*np.pi
    hue_weights = weights*hsv[:, 1]
    mean_h = np.arctan2(np.sum(np.sin(angles)*hue_weights), np.sum(np.cos(angles)*hue_weights))/(2*np.pi) % 1.
    result.update(hue_name=hue_name(main), mean_h=float(mean_h),
                  mean_s=float(np.average(hsv[:, 1], weights=weights)),
                  mean_v=float(np.average(hsv[:, 2], weights=weights)))
    return result


_ASSETS = None


def init_worker(dyes):
    global _ASSETS
    _ASSETS = Assets([], ROOT/'outputs/render-pipeline/cache', dyes=dyes)


def process_item(task):
    iid, evidence = task
    if evidence is None:
        return iid, dict.fromkeys(COLUMNS), ['No measured geometry'], 'no_geometry'
    try:
        record = json.loads(evidence)
        record['item_id'] = iid
        _ASSETS.records = {iid: record}
        mesh = _ASSETS.load(iid)
        used = {g['material_index'] for g in mesh['groups'] if g['triangle_count'] > 0 and g['material_index'] >= 0}
        textures, seen, warnings = [], set(), []
        for index in sorted(used):
            mat = mesh['materials'][index]
            if mat.get('warning'):
                warnings.append(mat['warning'])
            if mat['texture'] is None:
                continue
            key = (mat.get('texture_cache'), tuple(mat.get('dyed_with') or []))
            if key not in seen:
                seen.add(key)
                textures.append(mat['texture'])
        summary = summarize_textures(textures)
        warnings.extend(_ASSETS.coverage[-1]['notes'])
        return iid, summary, warnings, 'colored' if summary['c1_hex'] else 'no_eligible_texture'
    except Exception as error:
        return iid, dict.fromkeys(COLUMNS), [f'{type(error).__name__}: {error}'], 'failed'
    finally:
        _ASSETS.loaded.clear()
        _ASSETS.coverage.clear()
        _ASSETS.records.clear()


def validate(db, expected):
    count = db.execute('SELECT COUNT(*) FROM item_colors').fetchone()[0]
    covered = db.execute('SELECT COUNT(*) FROM furniture f JOIN item_colors c ON c.item_id=f.id').fetchone()[0]
    assert count == covered == expected, (count, covered, expected)
    rows = db.execute('SELECT c1_hex,c1_frac,c2_frac,c3_frac,mean_h,mean_s,mean_v FROM item_colors').fetchall()
    for c1, f1, f2, f3, h, s, v in rows:
        if c1:
            assert abs(sum(x or 0 for x in (f1, f2, f3))-1) < 1e-8
            assert all(0 <= x <= 1 for x in (h, s, v))
        else:
            assert all(x is None for x in (f1, f2, f3, h, s, v))
    distribution = dict(db.execute('SELECT coalesce(hue_name,\'NULL\'),count(*) FROM item_colors GROUP BY hue_name ORDER BY count(*) DESC'))
    print('hue_name distribution:', json.dumps(distribution), flush=True)
    checks = []
    for term in ('Crimson', 'Ivory', 'Jade', 'Oak'):
        checks.extend(db.execute('SELECT f.id,f.name,c.hue_name,c.c1_hex,c.c1_frac FROM furniture f JOIN item_colors c ON c.item_id=f.id WHERE f.name LIKE ? ORDER BY f.id LIMIT 3', ('%'+term+'%',)).fetchall())
    seen = {r[0] for r in checks}
    if len(checks) < 10:
        checks.extend(r for r in db.execute('SELECT f.id,f.name,c.hue_name,c.c1_hex,c.c1_frac FROM furniture f JOIN item_colors c ON c.item_id=f.id ORDER BY f.id') if r[0] not in seen)
    checks = checks[:10]
    print('10 name/colour spot checks:', json.dumps(checks, ensure_ascii=True), flush=True)
    return distribution, checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT/'data/furniture.sqlite3')
    parser.add_argument('--workers', type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be positive')
    start = time.monotonic()
    db_path = args.db.resolve()
    if not db_path.is_file():
        parser.error(f'Database does not exist: {db_path}')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = ROOT/'data/backups'/f'pre-item-colors-{stamp}.sqlite3'
    backup.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as db:
        with closing(sqlite3.connect(backup)) as target:
            db.backup(target)
        tasks = db.execute('SELECT f.id,g.evidence FROM furniture f LEFT JOIN asset_geometry g ON g.item_id=f.id ORDER BY f.id').fetchall()
        with (ROOT/'data/external/Stain.csv').open(encoding='utf-8') as handle:
            stains = {r['Name']: tuple((int(r['Color']) >> shift) & 255 for shift in (16, 8, 0)) for r in csv.DictReader(handle) if r['Color'] != '0'}
        dyes = {iid: stains[name] for iid, name in db.execute('SELECT item_id,dye_name FROM item_default_dye') if name in stains}
    print(f'Backup: {backup}\nProcessing {len(tasks)} furniture items with {args.workers} workers', flush=True)
    results, stats, warnings = [], Counter(), []
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker, initargs=(dyes,)) as pool:
        for n, (iid, summary, notes, status) in enumerate(pool.map(process_item, tasks, chunksize=1), 1):
            results.append((iid, *(summary[k] for k in COLUMNS)))
            stats[status] += 1
            if notes:
                warnings.append({'item_id': iid, 'status': status, 'warnings': notes})
            if n % 50 == 0 or n == len(tasks):
                print(f'{n}/{len(tasks)} {dict(stats)} elapsed={time.monotonic()-start:.1f}s', flush=True)
    # Only this new table is written, in one transaction after all workers finish.
    with closing(sqlite3.connect(db_path)) as db:
        with db:
            db.execute(SCHEMA)
            db.executemany('INSERT OR REPLACE INTO item_colors VALUES(?,?,?,?,?,?,?,?,?,?,?)', results)
        distribution, checks = validate(db, len(tasks))
    report = {'backup': str(backup), 'database': str(db_path), 'total': len(tasks), 'counts': dict(stats),
              'distribution': distribution, 'spot_checks': checks, 'issues': warnings,
              'elapsed_seconds': round(time.monotonic()-start, 2), 'model_calls': 0}
    report_path = ROOT/'data/backups'/f'item-colors-report-{stamp}.json'
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    print(f'Verified {len(results)} rows. Counts: {dict(stats)}\nReport: {report_path}', flush=True)


if __name__ == '__main__':
    main()
