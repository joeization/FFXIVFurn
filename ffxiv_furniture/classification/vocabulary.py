"""Versioned concepts and conservative bounded text-only model proposals."""
from collections import defaultdict
import json
from pathlib import Path
import time
import unicodedata
from . import CATEGORIES, PROMPT_VERSION
from .client import Client
from .prompts import CONSOLIDATE_PROMPT
from .state import connect, digest, dumps, read_json, write_json
from .validation import text


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


def observations(run_dir, phase='explore'):
    """Latest successful observation per image+category context, never failed jobs."""
    db = connect(run_dir)
    try:
        rows = db.execute('''SELECT p.*,j.phase,j.finished_at,j.id FROM predictions p
          JOIN jobs j ON j.id=p.job_id WHERE j.status='succeeded' AND j.phase=?
          ORDER BY j.finished_at DESC,j.id DESC''', (phase,)).fetchall()
        seen, output = set(), []
        for row in rows:
            identity = (row['image_hash'], row['anon_id'])
            if identity in seen:
                continue
            seen.add(identity)
            output.append({**dict(row), 'data': json.loads(row['data'])})
        return output
    finally:
        db.close()


def discovery_observations(run_dir):
    """Discovery across immutable scheduler rounds, including guided proposals.

    Controlled keys are interpreted against their own round snapshot, not latest
    vocabulary. Unguided controls retain their separate role and original evidence.
    """
    from .scheduler import exploration_records
    records = exploration_records(run_dir)
    seen, result = set(), []
    for row in reversed(records):
        identity = (row['image_hash'], row['anon_id'], row['phase'], row['role'])
        if identity in seen:
            continue
        seen.add(identity)
        keys = {c['key']: c for c in (row.get('vocabulary') or {}).get('concepts', [])}
        tags = []
        for tag in row['data']['tags']:
            if 'key' in tag:
                if tag['key'] not in keys:
                    raise ValueError('Guided observation key absent from immutable round vocabulary')
                concept = keys[tag['key']]
                tags.append({**tag, 'category': concept['category'], 'name': concept['name'], 'source_kind': 'controlled'})
            else:
                tags.append({**tag, 'source_kind': 'unguided'})
        tags.extend({**tag, 'source_kind': 'proposed'} for tag in row['data'].get('proposed_tags', []))
        result.append({**row, 'data': {**row['data'], 'tags': tags}})
    return result


def inventory(run_dir):
    images = {}
    for path in sorted(Path(run_dir).glob('round-[0-9][0-9][0-9].json')):
        round_number = int(path.stem.split('-')[1])
        for image in read_json(path)['images']:
            images[(image['image_hash'], image['anon_id'])] = {**image, '_round': round_number}
    if not images:
        raise ValueError('No sampled rounds')
    grouped = {}
    obs = []
    for row in discovery_observations(run_dir):
        identity = (row['image_hash'], row['anon_id'])
        if identity not in images:
            raise ValueError('Observation has no sampled image context')
        image = images[identity]
        for tag in row['data']['tags']:
            category, name = tag['category'], tag['name']
            normalized = normalize(name)
            cid = 'c_' + digest([category, normalized])[:24]
            concept = grouped.setdefault(cid, {'concept_id': cid, 'key': category + ':' + normalized,
                'category': category, 'name': normalized, 'definition': '', 'include': [], 'exclude': [],
                'examples': [], 'negative_examples': [], 'status': 'provisional', 'original_names': set(),
                'images': set(), 'assets': set(), 'strata': set(), 'aliases': []})
            concept['original_names'].add(name)
            concept['images'].add(row['image_hash'])
            for mapping in image['mappings']:
                concept['assets'].add(mapping['asset_key'])
                concept['strata'].add((mapping['scope'], mapping['source_category']))
            observation = {'concept_id': cid, 'image_hash': row['image_hash'], 'anon_id': row['anon_id'],
                           'raw_name': name, 'category': category, 'evidence': tag['evidence'],
                           'confidence': tag['confidence'], 'round': image['_round'], 'job_id': row['job_id'],
                           'selection_reason': image['selection_reason'], 'stratum': image['stratum'],
                           'phase': row.get('phase', 'explore'), 'role': row.get('role', 'main'),
                           'source_kind': tag.get('source_kind', 'unguided')}
            obs.append(observation)
            if len(concept['examples']) < 3:
                concept['examples'].append({'id': row['anon_id'], 'evidence': tag['evidence']})
    concepts = []
    for cid, concept in sorted(grouped.items()):
        for field in ('images', 'assets', 'strata', 'original_names'):
            concept[field] = sorted(concept[field])
        concept['frequency'] = {'unique_images': len(concept['images']), 'furniture_candidates': len(concept['assets']),
                                'source_strata': len(concept['strata'])}
        concept['aliases'] = [{'name': name, 'language': 'und', 'scope': concept['category'],
                               'ambiguous': False, 'policy': 'NFKC-whitespace-casefold-only'}
                              for name in concept['original_names'] if name != concept['name']]
        concepts.append(concept)
    return concepts, obs


