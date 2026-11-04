"""Reject incomplete IDs and unsupported observations rather than fabricating results."""
import math
from . import CATEGORIES


def text(value, label, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'Invalid {label}')
    return value


def confidence(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('confidence must be finite numeric 0..1')


def validate_items(value, expected_ids, phase='explore', vocab=None):
    if not isinstance(value, dict) or set(value) != {'items'} or not isinstance(value['items'], list):
        raise ValueError('Expected object containing only items array')
    ids = [item.get('id') if isinstance(item, dict) else None for item in value['items']]
    if len(ids) != len(expected_ids) or any(not isinstance(i, str) for i in ids) or set(ids) != set(expected_ids):
        raise ValueError('Response IDs must match exact expected ID set, without duplicates')
    known = {c['key']: c for c in vocab['concepts'] if c['status'] in ('accepted', 'provisional')
             and not c.get('superseded_by')} if vocab else {}
    for item in value['items']:
        if set(item) != {'id', 'visual_description', 'tags', 'proposed_tags', 'uncertain'}:
            raise ValueError('Unexpected/missing item fields')
        text(item['visual_description'], 'visual_description', 600)
        if not isinstance(item['tags'], list) or len(item['tags']) > 6:
            raise ValueError('tags must be array with at most six entries')
        seen = set()
        for tag in item['tags']:
            if not isinstance(tag, dict):
                raise ValueError('Invalid tag')
            fields = {'category', 'name', 'confidence', 'evidence'} if phase == 'explore' else {'key', 'confidence', 'evidence'}
            if set(tag) != fields:
                raise ValueError(f'Unexpected/missing tag fields: expected {sorted(fields)}, got {sorted(tag)}')
            if phase == 'explore':
                if tag['category'] not in CATEGORIES:
                    raise ValueError('Unknown category')
                text(tag['name'], 'tag name', 100)
                from .vocabulary import normalize
                identity = (tag['category'], normalize(tag['name']))
            else:
                if tag['key'] not in known:
                    raise ValueError(f'Unknown controlled vocabulary key: {tag["key"]!r}; remove it from tags and use proposed_tags in guided phase')
                identity = tag['key']
            if identity in seen:
                raise ValueError('Duplicate tag')
            seen.add(identity)
            confidence(tag['confidence'])
            text(tag['evidence'], 'visible evidence', 300)
        proposed = item['proposed_tags']
        if not isinstance(proposed, list) or len(proposed) > 6:
            raise ValueError('Invalid proposed_tags')
        if phase in ('explore', 'final') and proposed:
            raise ValueError('proposed_tags not allowed in explore/final')
        proposed_seen = set()
        for tag in proposed:
            if not isinstance(tag, dict) or set(tag) != {'category', 'name', 'definition', 'reason', 'confidence', 'evidence'}:
                raise ValueError('Invalid proposed tag fields')
            if tag['category'] not in CATEGORIES:
                raise ValueError('Unknown proposed category')
            for field in ('name', 'definition', 'reason', 'evidence'):
                text(tag[field], field, 300)
            confidence(tag['confidence'])
            from .vocabulary import normalize
            identity = (tag['category'], normalize(tag['name']))
            if identity in proposed_seen:
                raise ValueError('Duplicate proposed tag')
            proposed_seen.add(identity)
        if not isinstance(item['uncertain'], list) or len(item['uncertain']) > 12:
            raise ValueError('Invalid uncertain array')
        for note in item['uncertain']:
            text(note, 'uncertainty', 300)
    return value
