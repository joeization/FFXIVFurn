"""Lossless taxonomy views and evidence-linked category refactors (no inference)."""
from collections import Counter, defaultdict
from copy import deepcopy
from .state import digest


def resolve_id(vocab, concept_id):
    """Resolve reviewed synonyms, but never silently traverse a category refactor."""
    by_id = {c['concept_id']: c for c in vocab['concepts']}
    visited = set()
    while True:
        if concept_id not in by_id or concept_id in visited:
            raise ValueError('Unknown/cyclic concept reference')
        visited.add(concept_id)
        concept = by_id[concept_id]
        if not concept.get('merged_into'):
            return concept_id
        concept_id = concept['merged_into']


def active_id(vocab, concept_id):
    """Resolve explicitly accepted refactors as well as same-category synonyms."""
    by_id = {c['concept_id']: c for c in vocab['concepts']}
    visited = set()
    while True:
        if concept_id in visited:
            raise ValueError('Mixed synonym/reclassification cycle')
        visited.add(concept_id)
        resolved = resolve_id(vocab, concept_id)
        next_id = by_id[resolved].get('superseded_by')
        if not next_id:
            return resolved
        concept_id = next_id


def grouping(vocab, observations=()):
    """Canonical grouping view; raw concept membership and evidence never disappear."""
    groups = defaultdict(list)
    for concept in vocab['concepts']:
        groups[active_id(vocab, concept['concept_id'])].append(concept)
    obs = defaultdict(list)
    for observation in observations:
        obs[active_id(vocab, observation['concept_id'])].append(observation)
    result = []
    for target, members in sorted(groups.items()):
        canonical = next(c for c in members if c['concept_id'] == target)
        evidence = obs[target]
        result.append({'concept_id': target, 'category': canonical['category'], 'name': canonical['name'],
                       'status': canonical['status'], 'members': [c['concept_id'] for c in members],
                       'names': sorted({n for c in members for n in [c['name'], *c['original_names']]}),
                       'unique_images': len({o['image_hash'] for o in evidence}),
                       'observation_count': len(evidence)})
    return result


def counts(vocab):
    concepts = vocab['concepts']
    active = [c for c in concepts if c['status'] in ('accepted', 'provisional') and not c.get('superseded_by')]
    return {'concept_records': len(concepts), 'active_concepts': len(active),
            'statuses': dict(sorted(Counter(c['status'] for c in concepts).items())),
            'active_categories': dict(sorted(Counter(c['category'] for c in active).items())),
            'alias_entries': sum(len(c['aliases']) for c in concepts),
            'merged_concepts': sum(c['status'] == 'merged' for c in concepts),
            'superseded_concepts': sum(bool(c.get('superseded_by')) for c in concepts),
            'proposal_statuses': dict(sorted(Counter(p['status'] for p in vocab.get('proposals', [])).items())),
            'relations': len(vocab.get('relations', [])), 'decisions': len(vocab.get('decisions', []))}


def reclassify(vocab, source_id, category, observations, reason, reviewer='agent'):
    """Create a new category identity, retaining source and exact observation links.

    This changes the taxonomy, not model predictions. The source stays provisional
    and inspectable, but is excluded from active tagging via superseded_by.
    """
    from . import CATEGORIES
    from .vocabulary import normalize, validate_vocab
    if category not in CATEGORIES or not reason.strip() or not reviewer.strip():
        raise ValueError('Invalid reclassification decision')
    source = next(c for c in vocab['concepts'] if c['concept_id'] == source_id)
    if source['category'] == category or source.get('merged_into') or source.get('superseded_by'):
        raise ValueError('Reclassification requires an active source and different category')
    evidence = [deepcopy(o) for o in observations if o['concept_id'] == source_id]
    if not evidence:
        raise ValueError('Category change requires source observations')
    target_id = 'c_' + digest([category, normalize(source['name'])])[:24]
    if any(c['concept_id'] == target_id for c in vocab['concepts']):
        raise ValueError('Target already exists; explicit reconciliation required')
    target = deepcopy(source)
    target.update(concept_id=target_id, category=category, key=category + ':' + normalize(source['name']),
                  aliases=[], original_names=list(source['original_names']), supersedes=[source_id])
    source['superseded_by'] = target_id
    vocab['concepts'].append(target)
    relation = {'type': 'reclassify', 'source': source_id, 'target': target_id,
                'reason': reason, 'reviewer': reviewer, 'status': 'accepted',
                'source_observations': evidence}
    vocab.setdefault('relations', []).append(relation)
    vocab.setdefault('decisions', []).append({'action': 'reclassify', **relation})
    validate_vocab(vocab)
    return target_id