def validate_proposals(value, concepts, maximum=12):
    if not isinstance(value, dict) or set(value) != {'proposals'} or not isinstance(value['proposals'], list):
        raise ValueError('Expected proposals array')
    if len(value['proposals']) > maximum:
        raise ValueError('Too many proposals')
    known = {c['concept_id']: c for c in concepts}
    edges = {}
    seen = set()
    for proposal in value['proposals']:
        if not isinstance(proposal, dict) or set(proposal) - {'action','source','target','reason','interchangeable','name','reviewer','review_reason'}:
            raise ValueError('Unexpected proposal fields')
        action, source, target = proposal.get('action'), proposal.get('source'), proposal.get('target')
        if action not in ('alias','merge','split','reject','keep','related','broader','rename') or source not in known:
            raise ValueError('Unknown action/source')
        text(proposal.get('reason'), 'proposal reason', 500)
        if 'interchangeable' in proposal and type(proposal['interchangeable']) is not bool:
            raise ValueError('interchangeable must be boolean')
        if action in ('alias','merge','related','broader'):
            if target not in known or target == source or known[target]['category'] != known[source]['category']:
                raise ValueError('Invalid/cross-category target')
            if action in ('alias','merge'):
                if proposal.get('interchangeable') is not True:
                    raise ValueError('Merge/alias must assert interchangeable scope')
                if source in edges and edges[source] != target:
                    raise ValueError('Conflicting merge targets')
                edges[source] = target
        elif target is not None:
            raise ValueError('Unexpected target')
        if action == 'rename':
            text(proposal.get('name'), 'rename name', 100)
        identity = (action, source, target)
        if identity in seen:
            raise ValueError('Duplicate proposal')
        seen.add(identity)
    for source in edges:
        visited, current = set(), source
        while current in edges:
            if current in visited:
                raise ValueError('Merge cycle')
            visited.add(current)
            current = edges[current]
    return value


def validate_vocab(vocab):
    if not isinstance(vocab, dict) or not isinstance(vocab.get('concepts'), list):
        raise ValueError('Invalid vocabulary')
    ids, keys = set(), set()
    for concept in vocab['concepts']:
        cid = text(concept.get('concept_id'), 'concept_id', 100)
        key = text(concept.get('key'), 'canonical key', 200)
        if cid in ids or key in keys or concept.get('category') not in CATEGORIES:
            raise ValueError('Duplicate concept/key or invalid category')
        ids.add(cid)
        keys.add(key)
        if concept.get('status') not in ('provisional','accepted','rejected','unresolved','merged'):
            raise ValueError('Invalid concept status')
        if (concept['status'] == 'merged') != bool(concept.get('merged_into')):
            raise ValueError('Merged status requires exactly one merged_into target')
        if not key.startswith(concept['category'] + ':'):
            raise ValueError('Key/category mismatch')
        for field in ('name',):
            text(concept.get(field), field, 100)
        for field in ('definition',):
            if not isinstance(concept.get(field), str):
                raise ValueError('Invalid definition')
        for field in ('include','exclude','examples','negative_examples','aliases','original_names'):
            if not isinstance(concept.get(field), list):
                raise ValueError(f'Invalid {field}')
        if vocab.get('frozen') and (concept['status'] in ('provisional','unresolved') or
                                   (concept['status'] == 'accepted' and not concept['definition'].strip())):
            raise ValueError('Frozen vocab requires decided concepts and definitions')
    edges = {c['concept_id']: c['merged_into'] for c in vocab['concepts'] if c.get('merged_into')}
    for source in edges:
        by_id = {c['concept_id']: c for c in vocab['concepts']}
        visited, current = set(), source
        while current in edges:
            if current in visited or edges[current] not in ids:
                raise ValueError('Invalid/cyclic merged_into')
            if by_id[current]['category'] != by_id[edges[current]]['category']:
                raise ValueError('Cross-category merged_into')
            visited.add(current)
            current = edges[current]
        if by_id[current]['status'] not in ('accepted', 'provisional'):
            raise ValueError('Merge resolves to inactive/undecided target')
    from .taxonomy import validate_links
    validate_links(vocab)
    return vocab


