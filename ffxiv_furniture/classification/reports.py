"""Machine-readable and compact human-readable pilot accounting."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from . import CATEGORIES
from .state import connect, read_json, write_json
from .vocabulary import inventory, observations
from .scheduler import exploration_coverage, round_history, status


def report(run_dir):
    root = Path(run_dir)
    manifest = read_json(root / 'manifest.json')
    round_data = round_history(root)[-1]
    concepts, obs = inventory(root)
    successful = set(exploration_coverage(root)['successful_image_hashes'])
    selected = {r['image_hash'] for plan in round_history(root) if plan.get('phase') != 'final' for r in plan['images']}
    all_images = {r['image_hash'] for r in manifest['assets']}
    coverage = defaultdict(lambda: {'eligible_assets': 0, 'eligible_unique_images': set(),
                                    'selected_unique_images': set(), 'successful_unique_images': set()})
    for row in manifest['assets']:
        key = (row['scope'], row['source_category'])
        bucket = coverage[key]
        bucket['eligible_assets'] += 1
        bucket['eligible_unique_images'].add(row['image_hash'])
        if row['image_hash'] in selected:
            bucket['selected_unique_images'].add(row['image_hash'])
        if row['image_hash'] in successful:
            bucket['successful_unique_images'].add(row['image_hash'])
    coverage_rows = []
    for key, value in sorted(coverage.items()):
        counts = {k:len(v) if isinstance(v,set) else v for k,v in value.items()}
        coverage_rows.append({'scope': key[0], 'source_category': key[1], **counts,
                              'unseen_unique_images': len(value['eligible_unique_images'] - successful)})
    db = connect(root)
    try:
        jobs = [dict(row) for row in db.execute('SELECT id,kind,phase,model,prompt_version,status,attempts,error FROM jobs ORDER BY id')]
        usage = Counter()
        elapsed = 0
        responses = []
        for row in db.execute('SELECT job_id,attempt,elapsed,usage,error FROM responses ORDER BY job_id,attempt'):
            responses.append(dict(row))
            elapsed += row['elapsed']
            values = json.loads(row['usage']) if row['usage'] else None
            if isinstance(values, dict):
                for key, value in values.items():
                    if type(value) in (int, float):
                        usage[key] += value
        inputs = [json.loads(row[0]) for row in db.execute('SELECT input FROM jobs')]
    finally:
        db.close()
    vocab = read_json(root / 'vocab-latest.json') if (root / 'vocab-latest.json').exists() else None
    frequency = [{'concept_id': c['concept_id'], 'category': c['category'], 'name': c['name'],
                  'original_names': c['original_names'], **c['frequency'], 'example_ids': [x['id'] for x in c['examples']]}
                 for c in sorted(concepts, key=lambda c: (-c['frequency']['unique_images'], c['key']))]
    tag_categories = {category: {'candidate_concepts': sum(c['category']==category for c in concepts),
                    'unique_images_with_tags': len({o['image_hash'] for o in obs if o['category']==category}),
                    'observations': sum(o['category']==category for o in obs)} for category in CATEGORIES}
    summary = {'staging_only': True, 'run_dir': str(root.resolve()), 'round': round_data['round'],
               'scheduler': status(root),
               'manifest_hash': manifest['manifest_hash'], 'round_hash': round_data['round_hash'],
               'eligible_assets': len(manifest['assets']), 'eligible_unique_images': len(all_images),
               'selected_unique_images': len(selected), 'successful_unique_images': len(successful),
               'selected_incomplete_images': len(selected - successful), 'unseen_unique_images': len(all_images - successful),
               'round_complete': selected <= successful, 'full_library_complete': all_images <= successful,
               'source_coverage': coverage_rows, 'tag_categories': tag_categories, 'candidate_tag_frequency': frequency,
               'rare_candidates': [f for f in frequency if f['unique_images'] == 1],
               'job_status_counts': dict(Counter(j['status'] for j in jobs)), 'jobs': jobs,
               'usage': dict(usage), 'attempt_elapsed_seconds': elapsed, 'responses': responses,
               'repair_or_rerun_attempts': sum(max(0,j['attempts']-1) for j in jobs),
               'proposal_status_counts': dict(Counter(p['status'] for p in vocab.get('proposals', []))) if vocab else {},
               'concept_status_counts': dict(Counter(c['status'] for c in vocab['concepts'])) if vocab else {},
               'reproducibility_warnings': ['Server weight revision not pinned'] if any(not i.get('deployment_revision') for i in inputs) else [],
               'quality_notes': ['Confidence is uncalibrated; no gold labels, no accuracy claimed.',
                                 'Global exploration coverage includes all immutable rounds; final is a separate fresh pass.',
                                 'Shared thumbnail mappings retained; source-category context not blindly reused.',
                                 'Unguided controls are already unguided in explore; anchors are development consistency set.']}
    write_json(root / 'report.json', summary)
    lines = ['# Classification staging report', '',
             f"- Staging only; {summary['successful_unique_images']}/{len(selected)} selected unique images successful.",
             f"- Manifest: {len(manifest['assets'])} candidates / {len(all_images)} unique images; all-library completion: {summary['full_library_complete']}.",
             f"- Jobs: {summary['job_status_counts']}; usage: {dict(usage)}.",
             f"- Proposals: {summary['proposal_status_counts']}; concepts: {summary['concept_status_counts']}.",
             '', '## Visual tag categories', '', '| Category | Concepts | Unique images | Observations |', '|---|---:|---:|---:|']
    for key, values in tag_categories.items():
        lines.append(f"| {key} | {values['candidate_concepts']} | {values['unique_images_with_tags']} | {values['observations']} |")
    lines += ['', '## Source coverage', '', '| Scope / Category | Eligible assets | Unique images | Selected | Success |', '|---|---:|---:|---:|---:|']
    for row in coverage_rows:
        lines.append(f"| {row['scope']} / {row['source_category']} | {row['eligible_assets']} | {row['eligible_unique_images']} | {row['selected_unique_images']} | {row['successful_unique_images']} |")
    lines += ['', '## Candidate frequency (unique images)', '', '| Category | Tag | Images | Candidates | Source strata |', '|---|---|---:|---:|---:|']
    for row in frequency:
        name = row['name'].replace('|','\\|').replace('\n',' ')
        lines.append(f"| {row['category']} | {name} | {row['unique_images']} | {row['furniture_candidates']} | {row['source_strata']} |")
    lines += ['', '## Caveats', ''] + ['- '+n for n in summary['quality_notes'] + summary['reproducibility_warnings']]
    (root / 'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return summary
