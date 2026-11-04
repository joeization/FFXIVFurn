"""Round-one total-budget stratified sampling of unique image bytes."""
from collections import defaultdict
import math
from pathlib import Path
import random
from .state import digest, read_json, write_json


def sample(run_dir, budget=96, seed=42, min_per_stratum=2):
    if type(budget) is not int or budget < 1 or min_per_stratum < 0:
        raise ValueError('budget must be positive and minimum nonnegative')
    manifest = read_json(Path(run_dir) / 'manifest.json')
    grouped = defaultdict(list)
    for row in manifest['assets']:
        grouped[row['image_hash']].append(row)
    # One representative per image; all original mappings remain private in the round.
    strata = defaultdict(list)
    for image_hash, mappings in sorted(grouped.items()):
        representative = min(mappings, key=lambda r: (r['scope'], r['source_category'], r['asset_key']))
        strata[(representative['scope'], representative['source_category'])].append(image_hash)
    rng = random.Random(seed)
    keys = sorted(strata)
    for key in keys:
        rng.shuffle(strata[key])
    order = keys[:]
    rng.shuffle(order)
    quotas = dict.fromkeys(keys, 0)
    budget = min(budget, len(grouped))
    # Round-robin minimums, so insufficient budgets do not favor lexicographic groups.
    for _ in range(min_per_stratum):
        for key in order:
            if sum(quotas.values()) < budget and quotas[key] < len(strata[key]):
                quotas[key] += 1
    base = quotas.copy()
    weights = {k: math.sqrt(len(strata[k]) - base[k]) for k in keys}
    while sum(quotas.values()) < budget:
        available = [k for k in keys if quotas[k] < len(strata[k])]
        # Weighted fair allocation: sqrt remaining population, stable tie-breaking.
        key = min(available, key=lambda k: ((quotas[k] - base[k] + 1) / weights[k], k))
        quotas[key] += 1
    images = []
    for key in keys:
        for index, image_hash in enumerate(strata[key][:quotas[key]]):
            mappings = grouped[image_hash]
            representative = min(mappings, key=lambda r: (r['scope'], r['source_category'], r['asset_key']))
            images.append({'image_hash': image_hash, 'representative': representative,
                           'mappings': mappings, 'stratum': list(key),
                           'selection_reason': 'minimum_coverage' if index < base[key] else 'sqrt_random'})
    rng.shuffle(images)
    for i, row in enumerate(images, 1):
        row['anon_id'] = f'I{i:04d}'
    controls = sorted(rng.sample([r['anon_id'] for r in images], min(8, len(images))))
    # Cross-stratum anchors, without extra model calls in first round.
    anchors = []
    for key in order:
        match = next((r['anon_id'] for r in images if r['stratum'] == list(key)), None)
        if match and len(anchors) < 24:
            anchors.append(match)
    extras = [r['anon_id'] for r in images if r['anon_id'] not in anchors]
    anchors.extend(rng.sample(extras, min(24 - len(anchors), len(extras))))
    result = {'round': 1, 'manifest_hash': manifest['manifest_hash'], 'budget': budget, 'seed': seed,
              'min_per_stratum': min_per_stratum, 'allocation': 'minimum-then-sqrt-remaining-v1',
              'images': images, 'unguided_control_ids': controls, 'anchor_ids': sorted(anchors),
              'controls_note': 'Explore is already unguided; no duplicate control calls in round one.',
              'minimum_coverage_shortfall': [list(k) for k in keys if quotas[k] < min(min_per_stratum, len(strata[k]))],
              'duplicate_policy': 'unique image bytes; deterministic single stratum representative; all mappings retained'}
    result['round_hash'] = digest(result)
    path = Path(run_dir) / 'round-001.json'
    if path.exists() and read_json(path) != result:
        raise ValueError('Round one is immutable; use a different run directory for another sample')
    write_json(path, result)
    return {'selected': len(images), 'round_hash': result['round_hash'],
            'minimum_coverage_shortfall': result['minimum_coverage_shortfall']}