def save_version(run_dir, vocab):
    validate_vocab(vocab)
    latest = Path(run_dir) / 'vocab-latest.json'
    if latest.exists():
        previous = {c['concept_id']: c for c in read_json(latest)['concepts']}
        current = {c['concept_id']: c for c in vocab['concepts']}
        if not set(previous) <= set(current):
            raise ValueError('Cannot erase concepts from a vocabulary version')
        for cid, old in previous.items():
            if old['category'] != current[cid]['category'] or not set(old['original_names']) <= set(current[cid]['original_names']):
                raise ValueError('Cannot erase originals or change permanent concept category')
    db = connect(run_dir)
    try:
        content_hash = digest(vocab)
        previous = db.execute('SELECT version FROM vocab_versions WHERE hash=?', (content_hash,)).fetchone()
        version = previous[0] if previous else db.execute('SELECT COALESCE(MAX(version),0)+1 FROM vocab_versions').fetchone()[0]
        if not previous:
            with db:
                db.execute('INSERT INTO vocab_versions VALUES(?,?,?,?)', (content_hash, version, time.time(), dumps(vocab)))
        with db:
            for decision in vocab.get('decisions', []):
                db.execute('INSERT OR IGNORE INTO tag_decisions VALUES(?,?,?)',
                           (digest(decision), time.time(), dumps(decision)))
        write_json(Path(run_dir) / f'vocab-v{version:03d}.json', vocab)
        write_json(Path(run_dir) / 'vocab-latest.json', vocab)
        return {'version': version, 'hash': content_hash, 'concepts': len(vocab['concepts']), 'frozen': vocab.get('frozen', False)}
    finally:
        db.close()


