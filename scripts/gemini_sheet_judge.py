"""Read-only image judging via one numbered contact sheet per Gemini call.

Input JSON: [{"id": ..., "image_path": ..., ...caller context...}].
Example: python scripts/gemini_sheet_judge.py --items items.json --task forms-v1
  --question-file question.txt --vocabulary vocab.json --output results.json
  --cache-dir path/to/cache
No database module is imported or database connection opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageDraw, ImageFont, ImageOps


def render_sheet(items, output, *, columns=4, cell_size=320):
    if not items or columns < 1 or cell_size < 64:
        raise ValueError('nonempty items, positive columns and cell_size >=64 required')
    height = cell_size + 32
    sheet = Image.new('RGB', (columns * cell_size, math.ceil(len(items) / columns) * height), '#eeeeee')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=22)
    layout = []
    for index, item in enumerate(items):
        x, y = (index % columns) * cell_size, (index // columns) * height
        with Image.open(item['image_path']) as original:
            image = ImageOps.contain(original.convert('RGBA'), (cell_size - 12, cell_size - 12))
            sheet.paste(image, (x + (cell_size-image.width)//2, y + 32 + (cell_size-image.height)//2), image)
        draw.rectangle((x, y, x+cell_size-1, y+height-1), outline='#777777')
        draw.text((x+8, y+3), f'{index+1} | ID {item["id"]}', fill='black', font=font)
        layout.append(dict(cell=index+1, id=item['id']))
    sheet.save(output)
    return layout


def parse_response(text, count):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    value = json.loads(text)
    if not isinstance(value, list) or any(not isinstance(r, dict) or type(r.get('cell')) is not int for r in value):
        raise ValueError('Expected array of objects with integer cell numbers')
    if len(value) != count or {r['cell'] for r in value} != set(range(1, count+1)):
        raise ValueError('Missing, duplicate, or unexpected cell numbers')
    return sorted(value, key=lambda r: r['cell'])


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def judge(items, *, task, question, vocabulary, cache_dir, batch_size=16, retries=2,
          model='gemini-3.8-flash-medium', timeout=540):
    if not 1 <= batch_size <= 20 or retries < 0:
        raise ValueError('batch size must be 1..20 and retries nonnegative')
    if len({str(i['id']) for i in items}) != len(items):
        raise ValueError('Duplicate item ids')
    root = Path(cache_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    signature = hashlib.sha256(json.dumps([task, question, vocabulary, model], sort_keys=True).encode()).hexdigest()
    pending, results = [], {}
    for item in items:
        image_hash = hashlib.sha256(Path(item['image_path']).read_bytes()).hexdigest()
        key = hashlib.sha256(json.dumps([item['id'], task, signature, item, image_hash], sort_keys=True).encode()).hexdigest()
        path = root / (key + '.json')
        if path.exists():
            results[str(item['id'])] = json.loads(path.read_text(encoding='utf-8'))
        else:
            pending.append((item, path))
    executable = shutil.which('agy')
    if pending and not executable:
        raise RuntimeError('agy executable not found')
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start+batch_size]
        rows = [row for row, _ in batch]
        batch_key = hashlib.sha256(''.join(p.stem for _, p in batch).encode()).hexdigest()[:20]
        sheet = root / f'{batch_key}.png'
        render_sheet(rows, sheet)
        context = root / f'{batch_key}-prompt.json'
        atomic_json(context, dict(question=question, allowed_vocabulary=vocabulary,
            items=[dict(cell=i+1, **row) for i, row in enumerate(rows)],
            instructions='Return ONLY a JSON array with exactly one object per cell, each with integer cell plus the fields requested in question. Use only allowed vocabulary when assigning tags.'))
        prompt = f'Read {context.as_posix()} and image {sheet.as_posix()} using your file-read tool. Do NOT run shell commands (they are denied). Inspect the ONE contact sheet; do not read individual image files. Follow the question and return JSON only.'
        assert executable is not None
        for attempt in range(retries+1):
            began = time.perf_counter()
            try:
                process = subprocess.run([executable, '-p', prompt, '--add-dir', str(root), '--model', model,
                    '--output-format', 'json', '--print-timeout', f'{timeout}s'], capture_output=True, text=True,
                    encoding='utf-8', timeout=timeout+30)
                atomic_json(root / f'{batch_key}-attempt-{attempt}.json', dict(stdout=process.stdout, stderr=process.stderr,
                    returncode=process.returncode, seconds=time.perf_counter()-began))
                if process.returncode:
                    raise RuntimeError(f'agy exit {process.returncode}: {process.stderr[:400]}')
                envelope = json.loads(process.stdout)
                answers = parse_response(envelope.get('response', ''), len(rows))
                for (item, path), answer in zip(batch, answers, strict=True):
                    record = dict(id=item['id'], task=task, answer=answer, sheet=str(sheet),
                        seconds_per_item=(time.perf_counter()-began)/len(rows))
                    atomic_json(path, record)
                    results[str(item['id'])] = record
                break
            except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                atomic_json(root / f'{batch_key}-error-{attempt}.json', dict(error=str(exc)))
                if attempt == retries:
                    raise RuntimeError(f'Failed sheet {sheet}: {exc}') from exc
                time.sleep(2 ** attempt)
    return [results[str(item['id'])] for item in items]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--items', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--question-file', required=True)
    parser.add_argument('--vocabulary')
    parser.add_argument('--output', required=True)
    parser.add_argument('--cache-dir', required=True)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=540)
    parser.add_argument('--model', default='gemini-3.8-flash-medium')
    args = parser.parse_args()
    read = lambda path: Path(path).read_text(encoding='utf-8')
    results = judge(json.loads(read(args.items)), task=args.task, question=read(args.question_file),
        vocabulary=json.loads(read(args.vocabulary)) if args.vocabulary else [], cache_dir=args.cache_dir,
        batch_size=args.batch_size, retries=args.retries, timeout=args.timeout, model=args.model)
    atomic_json(args.output, results)
    print(json.dumps(dict(items=len(results), output=args.output)))


if __name__ == '__main__':
    main()
