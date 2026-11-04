"""Bounded, restartable jobs with raw attempts and atomic validated predictions."""
import base64
import hashlib
from pathlib import Path
import time
from . import PROMPT_VERSION
from .client import Client, parse_response
from .prompts import visual_prompt
from .state import cached_job, claim, connect, digest, dumps, read_json, write_json
from .validation import validate_items


def execute_job(db, run_dir, client, kind, phase, messages, validator, metadata,
                image_rows=(), max_tokens=4096, deployment_revision=None):
    identity = {'kind': kind, 'phase': phase, 'model': client.model, 'endpoint': client.endpoint,
                'prompt_version': PROMPT_VERSION, 'messages': messages, 'metadata': metadata,
                'temperature': 0, 'max_tokens': max_tokens, 'deployment_revision': deployment_revision}
    if getattr(client, 'enable_thinking', None) is not None:
        identity['chat_template_kwargs'] = {'enable_thinking': client.enable_thinking}
    if getattr(client, 'response_format', None) is not None:
        identity['response_format'] = client.response_format
    job_id = digest(identity)
    cached = cached_job(db, job_id)
    if cached is not None:
        return cached, True
    if not claim(db, job_id, kind, phase, client.model, identity, PROMPT_VERSION,
                 lease=max(900, client.timeout * 8)):
        return cached_job(db, job_id), True
    # Do not persist base64 repeatedly in SQLite; the hash identifies exact payload, inputs recorded in raw request file.
    write_json(Path(run_dir) / 'requests' / f'{job_id}.json', identity)
    conversation = list(messages)
    try:
        for repair in range(2):
            started = time.monotonic()
            raw, error = None, None
            try:
                raw = client.chat(conversation, max_tokens=max_tokens)
                result = validator(parse_response(raw))
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                error = str(exc)
            except Exception as exc:
                error = str(exc)
                raise
            finally:
                attempt = db.execute('SELECT attempts FROM jobs WHERE id=?', (job_id,)).fetchone()[0] + 1
                envelope = {'job_id': job_id, 'attempt': attempt, 'raw': raw, 'error': error,
                            'elapsed': time.monotonic() - started, 'actual_images_sent': len(image_rows)}
                write_json(Path(run_dir) / 'responses' / f'{job_id}-{attempt:03d}.json', envelope)
                usage = raw.get('usage') if isinstance(raw, dict) else None
                with db:
                    db.execute('INSERT INTO responses VALUES(?,?,?,?,?,?)',
                               (job_id, attempt, envelope['elapsed'], dumps(raw), dumps(usage), error))
                    db.execute('UPDATE jobs SET attempts=? WHERE id=?', (attempt, job_id))
            if error is None:
                with db:
                    for item in result.get('items', []):
                        row = next(r for r in image_rows if r['anon_id'] == item['id'])
                        db.execute('INSERT OR REPLACE INTO predictions VALUES(?,?,?,?)',
                                   (job_id, item['id'], row['image_hash'], dumps(item)))
                    db.execute("UPDATE jobs SET status='succeeded',finished_at=?,result=?,error=NULL WHERE id=?",
                               (time.time(), dumps(result), job_id))
                return result, False
            if repair == 0:
                # Same image-bearing prompt, one format repair; never use reasoning_content as answer.
                content = raw.get('choices', [{}])[0].get('message', {}).get('content', '') if isinstance(raw, dict) else ''
                conversation += [{'role': 'assistant', 'content': content or ''},
                                 {'role': 'user', 'content': 'Repair JSON once. Validation error: ' + error +
                                  '. Recheck exact IDs/schema against original supplied images. Return only corrected JSON.'}]
            else:
                raise ValueError('JSON validation failed after one repair: ' + error)
    except Exception as exc:
        with db:
            db.execute("UPDATE jobs SET status='failed',finished_at=?,error=? WHERE id=?",
                       (time.time(), str(exc), job_id))
        raise


def classify(run_dir, endpoint, model, batch_size=4, max_batches=None, timeout=180,
             phase='explore', vocab=None, deployment_revision=None, client=None,
             round_data=None, role='main'):
    if batch_size < 1 or batch_size > 16 or (max_batches is not None and max_batches < 1):
        raise ValueError('batch-size must be 1..16 and max-batches positive')
    if phase not in ('explore', 'guided', 'final'):
        raise ValueError('Unknown phase')
    root = Path(run_dir)
    round_data = round_data or read_json(root / 'round-001.json')
    vocabulary = vocab if isinstance(vocab, dict) else read_json(vocab) if vocab else None
    if phase != 'explore':
        from .vocabulary import validate_vocab
        if not vocabulary:
            raise ValueError('guided/final require --vocab')
        validate_vocab(vocabulary)
        if phase == 'final' and not vocabulary.get('frozen'):
            raise ValueError('final requires frozen vocabulary')
    elif vocabulary:
        raise ValueError('explore must not receive vocabulary')
    # Final is deliberately limited to selected round images, not silently the full library.
    client = client or Client(endpoint, model, timeout, enable_thinking=False if phase != 'explore' else None,
                              structured_output=phase != 'explore')
    db = connect(root)
    completed, cached = 0, 0
    try:
        rows = round_data['images']
        for offset in range(0, len(rows), batch_size):
            if (root / 'STOP').exists():
                break
            if max_batches is not None and completed >= max_batches:
                break
            batch = rows[offset:offset + batch_size]
            content = [{'type': 'text', 'text': visual_prompt(phase, vocabulary)}]
            for row in batch:
                representative = row['representative']
                data = Path(representative['image_path']).read_bytes()
                if hashlib.sha256(data).hexdigest() != row['image_hash']:
                    raise ValueError('Image changed since prepare; create a new run')
                # Only these metadata are exposed to VLM. No names, paths, scope or asset keys.
                content += [{'type': 'text', 'text': dumps({'id': row['anon_id'], 'source_category': representative['source_category']})},
                            {'type': 'image_url', 'image_url': {'url': 'data:' + representative['mime_type'] + ';base64,' + base64.b64encode(data).decode('ascii')}}]
            messages = [{'role': 'user', 'content': content}]
            expected = [r['anon_id'] for r in batch]
            if getattr(client, 'structured_output', False) is True:
                from .contracts import visual_response_format
                client.response_format = visual_response_format(expected, phase, vocabulary)
            metadata = {'round_hash': round_data['round_hash'], 'ids': expected,
                        'vocab_hash': digest(vocabulary) if vocabulary else None,
                        'image_hashes': [r['image_hash'] for r in batch]}
            if vocabulary and 'vocabulary' not in round_data:
                # Legacy classify --phase guided has no scheduler snapshot; retain its exact dictionary.
                metadata['vocabulary_snapshot'] = vocabulary
            if role != 'main':
                metadata['role'] = role
            if not getattr(client, '_astra_discovered', False):
                client.discover()
                client._astra_discovered = True
            _, hit = execute_job(db, root, client, 'visual', phase, messages,
                                 lambda value: validate_items(value, expected, phase, vocabulary), metadata,
                                 batch, deployment_revision=deployment_revision)
            cached += int(hit)
            completed += int(not hit)
    finally:
        db.close()
    return {'new_batches': completed, 'cached_batches': cached, 'phase': phase,
            'scope': round_data.get('kind', 'selected round images only'), 'deployment_revision': deployment_revision,
            'reproducibility_warning': None if deployment_revision else 'Server weight revision not recorded'}