def consolidate(run_dir, endpoint, model, max_proposals=96, timeout=180, client=None, deployment_revision=None):
    if max_proposals < 1 or max_proposals > 1000:
        raise ValueError('max-proposals must be 1..1000')
    from .runner import execute_job
    root = Path(run_dir)
    concepts, obs = inventory(root)
    write_json(root / 'candidate-inventory.json', {'normalization': 'NFKC-whitespace-casefold-v1', 'concepts': concepts})
    write_json(root / 'tag-observations.json', obs)
    if not concepts:
        raise ValueError('No successful explore observations to consolidate')
    # Resume decisions/revisions without deleting raw concepts. New observations rebuild frequencies.
    previous = read_json(root / 'vocab-latest.json') if (root / 'vocab-latest.json').exists() else None
    if previous:
        old = {c['concept_id']: c for c in previous['concepts']}
        for concept in concepts:
            if concept['concept_id'] in old:
                for field in ('name','key','definition','include','exclude','negative_examples','status','merged_into','aliases','supersedes','superseded_by'):
                    if field in old[concept['concept_id']]:
                        concept[field] = old[concept['concept_id']][field]
        known_ids = {c['concept_id'] for c in concepts}
        concepts.extend(c for c in previous['concepts'] if c['concept_id'] not in known_ids)
    # Qwen text reasoning can consume the entire bounded token budget without an answer.
    # Record this explicit provider-template setting in the request and cache identity.
    client = client or Client(endpoint, model, timeout, enable_thinking=False)
    client.discover()
    proposals = []
    db = connect(root)
    try:
        for category in CATEGORIES:
            candidates = [c for c in concepts if c['category'] == category
                          and c['status'] in ('accepted', 'provisional') and not c.get('superseded_by')]
            for offset in range(0, len(candidates), 32):
                if len(proposals) >= max_proposals or (root / 'STOP').exists():
                    break
                chunk = candidates[offset:offset + 32]
                bounded = [{key: c[key] for key in ('concept_id','category','name','definition','include','exclude','examples','frequency','status')} for c in chunk]
                messages = [{'role': 'user', 'content': CONSOLIDATE_PROMPT + dumps(bounded)}]
                maximum = min(12, max_proposals - len(proposals))
                # Include remaining cap in prompt and hash; repair cannot exceed it.
                messages[0]['content'] += f'\nThis chunk permits at most {maximum} proposals.'
                result, _ = execute_job(db, root, client, 'text', 'consolidate', messages,
                    lambda value: validate_proposals(value, chunk, maximum),
                    {'category': category, 'concepts_hash': digest(chunk)}, max_tokens=2048,
                    deployment_revision=deployment_revision)
                for proposal in result['proposals']:
                    proposal = {**proposal, 'status': 'pending', 'policy': 'semantic-proposals-require-explicit-decision'}
                    proposal['proposal_id'] = digest(proposal)
                    if proposal['action'] == 'keep':
                        proposal['status'] = 'accepted'
                        proposal['policy'] = 'automatic-preserve-provisional-only'
                    proposals.append(proposal)
        # Validate across chunks too, including conflicting edges and cycles.
        validate_proposals({'proposals': [{k:v for k,v in p.items() if k not in ('status','policy','proposal_id')} for p in proposals]}, concepts, max_proposals)
    finally:
        db.close()
    if previous:
        prior = {p['proposal_id']: p for p in previous.get('proposals', [])}
        for proposal in proposals:
            if proposal['proposal_id'] in prior:
                proposal['status'] = prior[proposal['proposal_id']]['status']
        current_ids = {p['proposal_id'] for p in proposals}
        proposals.extend(p for pid, p in prior.items() if pid not in current_ids)
    automatic_decisions = [
        {'action': 'normalize', 'concept_id': c['concept_id'], 'original': original,
         'canonical': normalize(original), 'reason': 'Exact NFKC/whitespace/casefold normalization within category',
         'adopter': 'deterministic-normalizer', 'status': 'accepted'}
        for c in concepts for original in c['original_names'] if original != normalize(original)]
    automatic_decisions += [
        {'proposal_id': p['proposal_id'], 'action': 'keep', 'status': 'accepted',
         'reason': p['reason'], 'adopter': 'automatic-preserve-provisional-only'}
        for p in proposals if p['action'] == 'keep' and p['status'] == 'accepted']
    existing_decisions = previous.get('decisions', []) if previous else []
    all_decisions = {digest(d): d for d in existing_decisions + automatic_decisions}
    vocab = {'schema_version': 1, 'frozen': False, 'prompt_version': PROMPT_VERSION,
             'normalization': 'NFKC-whitespace-casefold-v1', 'concepts': concepts, 'proposals': proposals,
             'relations': previous.get('relations', []) if previous else [],
             'revisions': previous.get('revisions', []) if previous else [],
             'decisions': list(all_decisions.values()),
             'notes': ['All originals preserved in tag-observations.json and original_names.',
                       'Only exact normalized duplicates automatically consolidated; semantic proposals remain pending.',
                       'Chunks limited to 32 same-category concepts; cross-chunk synonym discovery is not exhaustive.']}
    write_json(root / 'consolidation-proposals.json', proposals)
    return save_version(root, vocab)


