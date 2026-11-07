"""Independent model review of a deco round's render sheets through the `agy` CLI (file protocol: the model reads the JPEG/PNG sheets itself).

  python scripts/review_deco.py <round-dir> --program-file program.txt --models <model-a>,<model-b> [--runs 1]

Models come from --models or $DECO_REVIEW_MODELS (comma-separated agy model ids); there is no built-in default. Use reviewers that
passed a planted-defect benchmark (DESIGN_CONTEXT 9.6), preferably two different ones.

The reviewer gets ONLY: the owner's program (what was asked for), the renderer's real limits, and a fixed checklist.
The orchestrating agent cannot tell the reviewer what the design achieves: program text that claims results, verification or
pre-excuses ("already verified", "intentionally empty", "do not flag", "faces it") is rejected (lint), because such prompts turned a
broken design into an "ok" verdict (the same sheets scored 3/10 'revise' in 4/4 runs once the claims were removed).
Every round is a fresh review (no "was your previous issue fixed?" checklist, which converges to ok). Verdict ok only if EVERY run
returns ok; issues raised by a single run are hints to verify against geometry. Writes review-reply.json into the round dir (prompt, raw output and
per-run JSON are removed afterwards unless --keep-artifacts or a parse failure); exit code 0 = ok, 1 = revise. Applies nothing itself.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

RENDER_LIMITS = ("Approximate lighting without shadows or reflections; native windows show no outdoor view; book spines are baked "
                 "textures; water and particle effects are not drawn. These are preview-tool limits, not design faults.")
CONVENTIONS = ("Every image is mirrored left-right to match the in-app camera, so compass words in panel titles (north, east...) do not map to "
               "image left/right. A set item (a stepping-stone set, a rug, a paired lantern piece) counts as one item toward any item limit.")
CHECKLIST = """For every panel check:
1. Can each door / doorway actually be walked through, or is it filled or blocked by furniture or partitions?
2. Does any furniture intersect other furniture or walls, float, or sit on nothing?
3. Do seats face their table / focal point / conversation partner? Do storage and work fronts face where they are used?
4. Do the entrance, stair arrival and main paths (and a yard path from gate to door, if shown) line up and stay clear?
5. Does each requested function exist and read clearly (focal points visible, fixtures usable, storage reachable)?
6. Overall: emptiness vs clutter, grouping, coherence with the requested style."""
REPLY = ('Reply with ONLY a JSON object: {"verdict": "ok" | "revise", "score": <1-10 overall>, '
         '"issues": [{"panel": "<sheet + panel position>", "problem": "...", "fix": "concrete instruction", "severity": "must|should|nit"}], '
         '"requested_functions_missing_or_broken": ["..."]}. verdict ok only if there is no must issue. Max 10 issues, worst first. '
         'Report only what you can see; do not demand items that do not exist in FFXIV.')
CLAIM_PATTERNS = [r'\bverif', r'\balready\b', r'\bintentional', r'\bdeliberate', r"\bdo(?:n't| not) (?:flag|mention|report|penali[sz]e)",
                  r'\bfacts?\b', r'\bdeclared\b', r'\bnot (?:unfinished|a bug|an error|a mistake)', r'\bkept clear\b', r'\bfaces? (?:it|the)\b',
                  r'\bpassed\b', r'\bapproved\b', r'\bconfirmed\b', r'\bfixed\b']



SHEET_SUFFIXES = ('.jpg', '.jpeg', '.png')


def find_sheets(round_dir):
    """Render sheets in a round dir (JPEG is the normal format; PNG kept for older rounds), sorted by name."""
    return sorted(p.name for p in Path(round_dir).iterdir() if p.is_file() and p.suffix.lower() in SHEET_SUFFIXES)

def lint_program(text):
    """Lines of the program that claim results/verification or pre-excuse defects (the reviewer must find those itself)."""
    return [(i + 1, line.strip(), pat) for i, line in enumerate(text.splitlines()) for pat in CLAIM_PATTERNS if re.search(pat, line, re.I)]


def build_prompt(program, sheets):
    return ("You are an independent reviewer of an FFXIV housing design shown as native preview renders. Nothing has been verified "
            "for you: check everything yourself from the pixels.\n\nWHAT THE OWNER ASKED FOR (program, not a description of the result; "
            "do not assume any of it exists or works):\n" + program.strip() + "\n\nRENDER LIMITS: " + RENDER_LIMITS + "\n\nVIEW AND COUNTING CONVENTIONS: " + CONVENTIONS + "\n\n" + CHECKLIST +
            "\n\nSheets in this folder (read every one fully): " + ", ".join(sheets) + "\n\n" + REPLY)


def aggregate(runs):
    valid = [r for r in runs if isinstance(r, dict) and 'verdict' in r]
    must = [sum(i.get('severity') == 'must' for i in r.get('issues', [])) for r in valid]
    ok = bool(valid) and len(valid) == len(runs) and all(r['verdict'] == 'ok' and m == 0 for r, m in zip(valid, must))
    return {'verdict': 'ok' if ok else 'revise', 'runs': len(runs), 'valid_runs': len(valid), 'must_per_run': must,
            'scores': [r.get('score') for r in valid],
            'note': 'ok requires every run to be ok with no must issue; single-run issues are hints to verify against geometry'}


def cleanup_round(round_dir, runs, keep_artifacts=False):
    """After review-reply.json is written, delete the round's intermediates (prompt, raw agy output, per-run JSON): the reply
    already holds every verdict, score and issue. Kept when keep_artifacts is set or any run failed to parse (evidence)."""
    if keep_artifacts or any(r.get('parse_error') for r in runs):
        return []
    removed = []
    for p in Path(round_dir).iterdir():
        if p.is_file() and (p.name == 'review-prompt.txt' or p.name.startswith(('review-raw-', 'review-run-'))):
            p.unlink(); removed.append(p.name)
    return removed


def run_jobs(jobs, call, staged=False):
    """Run review jobs [(model, k)]. Parallel by default. staged=True runs them in order and stops at the first run that is not
    'ok' (revise or unparseable): the round already needs revision, so later reviewers would cost quota without changing the verdict.
    An ok run never ends a staged round early; the next model must confirm it. Returns (runs, skipped_jobs)."""
    if not staged:
        with ThreadPoolExecutor(max(1, len(jobs))) as ex:
            results = list(ex.map(call, jobs))
        return [dict(r, _model=m, _run=k) for (m, k), r in zip(jobs, results)], []
    runs = []
    for i, (m, k) in enumerate(jobs):
        r = dict(call((m, k)), _model=m, _run=k); runs.append(r)
        if r.get('parse_error') or r.get('verdict') != 'ok' or any(x.get('severity') == 'must' for x in r.get('issues', [])):
            return runs, jobs[i + 1:]
    return runs, []


def _call(model, short, round_dir, timeout, raw_path):
    exe = shutil.which('agy')
    if not exe: raise SystemExit('agy CLI not found')
    r = subprocess.run([exe, '-p', short, '--add-dir', str(round_dir), '--model', model, '--output-format', 'json',
                        '--print-timeout', f'{timeout - 30}s'], capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    raw_path.write_text(r.stdout + '\n---STDERR---\n' + r.stderr, encoding='utf-8')
    try:
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', (json.loads(r.stdout).get('response') or '').strip()).strip()
        return json.loads(re.search(r'\{.*\}', text, re.S).group(0))
    except Exception:
        return {'parse_error': (r.stdout + r.stderr)[:2000]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('round_dir', type=Path)
    ap.add_argument('--program-file', '--brief-file', dest='program_file', type=Path, required=True,
                    help="owner's program: requested functions, users, style; NOT claims about the result")
    ap.add_argument('--models', default=os.environ.get('DECO_REVIEW_MODELS'), help='comma-separated agy model ids (default: $DECO_REVIEW_MODELS)')
    ap.add_argument('--runs', type=int, default=1, help='runs per model')
    ap.add_argument('--timeout', type=int, default=540)
    ap.add_argument('--dry-run', action='store_true', help='lint and write the prompt only')
    ap.add_argument('--keep-artifacts', action='store_true', help='keep the prompt, raw agy output and per-run JSON (default: only '
                    'review-reply.json is kept unless a run failed to parse)')
    ap.add_argument('--staged', action='store_true', help='run models in the given order and stop at the first non-ok run '
                    '(acceptance still needs every run ok, so an ok first run is always confirmed by the next model)')
    a = ap.parse_args(argv)
    rd = a.round_dir.resolve(); sheets = find_sheets(rd)
    if not sheets: raise SystemExit('no render sheets (*.jpg/*.jpeg/*.png) in round dir')
    program = a.program_file.read_text(encoding='utf-8')
    bad = lint_program(program)
    if bad:
        for n, line, pat in bad: print(f'program line {n} claims a result or pre-excuses a defect ({pat}): {line[:120]}', file=sys.stderr)
        raise SystemExit('rewrite the program as what was ASKED FOR; the reviewer must judge what was achieved')
    prompt = build_prompt(program, sheets); (rd / 'review-prompt.txt').write_text(prompt, encoding='utf-8')
    if a.dry_run: print(prompt); return 0
    if not a.models: raise SystemExit('set --models or DECO_REVIEW_MODELS to the benchmarked reviewer model ids')
    short = (f"Read {rd / 'review-prompt.txt'} with your file-read tool, then read every image it lists from {rd} with the file-read "
             "tool (do not run shell commands). Follow it exactly and reply with ONLY the JSON object.")
    jobs = [(m.strip(), k) for m in a.models.split(',') if m.strip() for k in range(1, a.runs + 1)]
    runs, skipped = run_jobs(jobs, lambda j: _call(j[0], short, rd, a.timeout, rd / f'review-raw-{j[0]}-{j[1]}.json'), a.staged)
    for r in runs:
        (rd / f"review-run-{r['_model']}-{r['_run']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8')
    reply = {**aggregate(runs), 'skipped_after_revise': [f'{m}-{k}' for m, k in skipped], 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'sheets': sheets,
             'issues_by_run': [{'model': r['_model'], 'run': r['_run'], 'verdict': r.get('verdict'), 'issues': r.get('issues', []),
                                'missing': r.get('requested_functions_missing_or_broken', [])} for r in runs]}
    (rd / 'review-reply.json').write_text(json.dumps(reply, ensure_ascii=False, indent=1), encoding='utf-8')
    cleanup_round(rd, runs, a.keep_artifacts)
    print(json.dumps({k: reply[k] for k in ('verdict', 'must_per_run', 'scores', 'skipped_after_revise')}, ensure_ascii=False))
    return 0 if reply['verdict'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
