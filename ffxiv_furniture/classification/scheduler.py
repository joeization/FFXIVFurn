"""Explicit, bounded multi-round staging; planning never invokes a model."""
from collections import defaultdict, Counter
from contextlib import closing
import json
from pathlib import Path
import random
import re
import sqlite3
from .state import digest, read_json, write_json, connect


def round_history(run_dir):
    rounds = [read_json(p) for p in sorted(Path(run_dir).glob('round-*.json'))]
    for value in rounds:
        if digest({k: v for k, v in value.items() if k != 'round_hash'}) != value['round_hash']:
            raise ValueError('Round snapshot hash mismatch')
    return sorted(rounds, key=lambda r: r['round'])


def exploration_records(run_dir):
    """All successful discovery observations, resolved through exact round hashes."""
    root = Path(run_dir)
    history = {r['round_hash']: r for r in round_history(root)}
    if not (root / 'state.sqlite3').exists():
        return []
    output = []
    with closing(sqlite3.connect(f'{(root / "state.sqlite3").resolve().as_uri()}?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("""SELECT p.*,j.phase,j.input,j.finished_at FROM predictions p
          JOIN jobs j ON j.id=p.job_id WHERE j.status='succeeded' AND j.kind='visual'
          AND j.phase IN ('explore','guided') ORDER BY j.finished_at,j.id,p.anon_id""")
        for raw in rows:
            row = dict(raw)
            meta = json.loads(row.pop('input'))['metadata']
            role = meta.get('role', 'main')
            plan = history.get(meta.get('round_hash'))
            if not plan or role not in ('main', 'control'):
                continue
            image = next((r for r in plan['images'] if r['anon_id'] == row['anon_id'] and r['image_hash'] == row['image_hash']), None)
            if image:
                vocabulary = plan.get('vocabulary') or meta.get('vocabulary_snapshot')
                if row['phase'] == 'guided' and not vocabulary:
                    saved = db.execute('SELECT data FROM vocab_versions WHERE hash=?', (meta.get('vocab_hash'),)).fetchone()
                    vocabulary = json.loads(saved[0]) if saved else None
                output.append({**row, 'data': json.loads(row['data']), 'image': image,
                               'round': plan['round'], 'role': role,
                               'vocabulary': vocabulary})
    return output


def exploration_coverage(run_dir):
    all_images = {r['image_hash'] for r in read_json(Path(run_dir) / 'manifest.json')['assets']}
    success = {r['image_hash'] for r in exploration_records(run_dir) if r['role'] == 'main'} & all_images
    return {'eligible_image_hashes': sorted(all_images), 'successful_image_hashes': sorted(success),
            'unseen_image_hashes': sorted(all_images - success), 'complete': success == all_images}


def _pool(manifest):
    grouped = defaultdict(list)
    for row in manifest['assets']:
        grouped[row['image_hash']].append(row)
    result = []
    for image_hash, mappings in sorted(grouped.items()):
        rep = min(mappings, key=lambda r: (r['scope'], r['source_category'], r['asset_key']))
        result.append({'image_hash': image_hash, 'representative': rep, 'mappings': mappings,
                       'stratum': [rep['scope'], rep['source_category']]})
    return result


def _stratified(pool, count, rng):
    groups = defaultdict(list)
    for row in pool:
        groups[tuple(row['stratum'])].append(row)
    for rows in groups.values():
        rng.shuffle(rows)
    selected = []
    # Randomized round-robin across strata; no replacement.
    while len(selected) < count and groups:
        keys = sorted(groups)
        rng.shuffle(keys)
        for key in keys:
            if len(selected) == count:
                break
            selected.append(groups[key].pop())
            if not groups[key]:
                del groups[key]
    return selected


def _round_done(plan, records):
    successes = {(r['image_hash'], r['role']) for r in records if r['round'] == plan['round']}
    main = all((r['image_hash'], 'main') in successes for r in plan['images'])
    controls = all((r['image_hash'], 'control') in successes for r in plan['images']
                   if r['anon_id'] in plan.get('unguided_control_ids', [])) if plan.get('phase') == 'guided' else True
    return main and controls


def _plan(run_dir, kind, vocab, seed, targets):
    root = Path(run_dir)
    manifest = read_json(root / 'manifest.json')
    history = round_history(root)
    records = exploration_records(root)
    if not history:
        raise ValueError('Prepare and sample round one first')
    if kind == 'next-round' and not _round_done(history[0], records):
        raise ValueError('Complete original round exploration first')
    latest = next((r for r in reversed(history) if r.get('kind') == kind), None)
    # Resume the exact immutable plan; never let a changed seed/vocab silently alter it.
    if latest and (kind != 'next-round' or not _round_done(latest, records)):
        if vocab and digest(read_json(vocab)) != latest.get('vocab_hash'):
            raise ValueError('Resume vocabulary differs from immutable snapshot')
        return latest, True
    if kind == 'next-round' and any(r.get('kind') == 'discover-rest' for r in history):
        raise ValueError('Discovery pass already scheduled; resume discover-rest')
    vocabulary = read_json(vocab) if vocab else None
    if vocabulary is None:
        raise ValueError('--vocab is required to create a guided/final plan')
    from .vocabulary import validate_vocab
    validate_vocab(vocabulary)
    if kind == 'final-all' and not vocabulary.get('frozen'):
        raise ValueError('final-all requires frozen vocabulary')
    if kind == 'final-all' and not exploration_coverage(root)['complete']:
        raise ValueError('final-all blocked: entire library must be explored first')
    pool = _pool(manifest)
    known_hashes = {r['image_hash'] for r in pool}
    if any(not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h) or h not in known_hashes for h in targets or []):
        raise ValueError('Targets must be exact lowercase SHA-256 image hashes from this manifest')
    rng = random.Random(seed)
    selected = []
    if kind == 'next-round':
        reserved = {r['image_hash'] for p in history for r in p['images']}
        available = [r for r in pool if r['image_hash'] not in reserved]
        random_rows = _stratified(available, 32, rng)
        for row in random_rows:
            row['selection_reason'] = 'random'
        selected += random_rows
        available = [r for r in available if r not in selected]
        total = Counter(tuple(r['stratum']) for r in pool)
        unique_seen = {r['image_hash']: r['image'] for r in records if r['role'] == 'main'}
        seen = Counter(tuple(r['stratum']) for r in unique_seen.values())
        rng.shuffle(available)
        available.sort(key=lambda r: seen[tuple(r['stratum'])] / total[tuple(r['stratum'])])
        for row in available[:16]:
            row['selection_reason'] = 'low_coverage'
            selected.append(row)
        available = [r for r in available if r not in selected]
        wanted = set(targets or [])
        targeted = _stratified([r for r in available if r['image_hash'] in wanted], 16, rng)
        for row in targeted:
            row['selection_reason'] = 'target'
        selected += targeted
        for row in _stratified([r for r in available if r not in targeted], 16 - len(targeted), rng):
            row['selection_reason'] = 'target_fallback_random'
            selected.append(row)
    else:
        unseen = set(exploration_coverage(root)['unseen_image_hashes'])
        selected = [r for r in pool if kind == 'final-all' or r['image_hash'] in unseen]
        for row in selected:
            row['selection_reason'] = kind
    if not selected:
        raise ValueError('No unseen images remain; no empty round created')
    number = max(r['round'] for r in history) + 1
    for index, row in enumerate(selected, 1):
        row['anon_id'] = f'R{number:03d}I{index:04d}'
    random_ids = [r['anon_id'] for r in selected if r['selection_reason'] == 'random']
    controls = sorted(rng.sample(random_ids, min(8, len(random_ids)))) if kind == 'next-round' else []
    anchors = history[0].get('anchor_ids', [])
    plan = {'round': number, 'kind': kind, 'phase': 'final' if kind == 'final-all' else 'guided',
            'manifest_hash': manifest['manifest_hash'], 'seed': seed, 'images': selected,
            'vocabulary': vocabulary, 'vocab_hash': digest(vocabulary),
            'unguided_control_ids': controls, 'anchor_ids': anchors,
            'anchor_round_hash': history[0]['round_hash'], 'anchor_policy': 'fixed development set; explicit QA only',
            'target_image_hashes': sorted(set(targets or []))}
    plan['round_hash'] = digest(plan)
    return plan, False


def schedule(run_dir, kind, vocab=None, seed=43, targets=None, dry_run=False,
             execute=False, endpoint=None, model=None, batch_size=4, max_batches=1,
             timeout=180, deployment_revision=None, client=None):
    if kind not in ('next-round', 'discover-rest', 'final-all'):
        raise ValueError('Unknown scheduler kind')
    if batch_size not in range(1, 17) or type(max_batches) is not int or max_batches < 1:
        raise ValueError('batch-size must be 1..16; bounded positive --max-batches required')
    if execute and dry_run:
        raise ValueError('--execute and --dry-run are mutually exclusive')
    if execute and not client and (not endpoint or not model):
        raise ValueError('--execute requires explicit --endpoint and --model')
    plan, resumed = _plan(run_dir, kind, vocab, seed, targets)
    result = {'kind': kind, 'round': plan['round'], 'round_hash': plan['round_hash'],
              'selected': len(plan['images']), 'selection_counts': dict(Counter(r['selection_reason'] for r in plan['images'])),
              'controls': len(plan['unguided_control_ids']), 'vocab_hash': plan['vocab_hash'],
              'resumed': resumed, 'dry_run': dry_run, 'executed': False,
              'image_hashes': [r['image_hash'] for r in plan['images']]}
    if dry_run:
        return result
    root = Path(run_dir)
    # Serialize plan creation against other schedulers; immutable files survive restarts.
    with closing(connect(root)) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            path = root / f"round-{plan['round']:03d}.json"
            if path.exists() and read_json(path) != plan:
                raise ValueError('Round number already occupied; retry status/resume')
            if not path.exists():
                write_json(path, plan)
            for historical in round_history(root):
                db.execute('INSERT OR IGNORE INTO rounds VALUES(?,?,?)',
                           (historical['round'], historical['round_hash'], json.dumps(historical)))
    if execute:
        from .runner import classify
        from .client import Client
        # Bounded guided dictionaries can exhaust Qwen's answer cap in reasoning.
        # execute_job hashes this explicit setting into each new request identity.
        client = client or Client(endpoint, model, timeout, enable_thinking=False, structured_output=True)
        settings = {'endpoint': endpoint or client.endpoint, 'model': model or client.model,
                    'batch_size': batch_size, 'deployment_revision': deployment_revision}
        execution_path = root / f"execution-{plan['round']:03d}.json"
        if execution_path.exists() and read_json(execution_path) != settings:
            raise ValueError('Execution settings changed; keep endpoint/model/revision/batch-size fixed to resume')
        if not execution_path.exists():
            write_json(execution_path, settings)
        main = classify(root, client.endpoint, client.model, batch_size, max_batches, timeout,
                        plan['phase'], plan['vocabulary'], deployment_revision, client, plan)
        remaining = max_batches - main['new_batches']
        result.update(main)
        if remaining and plan['unguided_control_ids']:
            control = {**plan, 'images': [r for r in plan['images'] if r['anon_id'] in plan['unguided_control_ids']]}
            extra = classify(root, client.endpoint, client.model, batch_size, remaining, timeout,
                             'explore', None, deployment_revision, client, control, 'control')
            result['new_batches'] += extra['new_batches']
            result['cached_batches'] += extra['cached_batches']
        result['executed'] = True
    return result


def next_round(run_dir, **kwargs):
    return schedule(run_dir, 'next-round', **kwargs)


def discover_rest(run_dir, **kwargs):
    return schedule(run_dir, 'discover-rest', **kwargs)


def final_all(run_dir, **kwargs):
    return schedule(run_dir, 'final-all', **kwargs)


def status(run_dir):
    history = round_history(run_dir)
    coverage = exploration_coverage(run_dir)
    records = exploration_records(run_dir)
    successes, anchor_results = _audit_successes(run_dir)
    return {'staging_only': True, 'rounds': [{'round': p['round'], 'kind': p.get('kind', 'pilot'),
            'round_hash': p['round_hash'], 'selected': len(p['images']),
            'successful': len({r['image_hash'] for r in p['images']} & successes.get(p['round_hash'], set())),
            'complete': _round_done(p, records) if p.get('phase') != 'final' else
                {r['image_hash'] for r in p['images']} <= successes.get(p['round_hash'], set())}
            for p in history], 'eligible_unique_images': len(coverage['eligible_image_hashes']),
            'successful_unique_images': len(coverage['successful_image_hashes']),
            'unseen_unique_images': len(coverage['unseen_image_hashes']),
            'full_library_explored': coverage['complete'], 'stopped': (Path(run_dir) / 'STOP').exists(),
            'anchor_trends': anchor_results,
            'convergence': convergence_report(run_dir)}


def _audit_successes(run_dir):
    """Per-plan completion and development-anchor change trends, not accuracy."""
    path = Path(run_dir) / 'state.sqlite3'
    if not path.exists():
        return {}, []
    successes = defaultdict(set)
    anchor_sets = {}
    with closing(sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)) as db:
        for image_hash, raw_data, raw_input, finished in db.execute("""SELECT p.image_hash,p.data,j.input,j.finished_at
                FROM predictions p JOIN jobs j ON j.id=p.job_id
                WHERE j.status='succeeded' AND j.kind='visual' ORDER BY j.finished_at,j.id"""):
            identity = json.loads(raw_input)
            meta = identity['metadata']
            role = meta.get('role', 'main')
            if role == 'main':
                successes[meta['round_hash']].add(image_hash)
            elif role == 'anchor':
                key = digest({'vocab_hash': meta.get('vocab_hash'), 'endpoint': identity['endpoint'],
                              'model': identity['model'], 'deployment_revision': identity.get('deployment_revision')})
                bucket = anchor_sets.setdefault(key, {'vocab_hash': meta.get('vocab_hash'), 'images': {}, 'finished_at': finished})
                bucket['images'][image_hash] = {t.get('key') for t in json.loads(raw_data)['tags']}
                bucket['finished_at'] = max(bucket['finished_at'], finished)
    trends, previous = [], None
    for bucket in sorted(anchor_sets.values(), key=lambda r: r['finished_at']):
        overlap = set(bucket['images']) & set(previous['images']) if previous else set()
        trends.append({'vocab_hash': bucket['vocab_hash'], 'successful_anchors': len(bucket['images']),
                       'overlap_with_previous': len(overlap),
                       'changed_tag_sets': sum(bucket['images'][h] != previous['images'][h] for h in overlap),
                       'note': 'Development consistency only; key changes can reflect vocabulary revisions, not quality.'})
        previous = bucket
    return dict(successes), trends


def convergence_report(run_dir):
    """Only explicit human-adjudicated genuinely-new concepts can satisfy numerator."""
    root = Path(run_dir)
    history = [p for p in round_history(root) if p.get('kind') == 'next-round']
    records = exploration_records(root)
    qa = read_json(root / 'convergence-qa.json') if (root / 'convergence-qa.json').exists() else {}
    rows = []
    for plan in history:
        random_images = {r['image_hash'] for r in plan['images'] if r['selection_reason'] == 'random'}
        success = {r['image_hash'] for r in records if r['round'] == plan['round'] and r['role'] == 'main'}
        review = qa.get(plan['round_hash'], {})
        new_images = review.get('genuinely_new_image_hashes')
        valid = isinstance(new_images, list) and set(new_images) <= random_images and bool(review.get('reviewer'))
        denominator = len(random_images & success)
        numerator = len(set(new_images)) if valid else None
        rows.append({'round': plan['round'], 'round_hash': plan['round_hash'], 'random_numerator': numerator,
                     'random_denominator': denominator, 'random_selected': len(random_images),
                     'new_concept_rate': numerator / denominator if valid and denominator else None,
                     'random_complete': random_images <= success, 'manual_qa': review,
                     'round_complete_including_controls': _round_done(plan, records),
                     'control_comparison_required': True, 'anchor_comparison_required': True})
    latest = rows[-3:]
    signal = len(latest) == 3 and all(r['random_complete'] and r['round_complete_including_controls'] and r['new_concept_rate'] is not None
        and r['new_concept_rate'] < .05 for r in latest)
    gates = ('controls_no_repeated_misses', 'anchors_no_systematic_regression', 'no_high_impact_pending')
    reviewed = signal and all(all(r['manual_qa'].get(k) is True for k in gates) for r in latest)
    return {'rounds': rows, 'three_round_low_rate_signal': signal, 'manual_gates_passed': reviewed,
            'converged': False, 'discover_rest_recommended': reviewed,
            'note': 'Review-assisted signal only, never proof of completeness. Raw proposed strings are not new concepts.'}


def anchor_qa(run_dir, vocab=None, seed=43, dry_run=False, execute=False, endpoint=None,
              model=None, batch_size=4, max_batches=1, timeout=180,
              deployment_revision=None, client=None):
    """Fixed original anchors, once per snapshot/settings via cache, explicitly invoked."""
    if not vocab:
        raise ValueError('anchor-qa requires --vocab')
    if execute and dry_run:
        raise ValueError('--execute and --dry-run are mutually exclusive')
    if type(max_batches) is not int or max_batches < 1 or batch_size not in range(1, 17):
        raise ValueError('Positive bounded max-batches and batch-size 1..16 required')
    from .vocabulary import validate_vocab
    vocabulary = validate_vocab(read_json(vocab))
    root = Path(run_dir)
    original = round_history(root)[0]
    plan = {**original, 'images': [r for r in original['images'] if r['anon_id'] in original['anchor_ids']]}
    result = {'selected': len(plan['images']), 'anchor_ids': original['anchor_ids'],
              'vocab_hash': digest(vocabulary), 'dry_run': dry_run, 'executed': False}
    if dry_run:
        return result
    snapshot = {'original_round_hash': original['round_hash'], 'vocabulary': vocabulary,
                'anchor_ids': original['anchor_ids']}
    path = root / 'anchor-qa' / (digest(snapshot) + '.json')
    if path.exists() and read_json(path) != snapshot:
        raise ValueError('Anchor QA snapshot changed')
    if not path.exists():
        write_json(path, snapshot)
    if execute:
        if not client and (not endpoint or not model):
            raise ValueError('--execute requires explicit --endpoint and --model')
        from .runner import classify
        result.update(classify(root, endpoint, model, batch_size, max_batches, timeout,
                               'guided', vocabulary, deployment_revision, client, plan, 'anchor'))
        result['executed'] = True
    return result
