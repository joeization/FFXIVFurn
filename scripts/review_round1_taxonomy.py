"""Reproducible agent adjudication of the bounded round-one evidence, no model calls.

Run from repository root: .venv/Scripts/python.exe scripts/review_round1_taxonomy.py
Writes only runs/round1/review. Raw inputs and predictions are never rewritten.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ffxiv_furniture.classification.state import digest, read_json, write_json
from ffxiv_furniture.classification.taxonomy import counts, grouping, materialize_observations, reclassify
from ffxiv_furniture.classification.vocabulary import apply_vocab, validate_vocab


# Evidence-specific proposal positions are pinned to exact source file hashes.
STRICT = {8, 11, 12, 13, 14, 15, 16, 23, 35, 59, 62}
RELATED = {19, 20, 21, 22, 50, 51, 53, 54, 56, 58, 78, 80}
SOURCE_HASHES = {
    'candidate-inventory.json': 'b984f9fb0e8a26819bbd60a9333be907100681b5fdd002867034ecc166ecf121',
    'consolidation-proposals.json': '1d5e99c85ffec879ef36b5da40e8e2602553f7f727359c7b1c64039811a9c5f8',
    'tag-observations.json': 'e09faf39e74a31f7e882e0305bf2b0b325bd66588ff6dbc03b412b9b33d4cb51',
    'vocab-latest.json': '38453fb13513cc4e0069a79ed40e62c414e79b8431deaadfdc5888743042b1b4'}


def review(run_dir):
    root = Path(run_dir)
    output = root / 'review'
    if (output / 'apply-result.json').exists():
        raise ValueError('Review already exists; preserve its audit rather than overwrite it')
    for name, expected in SOURCE_HASHES.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Evidence snapshot changed: {name}; this review must not be blindly reused')
    inventory = read_json(root / 'candidate-inventory.json')
    original = read_json(root / 'vocab-latest.json')
    original_proposals = read_json(root / 'consolidation-proposals.json')
    observations = read_json(root / 'tag-observations.json')
    if len(inventory['concepts']) != 284 or len(original_proposals) != 90 or len(observations) != 453:
        raise ValueError('This evidence-specific review requires the original round-one snapshot')
    if original['proposals'] != original_proposals or len(original['concepts']) != 284:
        raise ValueError('Vocabulary/proposal snapshot mismatch')
    vocab = deepcopy(original)
    by_name = {(c['category'], c['name']): c for c in vocab['concepts']}
    by_id = {c['concept_id']: c for c in vocab['concepts']}
    log = []
    for index, proposal in enumerate(vocab['proposals']):
        if proposal['status'] != 'pending':
            continue
        source, target = by_id[proposal['source']], by_id[proposal['target']]
        if index in STRICT:
            reason = ('Reviewed labels have interchangeable visual meaning and scope in their category; '
                      'no hue, component, finish, or structural qualifier is removed. Material terms describe appearance, not composition.')
            proposal['status'] = 'accepted'
        elif index in RELATED:
            reason = 'Preserve both concepts and all specificity; a non-equivalence association is useful, not grounds for merging.'
            proposal['status'] = 'accepted'
        else:
            reason = ('Reject the proposed equivalence/association: qualifiers, subtype/component scope, hue/saturation, '
                      'or distinct depicted subjects are not interchangeable. Retain original provisional concept and evidence; '
                      'frequency is not a reason to erase a rare concept.')
            proposal['status'] = 'rejected'
        proposal.update(reviewer='agent', review_reason=reason)
        log.append({'proposal_id': proposal['proposal_id'], 'original_index': index,
                    'action': proposal['action'], 'source_name': source['name'], 'target_name': target['name'],
                    'status': proposal['status'], 'reviewer': 'agent', 'reason': reason,
                    'source_observations': [o for o in observations if o['concept_id'] == source['concept_id']],
                    'target_observations': [o for o in observations if o['concept_id'] == target['concept_id']]})

    def add(action, category, source_name, target_name, reason):
        source = by_name[(category, source_name)]['concept_id']
        target = by_name[(category, target_name)]['concept_id']
        if any(p['action'] == action and p['source'] == source and p.get('target') == target
               and p['status'] == 'accepted' for p in vocab['proposals']):
            return
        proposal = {'action': action, 'source': source, 'target': target, 'reason': reason,
                    'status': 'accepted', 'policy': 'agent-evidence-review', 'reviewer': 'agent', 'review_reason': reason}
        if action in ('alias', 'merge'):
            proposal['interchangeable'] = True
        proposal['proposal_id'] = digest(proposal)
        vocab['proposals'].append(proposal)
        log.append({'proposal_id': proposal['proposal_id'], 'action': action, 'source_name': source_name,
                    'target_name': target_name, 'status': 'accepted', 'reviewer': 'agent', 'reason': reason,
                    'source_observations': [o for o in observations if o['concept_id'] == source],
                    'target_observations': [o for o in observations if o['concept_id'] == target]})

    # Explicit scoped synonym sets; no general adjective stripping or fuzzy matching.
    for category, target, sources in [
        ('material', 'wood-like appearance', ['wood', 'wood-like']),
        ('material', 'matte surface', ['matte']),
        ('material', 'glossy surface', ['glossy']),
        ('material', 'woven texture', ['woven']),
        ('material', 'wooden planks', ['wooden plank appearance']),
        ('color', 'multicolor', ['multicolored']),
        ('color', 'reddish brown', ['reddish-brown']),
        ('color', 'pink and purple', ['purple and pink']),
        ('color', 'dark red', ['deep red']),
        ('color', 'dark purple', ['deep purple']),
        ('form', 'rectangular panel', ['flat rectangular panel']),
        ('form', 'cylindrical', ['cylinder']),
    ]:
        for source in sources:
            add('alias', category, source, target,
                'Agent reviewed same-category visual synonyms; phrasing/spelling changes only, preserving all meaningful modifiers.')

    # Useful hierarchy without flattening the original qualifiers or rare concepts.
    for category, source, target in [
        ('material', 'wood-like frame', 'wood-like appearance'),
        ('material', 'wooden plank appearance', 'wood-like appearance'),
        ('material', 'wooden planks', 'wood-like appearance'),
        ('material', 'wooden board', 'wood-like appearance'),
        ('material', 'wooden slat appearance', 'wood-like appearance'),
        ('material', 'dark wood appearance', 'wood-like appearance'),
        ('material', 'painted wood appearance', 'wood-like appearance'),
        ('material', 'metallic grid appearance', 'metallic appearance'),
        ('material', 'metallic gold appearance', 'metallic appearance'),
        ('material', 'dark metal appearance', 'metallic appearance'),
        ('material', 'dark metal-like', 'metallic appearance'),
        ('material', 'smooth matte surface', 'matte surface'),
        ('material', 'matte stone-like appearance', 'stone'),
        ('material', 'stone-like', 'stone'),
        ('material', 'stone-look', 'stone'),
        ('material', 'white fabric appearance', 'fabric-like'),
        ('material', 'fabric upholstery appearance', 'fabric-like'),
        ('form', 'arched panel', 'panel'),
        ('form', 'rectangular frame with central panel', 'rectangular frame'),
        ('form', 'circular ground patch', 'ground patch'),
        ('form', 'low rectangular table', 'rectangular table'),
        ('ornament', 'geometric border', 'geometric pattern'),
        ('theme', 'palm-like plant', 'plant-like'),
        ('theme', 'green foliage', 'foliage'),
        ('theme', 'blossoming scene', 'botanical'),
        ('theme', 'flowering ground cover', 'botanical'),
        ('theme', 'miniature garden', 'botanical'),
    ]:
        add('broader', category, source, target,
            'Source is narrower than target. Retain source as distinct; relation is for grouping only, never an alias or automatic extra image tag.')
    for source, target in [('muted green','green'), ('pale green','green'), ('olive green','green'),
                           ('dark green','green'), ('dark red','red'), ('medium brown','brown'),
                           ('reddish brown','brown'), ('pale cream','cream'), ('warm yellow','yellow'),
                           ('bright yellow','yellow'), ('deep purple','purple'), ('dark purple','purple'),
                           ('pale purple','purple'), ('dark blue','blue'), ('light gray','gray'),
                           ('dark gray','gray')]:
        add('broader', 'color', source, target,
            'Shade or saturation qualifier is meaningful. Source remains distinct; target groups the broader hue only.')
    for category, source, target in [('material','worn surface appearance','weathered surface'),
                                    ('color','gray-brown','gray'), ('color','gray-brown','brown'),
                                    ('material','wood-like and fabric-like','wood-like appearance'),
                                    ('material','wood-like and fabric-like','fabric-like'),
                                    ('material','stone-like and patterned surfaces','stone')]:
        add('related', category, source, target,
            'Overlap/component association only. Composite or surface distinctions retained, never equivalent or blindly decomposed.')

    # Supply bounded evidence-based working definitions, not unsupported image judgments.
    for concept in vocab['concepts']:
        evidence = [o['evidence'] for o in observations if o['concept_id'] == concept['concept_id']]
        concept['definition'] = (f"Visible {concept['category']} descriptor '{concept['name']}'. "
                                 'Observed evidence: ' + '; '.join(dict.fromkeys(evidence))[:650])
        if concept['category'] == 'material':
            concept['definition'] += ' Describes appearance only; actual composition is unverified.'
        concept['include'] = list(dict.fromkeys(evidence))[:5]
        concept['exclude'] = ['Do not infer hidden structure, provenance, or unobserved properties.']
    accepted_names = {
        'material': {'wood-like appearance', 'metallic appearance', 'stone', 'matte surface', 'glossy surface', 'woven texture'},
        'color': {'red','green','blue','yellow','purple','pink','orange','brown','black','white','gray','light gray',
                  'dark gray','dark brown','rust brown','multicolor','reddish brown','pink and purple'},
        'form': {'round','column','cylindrical','rectangular panel'},
    }
    for concept in vocab['concepts']:
        if concept['name'] in accepted_names.get(concept['category'], set()):
            concept['status'] = 'accepted'
            vocab['decisions'].append({'action': 'accept-concept', 'concept_id': concept['concept_id'],
                'reviewer': 'agent', 'status': 'accepted', 'reason': 'Unambiguous visual descriptor supported by retained source observations; scope limited to appearance.'})
    carved = by_name[('style', 'carved')]
    new_id = reclassify(vocab, carved['concept_id'], 'ornament', observations,
                       'Incised surface decoration describes ornament, not a coherent overall style; source observations support only decoration.')
    by_target = next(c for c in vocab['concepts'] if c['concept_id'] == new_id)
    by_target['definition'] = 'Visible incised/carved surface decoration. Does not identify an overall aesthetic or actual manufacturing process.'
    vocab['frozen'] = False
    vocab['notes'] += ['Agent evidence review resolved all original pending proposals; rare concepts and shade/composite distinctions retained.',
                       'Four active style labels remain provisional: antique is weakly supported by arch/trim and cannot establish historical provenance.',
                       'No images re-inferred, unseen tags invented, or furniture IDs assigned. Category refactor creates a new identity with source observation links.',
                       'Broader means source=narrower,target=broader. Relations do not automatically add tags to any image.']
    validate_vocab(vocab)
    output.mkdir(parents=True, exist_ok=True)
    # Snapshot exact original files; sqlite backup preserves all evidence rows including raw responses.
    raw_paths = ['candidate-inventory.json','consolidation-proposals.json','tag-observations.json','vocab-latest.json']
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in raw_paths}
    source_db = sqlite3.connect(root / 'state.sqlite3')
    target_db = sqlite3.connect(output / 'state.sqlite3')
    try:
        source_db.backup(target_db)
        before_predictions = source_db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]
        before_response = source_db.execute('SELECT COUNT(*) FROM responses').fetchone()[0]
    finally:
        source_db.close(); target_db.close()
    write_json(output / 'source-vocab.json', original)
    write_json(output / 'vocab-latest.json', original)
    write_json(output / 'reviewed-vocab-candidate.json', vocab)
    result = apply_vocab(output, output / 'reviewed-vocab-candidate.json')
    applied = validate_vocab(read_json(output / 'vocab-latest.json'))
    # Verify saved external state and lossless preservation, not just a successful return.
    db = sqlite3.connect(output / 'state.sqlite3')
    try:
        saved = json.loads(db.execute('SELECT data FROM vocab_versions WHERE hash=?', (result['hash'],)).fetchone()[0])
        assert saved == applied
        assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == before_predictions
        assert db.execute('SELECT COUNT(*) FROM responses').fetchone()[0] == before_response
    finally:
        db.close()
    for name, value in hashes.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == value
    assert {c['concept_id'] for c in original['concepts']} <= {c['concept_id'] for c in applied['concepts']}
    for concept in original['concepts']:
        after = next(c for c in applied['concepts'] if c['concept_id'] == concept['concept_id'])
        assert concept['category'] == after['category'] and set(concept['original_names']) <= set(after['original_names'])
    derived = materialize_observations(applied, observations)
    assert len(derived) == len(observations)
    write_json(output / 'review-log.json', {'reviewer': 'agent', 'method': 'bounded-programmatic-evidence-plus-agent-semantic-review',
        'model_calls': 0, 'original_pending_decisions': [r for r in log if 'original_index' in r],
        'additional_decisions': [r for r in log if 'original_index' not in r], 'source_sha256': hashes})
    write_json(output / 'reviewed-tag-observations.json', derived)
    write_json(output / 'grouped-concepts.json', grouping(applied, observations))
    style_notes = {
        'ornate': 'Elaborate frames/borders support the descriptor; keep provisional, not a historical style attribution.',
        'rustic': 'A single aged/worn example supports only a tentative overall aesthetic; do not generalize to unseen images.',
        'antique': 'Arch and trim do not establish age or provenance. Preserve the original provisional hypothesis; do not promote it.',
        'carved': 'Incised decoration is ornament, not overall style. New category identity supersedes source with exact evidence links.',
        'anime-style': 'Stylized illustration supports a provisional depiction-style descriptor only; not every stylized figure is anime.'}
    write_json(output / 'style-review.json', {'raw_style_concepts': 5, 'active_style_concepts': 4,
        'new_style_labels_invented': 0, 'reviewer': 'agent',
        'assessment': [{'concept_id': c['concept_id'], 'name': c['name'], 'status': c['status'],
                        'reason': style_notes[c['name']], 'superseded_by': c.get('superseded_by'),
                        'source_observations': [o for o in observations if o['concept_id'] == c['concept_id']]}
                       for c in applied['concepts'] if c['category'] == 'style']})
    summary = {'apply_result': result, 'before': counts(original), 'after': counts(applied),
               'original_pending_reviewed': sum('original_index' in r for r in log),
               'original_pending_outcomes': dict(Counter(r['status'] for r in log if 'original_index' in r)),
               'preserved_original_concepts': len(original['concepts']), 'new_category_refactor_concepts': 1,
               'raw_observations': len(observations), 'derived_observations': len(derived),
               'unique_observed_images': len({o['image_hash'] for o in observations}),
               'preserved_predictions': before_predictions, 'preserved_responses': before_response,
               'source_sha256': hashes, 'raw_source_files_unchanged': True,
               'staging_only': True, 'frozen': False}
    write_json(output / 'apply-result.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=Path('runs/round1'))
    args = parser.parse_args()
    print(json.dumps(review(args.run_dir), indent=2))