def materialize_observations(vocab, observations):
    """Derived staging tags retain raw identity/category and untouched evidence."""
    by_id = {c['concept_id']: c for c in vocab['concepts']}
    result = []
    for raw in observations:
        canonical = by_id[active_id(vocab, raw['concept_id'])]
        result.append({**deepcopy(raw), 'raw_concept_id': raw['concept_id'], 'raw_category': raw['category'],
                       'canonical_concept_id': canonical['concept_id'], 'canonical_key': canonical['key'],
                       'canonical_category': canonical['category']})
    return result


def validate_links(vocab):
    """Validate semantic references independently of schema field validation."""
    by_id = {c['concept_id']: c for c in vocab['concepts']}
    relations = vocab.get('relations', [])
    seen = set()
    reclassified = {}
    for relation in relations:
        identity = (relation.get('type'), relation.get('source'), relation.get('target'))
        kind, source, target = identity
        if identity in seen or source not in by_id or target not in by_id or source == target:
            raise ValueError('Duplicate/invalid relation reference')
        seen.add(identity)
        if kind not in ('related', 'broader', 'reclassify'):
            raise ValueError('Invalid relation type')
        if kind == 'reclassify':
            if (by_id[source]['category'] == by_id[target]['category'] or
                    by_id[source].get('superseded_by') != target or
                    source not in by_id[target].get('supersedes', []) or
                    relation.get('status') != 'accepted' or not relation.get('reviewer') or
                    not relation.get('reason')):
                raise ValueError('Unsafe category refactor')
            evidence = relation.get('source_observations')
            if not evidence or any(o.get('concept_id') != source or not o.get('evidence') or
                                   not o.get('image_hash') or o.get('category') != by_id[source]['category']
                                   for o in evidence):
                raise ValueError('Category refactor requires exact source observations')
            if source in reclassified:
                raise ValueError('Conflicting reclassification')
            reclassified[source] = target
    for concept in by_id.values():
        if concept.get('superseded_by') and reclassified.get(concept['concept_id']) != concept['superseded_by']:
            raise ValueError('Superseded concept requires reclassification relation')
        supersedes = concept.get('supersedes', [])
        if len(set(supersedes)) != len(supersedes) or any(reclassified.get(s) != concept['concept_id'] for s in supersedes):
            raise ValueError('Invalid/duplicate supersedes reference')
    for source in reclassified:
        visited = set()
        while source in reclassified:
            if source in visited:
                raise ValueError('Reclassification cycle')
            visited.add(source)
            source = reclassified[source]
    for concept_id in by_id:
        active_id(vocab, concept_id)
    # Canonical IDs/keys cannot be ambiguously claimed by aliases. An ambiguous
    # alias may be recorded as evidence but is never eligible for auto lookup.
    owners = defaultdict(set)
    from .vocabulary import normalize
    for concept in by_id.values():
        owners[(concept['category'], normalize(concept['name']))].add(resolve_id(vocab, concept['concept_id']))
    alias_seen = set()
    for concept in by_id.values():
        for alias in concept['aliases']:
            if not isinstance(alias, dict) or not isinstance(alias.get('name'), str) or not alias['name'].strip():
                raise ValueError('Invalid alias')
            if alias.get('scope') != concept['category'] or type(alias.get('ambiguous')) is not bool:
                raise ValueError('Alias requires explicit category scope and ambiguity')
            source_id = alias.get('source_concept_id')
            if source_id and (source_id not in by_id or resolve_id(vocab, source_id) != resolve_id(vocab, concept['concept_id'])):
                raise ValueError('Alias provenance must resolve to its canonical target')
            identity = (concept['concept_id'], normalize(alias['name']))
            if identity in alias_seen:
                raise ValueError('Duplicate alias reference')
            alias_seen.add(identity)
            if not alias['ambiguous']:
                owners[(concept['category'], normalize(alias['name']))].add(resolve_id(vocab, concept['concept_id']))
    if any(len(ids) > 1 for ids in owners.values()):
        raise ValueError('Alias has conflicting canonical targets')
    return vocab