def apply_vocab(run_dir, file):
    root = Path(run_dir)
    vocab = validate_vocab(read_json(file))
    previous = read_json(root / 'vocab-latest.json') if (root / 'vocab-latest.json').exists() else None
    old = {c['concept_id']: c for c in previous['concepts']} if previous else {}
    new = {c['concept_id']: c for c in vocab['concepts']}
    if not set(old) <= set(new):
        raise ValueError('Cannot delete original concepts; use explicit rejected/merged status')
    for cid, concept in old.items():
        if concept['category'] != new[cid]['category'] or not set(concept['original_names']) <= set(new[cid]['original_names']):
            raise ValueError('Cannot change category or erase original names')
    if previous:
        old_proposals = {p['proposal_id']: p for p in previous.get('proposals', [])}
        if not set(old_proposals) <= {p['proposal_id'] for p in vocab.get('proposals', [])}:
            raise ValueError('Cannot erase proposals; decide them explicitly')
        for proposal in vocab.get('proposals', []):
            if proposal['proposal_id'] in old_proposals:
                prior = old_proposals[proposal['proposal_id']]
                for field in ('action', 'source', 'target', 'name', 'interchangeable', 'reason'):
                    if prior.get(field) != proposal.get(field):
                        raise ValueError('Cannot rewrite an existing proposal identity; add an explicit new proposal')
    decisions = list(vocab.get('decisions', []))
    applied = {d['proposal_id']: d['status'] for d in decisions if 'proposal_id' in d}
    proposal_ids = [p['proposal_id'] for p in vocab.get('proposals', [])]
    if len(set(proposal_ids)) != len(proposal_ids):
        raise ValueError('Duplicate proposal reference')
    for proposal in vocab.get('proposals', []):
        if proposal.get('status') not in ('pending', 'accepted', 'rejected'):
            raise ValueError('Invalid proposal decision status')
        if proposal['proposal_id'] in applied and applied[proposal['proposal_id']] != proposal['status']:
            raise ValueError('Conflicting proposal decision; record a new explicit proposal')
        if proposal['status'] == 'pending' or proposal['proposal_id'] in applied:
            continue
        base = {k:v for k,v in proposal.items() if k not in ('status','policy','proposal_id')}
        validate_proposals({'proposals': [base]}, vocab['concepts'])
        action, source = proposal['action'], new[proposal['source']]
        if proposal['status'] == 'accepted':
            if action == 'split':
                raise ValueError('Split needs new concepts plus image reclassification; cannot mechanically apply')
            if action in ('alias','merge'):
                source['status'] = 'merged'
                source['merged_into'] = proposal['target']
                target = new[proposal['target']]
                existing = {normalize(a['name']) for a in target['aliases']}
                for name in [source['name'], *source['original_names']]:
                    if normalize(name) != normalize(target['name']) and normalize(name) not in existing:
                        target['aliases'].append({'name': name, 'language': 'und', 'scope': target['category'],
                            'ambiguous': False, 'policy': 'explicit-reviewed-synonym', 'source_concept_id': source['concept_id']})
                        existing.add(normalize(name))
            elif action == 'reject':
                source['status'] = 'rejected'
            elif action == 'rename':
                source['name'] = proposal['name']
                source['key'] = source['category'] + ':' + normalize(proposal['name'])
            elif action in ('related','broader'):
                relation = {'type': action, 'source': source['concept_id'], 'target': proposal['target']}
                if relation not in vocab.setdefault('relations', []):
                    vocab['relations'].append(relation)
        decisions.append({'proposal_id': proposal['proposal_id'], 'action': action,
                          'status': proposal['status'], 'reason': proposal.get('review_reason', proposal['reason']),
                          'reviewer': proposal.get('reviewer', 'explicit-vocab-reviewer'), 'adopter': 'explicit-vocab-apply'})
    vocab['decisions'] = decisions
    changes = [cid for cid in old if old[cid] != new[cid]]
    if changes:
        vocab.setdefault('revisions', []).append({'previous_hash': digest(previous), 'affected_ids': changes,
                                                'before': [old[cid] for cid in changes], 'after': [new[cid] for cid in changes]})
    validate_vocab(vocab)
    result = save_version(root, vocab)
    db = connect(root)
    try:
        with db:
            for decision in decisions:
                db.execute('INSERT OR IGNORE INTO tag_decisions VALUES(?,?,?)', (digest(decision), time.time(), dumps(decision)))
    finally:
        db.close()
    return result


def freeze_vocab(run_dir, file):
    root = Path(run_dir)
    vocab = read_json(file)
    from .scheduler import exploration_coverage
    if not exploration_coverage(root)['complete']:
        raise ValueError('Freeze blocked: not all manifest images successfully explored; round one is not convergence')
    if any(p.get('status') == 'pending' for p in vocab.get('proposals', [])):
        raise ValueError('Freeze blocked: pending proposals')
    vocab['frozen'] = True
    validate_vocab(vocab)
    return save_version(root, vocab)
