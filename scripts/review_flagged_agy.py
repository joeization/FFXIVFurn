"""Second review of the 24 still-flagged images with agy Gemini Flash (advisory only; no catalog writes)."""
from pathlib import Path
import json, subprocess, sys, hashlib, re, concurrent.futures as cf
ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'runs/round1/finalization/agy-flash-review'
MODEL = 'gemini-3.8-flash-medium'
BATCH = 6


def load(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8'))


def main():
    W.mkdir(exist_ok=True)
    (W / 'requests').mkdir(exist_ok=True); (W / 'responses').mkdir(exist_ok=True)
    rep = load('runs/round1/finalization/qwen-flagged-review/report.json')
    aud = load('runs/round1/finalization/tag-audit/report.json')
    vocab = load('runs/round1/finalization/frozen-vocab.json')
    accepted = {c['key']: c['definition'] for c in vocab['concepts'] if c['status'] == 'accepted'}
    meta = {}
    for it in aud['needs_review']:
        meta.setdefault(it['image_hash'], []).append(it)
    hashes = sorted(c['image_hash'] for c in rep['changes'] if c['still_flagged'])
    assert len(hashes) == 24, len(hashes)
    vocab_text = '\n'.join(f'{k}: {d[:90]}' for k, d in sorted(accepted.items()))
    (W / 'vocab.txt').write_text(vocab_text, encoding='utf-8')
    batches = [hashes[i:i + BATCH] for i in range(0, len(hashes), BATCH)]

    def run(bi, hs):
        out = W / 'responses' / f'batch{bi}.json'
        if out.exists():
            return bi, 'cached'
        items = []
        for j, h in enumerate(hs):
            m = meta[h]
            items.append({'id': f'F{bi}{j}', 'image_path': m[0]['image_path'],
                          'sources': [{'name': x['name'], 'source_category': x['source_category'], 'scope': x['scope']} for x in m]})
        prompt = f"""Task: tag FFXIV housing furniture thumbnails. For each item below, open the PNG at image_path with your file-read tool and look at it.
Source name/category/scope are trusted metadata; do not contradict them from a vague thumbnail, but a depicted/toy object may legitimately differ. Do NOT run shell commands; use only the file-view/read tool (for the PNGs and for the vocabulary text file {W / 'vocab.txt'}, format 'key: definition'; read all of it). Use ONLY keys from that vocabulary.
 Pick 3-8 tags that are clearly visible. No new tags. List doubts in 'uncertain'.
Items: {json.dumps(items, ensure_ascii=False)}
Final answer: ONLY a JSON array, one object per item: {{"id":..,"tags":[{{"key":..,"confidence":0-1,"evidence":".."}}],"uncertain":[".."],"visual_description":".."}}. No markdown fence."""
        (W / 'requests' / f'batch{bi}.txt').write_text(prompt, encoding='utf-8')
        r = subprocess.run(['agy', '-p', prompt, '--model', MODEL, '--output-format', 'json', '--print-timeout', '600s',
                            '--add-dir', str(ROOT / 'data/thumbnails')], cwd=ROOT, capture_output=True, text=True, timeout=700, encoding='utf-8')
        (W / 'responses' / f'batch{bi}.raw.json').write_text(r.stdout + '\n---STDERR---\n' + r.stderr, encoding='utf-8')
        try:
            raw = json.loads(r.stdout)
            text = (raw.get('response') or raw.get('result') or '').strip()
            text = re.sub(r'^```(?:json)?|```$', '', text).strip()
            arr = json.loads(text)
            ids = [i['id'] for i in items]
            assert [a['id'] for a in arr] == ids, 'ids mismatch'
        except Exception as e:
            return bi, f'parse-fail {e!r}'
        bad = [t['key'] for a in arr for t in a.get('tags', []) if t['key'] not in accepted]
        if bad:
            return bi, f'invalid keys {bad}'
        for a, h in zip(arr, hs):
            a['image_hash'] = h
        out.write_text(json.dumps(arr, ensure_ascii=False, indent=1), encoding='utf-8')
        return bi, 'ok'

    with cf.ThreadPoolExecutor(2) as ex:
        for bi, st in ex.map(lambda a: run(*a), enumerate(batches)):
            print(bi, st, flush=True)
    res = {}
    for p in sorted((W / 'responses').glob('batch?.json')):
        for a in json.loads(p.read_text(encoding='utf-8')):
            res[a['image_hash']] = a
    (W / 'agy-flash-predictions.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    print('collected', len(res), 'of 24')


if __name__ == '__main__':
    main()
