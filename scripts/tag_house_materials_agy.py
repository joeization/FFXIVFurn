"""Tag HouseAssets building materials with agy Gemini Flash (frozen vocab only; advisory, resumable, raw preserved).

Names are inferred from folder names (not game strings). Tags that don't fit the frozen vocab go to `proposed`, never to tags.
"""
from pathlib import Path
import json, subprocess, concurrent.futures as cf, re, hashlib
ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'runs/round1/house-materials-agy'
MODEL = 'gemini-3.8-flash-medium'; BATCH = 8; ATTEMPTS = 2


def main():
    (W / 'responses').mkdir(parents=True, exist_ok=True); (W / 'requests').mkdir(exist_ok=True)
    vocab = json.loads((ROOT / 'runs/round1/finalization/frozen-vocab.json').read_text(encoding='utf-8'))
    accepted = {c['key']: c['definition'] for c in vocab['concepts'] if c['status'] == 'accepted'}
    vfile = W / 'vocab.txt'; vfile.write_text('\n'.join(f'{k}: {d[:90]}' for k, d in sorted(accepted.items())), encoding='utf-8')
    rows = sorted(json.loads((ROOT / 'data/house-material-images/manifest.json').read_text(encoding='utf-8'))['images'], key=lambda r: r['asset_key'])
    batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]

    def run(bi, rs):
        out = W / 'responses' / f'batch{bi:03d}.json'
        if out.exists(): return bi, 'cached'
        items = [{'id': f'H{bi:03d}{j}', 'image_path': r['image_path'], 'slot': r['slot'], 'scope': r['scope'], 'name_guess': r['name'], 'image_kind': r['image_kind']} for j, r in enumerate(rs)]
        prompt = f"""Task: tag FFXIV housing BUILDING MATERIALS (wallpaper, flooring, ceiling lights, exterior walls, roofs, fences, doors, windows etc.) from preview images. For each item open the PNG at image_path with your file-read tool and look at it. image_kind 'albedo-texture' means the image is just the surface texture tile (describe colour/material/pattern); 'thumbnail' is an icon of the piece.
name_guess and slot/scope are trusted metadata derived from the folder name. Do NOT run shell commands; use only the file-read tool (for the PNGs and for the vocabulary file {vfile}, lines 'key: definition'; read all of it). Use ONLY keys from that vocabulary in "tags" (3-8 clearly visible ones). If an important visible property has no fitting key, list it as free text in "proposed" (these are NOT tags). Doubts go in "uncertain".
Items: {json.dumps(items, ensure_ascii=False)}
Final answer: ONLY a JSON array, one object per item, same order: {{"id":..,"tags":[{{"key":..,"confidence":0-1,"evidence":".."}}],"proposed":[".."],"uncertain":[".."],"visual_description":".."}}. No markdown fence."""
        (W / 'requests' / f'batch{bi:03d}.txt').write_text(prompt, encoding='utf-8')
        err = ''
        for attempt in range(ATTEMPTS):
            r = subprocess.run(['agy', '-p', prompt, '--model', MODEL, '--output-format', 'json', '--print-timeout', '600s', '--add-dir', str(ROOT / 'data/house-material-images')],
                               cwd=ROOT, capture_output=True, text=True, timeout=700, encoding='utf-8')
            (W / 'responses' / f'batch{bi:03d}.attempt{attempt}.raw.json').write_text(r.stdout + '\n---STDERR---\n' + r.stderr, encoding='utf-8')
            try:
                text = (json.loads(r.stdout).get('response') or '').strip()
                text = re.sub(r'^```(?:json)?|```$', '', text).strip(); arr = json.loads(text)
                assert [a['id'] for a in arr] == [i['id'] for i in items], 'ids mismatch'
                bad = [t['key'] for a in arr for t in a.get('tags', []) if t['key'] not in accepted]
                assert not bad, f'invalid keys {bad}'
                for a, row in zip(arr, rs): a['asset_key'] = row['asset_key']; a['image_sha256'] = row['image_sha256']
                out.write_text(json.dumps(arr, ensure_ascii=False, indent=1), encoding='utf-8'); return bi, 'ok'
            except Exception as e:
                err = repr(e)[:200]
        return bi, 'FAILED ' + err

    with cf.ThreadPoolExecutor(2) as ex:
        for bi, st in ex.map(lambda a: run(*a), enumerate(batches)): print(bi, st, flush=True)
    res = {}
    for p in sorted((W / 'responses').glob('batch???.json')):
        for a in json.loads(p.read_text(encoding='utf-8')): res[a['asset_key']] = a
    (W / 'predictions.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    print('collected', len(res), 'of', len(rows), 'vocab_sha256', hashlib.sha256(vfile.read_bytes()).hexdigest()[:12])


if __name__ == '__main__': main()
