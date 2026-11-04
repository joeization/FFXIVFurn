"""Retire unresolved concepts by explicit user policy; fresh visual recheck using accepted tags."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ffxiv_furniture.config import model_settings
from ffxiv_furniture.classification.client import Client
from ffxiv_furniture.classification.runner import classify
from ffxiv_furniture.classification.scheduler import exploration_records,_pool
from ffxiv_furniture.classification.state import read_json,write_json,digest,connect
from ffxiv_furniture.classification.vocabulary import validate_vocab,freeze_vocab,normalize


def select_affected(vocab,records):
    unresolved=[c for c in vocab['concepts'] if c['status']=='unresolved']
    ids={c['concept_id'] for c in unresolved};keys={c['key'] for c in unresolved}
    names={(c['category'],normalize(n)) for c in unresolved for n in [c['name'],*c['original_names']]}
    affected={h for c in unresolved for h in c.get('images',[])}
    for record in records:
        by_key={c['key']:c['concept_id'] for c in (record.get('vocabulary') or {}).get('concepts',[])}
        for tag in record['data']['tags']:
            if tag.get('key') in keys or by_key.get(tag.get('key')) in ids or (tag.get('category'),normalize(tag.get('name',''))) in names:
                affected.add(record['image_hash'])
    return unresolved,affected


def main():
    endpoint,model=model_settings()
    root=ROOT/'runs/round1';work=root/'finalization/unresolved-recheck';work.mkdir(parents=True,exist_ok=True)
    original=validate_vocab(read_json(root/'finalization/candidate-vocab.json'))
    unresolved,affected=select_affected(original,exploration_records(root))
    if not unresolved:raise ValueError('No unresolved concepts in candidate; refuse ambiguous rerun')
    pool={r['image_hash']:r for r in _pool(read_json(root/'manifest.json'))}
    if not affected or not affected<=set(pool):raise ValueError('Missing affected image mappings')
    vocab=deepcopy(original)
    for c in vocab['concepts']:
        if c['status']=='unresolved':
            c['status']='rejected'
            vocab.setdefault('decisions',[]).append({'action':'retire-unresolved','concept_id':c['concept_id'],
                'status':'rejected','reviewer':'explicit-user-policy','reason':'User requested affected furniture be reclassified by Qwen using existing accepted tags only; no synonym substitution or new concepts.'})
    vocab.setdefault('decisions',[]).append({'action':'finalize-visible-definitions','reviewer':'qwen-trial117',
        'source_vocab_hash':digest(read_json(root/'finalization/source-vocab.json')),
        'adjudication_audit_hash':digest(read_json(root/'finalization/adjudication-audit.json')),
        'user_policy':'Retire unresolved concepts, reclassify affected images under accepted vocabulary; preserve permanent concept IDs and originals.'})
    vocab['frozen']=True
    validate_vocab(vocab)
    write_json(work/'recheck-vocab.json',vocab)
    images=[deepcopy(pool[h]) for h in sorted(affected)]
    for i,r in enumerate(images,1):r['anon_id']=f'URECHECK{i:04d}'
    plan={'kind':'unresolved-image-recheck','phase':'final','images':images,'vocabulary':vocab,
          'vocab_hash':digest(vocab),'retired_concept_ids':[c['concept_id'] for c in unresolved]}
    plan['round_hash']=digest(plan)
    if (work/'plan.json').exists() and read_json(work/'plan.json')!=plan:raise ValueError('Immutable recheck plan changed')
    write_json(work/'plan.json',plan)
    client=Client(endpoint,model,240,enable_thinking=False,structured_output=True)
    client.discover()
    result=classify(root,client.endpoint,client.model,batch_size=4,max_batches=1000,timeout=240,phase='final',vocab=vocab,
                    client=client,round_data=plan,role='unresolved-recheck')
    with closing(connect(root)) as db:
        rows=db.execute("SELECT p.image_hash,p.data,j.input FROM predictions p JOIN jobs j ON j.id=p.job_id WHERE j.phase='final' AND j.status='succeeded' ORDER BY j.finished_at,j.id,p.anon_id").fetchall()
    predictions={h:json.loads(data) for h,data,inp in rows if json.loads(inp)['metadata'].get('round_hash')==plan['round_hash']}
    if set(predictions)!=affected:raise ValueError('Affected images not all reclassified; no global freeze')
    accepted={c['key'] for c in vocab['concepts'] if c['status']=='accepted'}
    assert all(t['key'] in accepted for p in predictions.values() for t in p['tags'])
    warnings=[]
    for row in images:
        tags={t['key'] for t in predictions[row['image_hash']]['tags']}
        if row['representative']['source_category']=='Furniture/Table' and 'form:bed' in tags:
            warnings.append({'image_hash':row['image_hash'],'asset_key':row['representative']['asset_key'],
                'issue':'Visual model still interprets table thumbnail as bed; authoritative Table category must not be overwritten.',
                'requires_manual_qa_before_catalog_publish':True})
    write_json(work/'predictions.json',predictions)
    write_json(work/'report.json',{'affected_unique_images':len(affected),'retired_concepts':[c['key'] for c in unresolved],
         'existing_accepted_tags_only':True,'fresh_images':True,'result':result,'predictions':predictions,'quality_warnings':warnings})
    # Publish the frozen vocabulary only AFTER the bounded fresh-image recheck succeeds.
    write_json(work/'candidate-for-freeze.json',vocab)
    freeze_result=freeze_vocab(root,work/'candidate-for-freeze.json')
    frozen=read_json(root/'vocab-latest.json')
    assert frozen.get('frozen') and digest(frozen)==digest(vocab)
    write_json(root/'finalization/frozen-vocab.json',frozen)
    write_json(root/'finalization/freeze-report.json',{'result':freeze_result,'frozen_hash':digest(frozen),
         'unresolved_remaining':0,'user_policy_recheck_report':str((work/'report.json').resolve())})
    print(json.dumps({'reclassified_images':len(predictions),'retired_concepts':[c['key'] for c in unresolved],
         'accepted_tags':len(accepted),'frozen_hash':digest(frozen),'frozen':True},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
