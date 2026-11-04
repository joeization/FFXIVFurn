"""Qwen vocabulary adjudication/freeze, then fresh final-all. Restartable; no catalog publish."""
import argparse
from collections import Counter
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffxiv_furniture.config import model_settings
from ffxiv_furniture.classification.client import Client
from ffxiv_furniture.classification.runner import execute_job
from ffxiv_furniture.classification.scheduler import exploration_coverage,schedule
from ffxiv_furniture.classification.state import connect,digest,read_json,write_json
from ffxiv_furniture.classification.vocabulary import validate_vocab,freeze_vocab


def validate_decisions(value,expected):
    if not isinstance(value,dict) or set(value)!={'decisions'} or not isinstance(value['decisions'],list):raise ValueError('Expected decisions array only')
    found=[]
    for d in value['decisions']:
        if not isinstance(d,dict) or set(d)!={'concept_id','status','definition','reason'}:raise ValueError('Decision fields mismatch')
        if d['status'] not in ('accepted','rejected','unresolved'):raise ValueError('Invalid status')
        if not all(isinstance(d[k],str) for k in d):raise ValueError('All decision fields must be strings')
        if not d['reason'].strip() or (d['status']=='accepted' and not d['definition'].strip()):raise ValueError('Reason and accepted definition required')
        if len(d['definition'])>700 or len(d['reason'])>700:raise ValueError('Keep definitions/reasons concise')
        found.append(d['concept_id'])
    if len(found)!=len(expected) or len(set(found))!=len(found) or set(found)!=set(expected):raise ValueError('Expected exactly every supplied concept ID once')
    return value


def decision_format(ids):
    return {'type':'json_schema','json_schema':{'name':'vocabulary_adjudication','strict':True,'schema':{
        'type':'object','additionalProperties':False,'required':['decisions'],'properties':{'decisions':{
        'type':'array','minItems':len(ids),'maxItems':len(ids),'items':{'type':'object','additionalProperties':False,
        'required':['concept_id','status','definition','reason'],'properties':{
        'concept_id':{'type':'string','enum':ids},'status':{'type':'string','enum':['accepted','rejected','unresolved']},
        'definition':{'type':'string','maxLength':700},'reason':{'type':'string','minLength':1,'maxLength':700}}}}}}}}


def finalize(root,client,batch_size=16):
    root=Path(root);work=root/'finalization';work.mkdir(parents=True,exist_ok=True)
    frozen_path=work/'frozen-vocab.json';source_path=work/'source-vocab.json'
    if frozen_path.exists():
        frozen=validate_vocab(read_json(frozen_path))
        if not frozen.get('frozen') or digest(frozen)!=digest(read_json(root/'vocab-latest.json')):raise ValueError('Frozen/latest vocabulary mismatch; do not silently resume')
        return frozen_path
    if not exploration_coverage(root)['complete']:raise ValueError('Full exploration required')
    latest=validate_vocab(read_json(root/'vocab-latest.json'))
    if latest.get('frozen'):
        write_json(frozen_path,latest);return frozen_path
    if source_path.exists():
        if digest(read_json(source_path))!=digest(latest):raise ValueError('Source vocabulary changed during adjudication')
    else:write_json(source_path,latest)
    if any(p.get('status')=='pending' for p in latest.get('proposals',[])):raise ValueError('Pending synonym proposals require explicit decisions before freezing')
    vocab=deepcopy(latest);active=[c for c in vocab['concepts'] if c['status'] not in ('merged','rejected')]
    prior_ids={c['concept_id'] for c in vocab['concepts']};audit=[]
    with closing(connect(root)) as db:
        for offset in range(0,len(active),batch_size):
            if (root/'STOP').exists():raise InterruptedError('STOP requested before freeze')
            chunk=active[offset:offset+batch_size];ids=[c['concept_id'] for c in chunk]
            prompt=('Finalize a visible-appearance vocabulary for anonymous FFXIV furniture thumbnail tagging. '
                'Decide EVERY supplied permanent concept ID exactly once. Only adjudicate usability and write a concise English definition; '
                'never merge, rename, change category/key, invent evidence, or create concepts. '
                'Accept useful visual concepts, including rare ones, when they are observable. Materials/style denote appearance, never proven composition/history. '
                'Do not claim hidden construction, measurements, origin, gameplay function or light emission from colors alone. '
                'Do not overturn an explicit evidence-based unresolved/exclusion note without new evidence. Reject unsupported combined claims; '
                'use unresolved when the supplied evidence cannot support a safe decision. Do not silently broaden or narrow a concept to force acceptance. '
                'If superseded_by exists, reject that superseded concept while preserving its identity/history. '
                'This is not another synonym consolidation round. Keep distinct modifiers. '
                'Return ONLY {"decisions":[{"concept_id":"exact ID","status":"accepted|rejected|unresolved","definition":"concise visible criterion","reason":"evidence/rationale"}]}.\n'
                +json.dumps(chunk,ensure_ascii=False))
            client.response_format=decision_format(ids)
            result,cached=execute_job(db,root,client,'text','finalize',[{'role':'user','content':prompt}],
                lambda value:validate_decisions(value,ids),{'source_vocab_hash':digest(latest),'ids':ids,'finalizer_version':1},max_tokens=7000)
            if result is None:raise RuntimeError('Another owner holds this finalization job')
            by_id={d['concept_id']:d for d in result['decisions']}
            for c in chunk:
                d=by_id[c['concept_id']];before=deepcopy(c);c['status']=d['status']
                if d['definition'].strip():c['definition']=d['definition'].strip()
                audit.append({'concept_id':c['concept_id'],'before':before,'after':deepcopy(c),'reason':d['reason'],'reviewer':client.model})
            write_json(work/'adjudication-audit.json',audit)
            write_json(work/'candidate-vocab.json',vocab)
            print(json.dumps({'stage':'adjudicating','reviewed':offset+len(chunk),'total':len(active),'cached':cached}),flush=True)
    assert {c['concept_id'] for c in vocab['concepts']}==prior_ids
    if any(c['status']=='unresolved' for c in vocab['concepts']):raise ValueError('Unresolved concepts remain; inspect finalization/adjudication-audit.json; final-all NOT started')
    vocab.setdefault('decisions',[]).append({'action':'finalize-visible-definitions','reviewer':client.model,
        'source_vocab_hash':digest(latest),'audit_file':str((work/'adjudication-audit.json').resolve()),'audit_hash':digest(audit),
        'policy':'No merges, renames, category changes, identity deletion, or unsupported claims'})
    candidate=work/'candidate-vocab.json';write_json(candidate,vocab)
    # Native freeze gate rechecks full exploration, all decisions, definitions and merge targets.
    result=freeze_vocab(root,candidate)
    frozen=read_json(root/'vocab-latest.json');validate_vocab(frozen);assert frozen['frozen']
    write_json(frozen_path,frozen)
    write_json(work/'freeze-report.json',{'result':result,'statuses':dict(Counter(c['status'] for c in frozen['concepts'])),
        'audit_hash':digest(audit),'model':client.model,'source_hash':digest(latest),'frozen_hash':digest(frozen)})
    return frozen_path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',default=str(ROOT/'runs/round1'))
    p.add_argument('--endpoint')
    p.add_argument('--model')
    p.add_argument('--stage',choices=['both','finalize','classify'],default='both')
    p.add_argument('--batch-size',type=int,default=4)
    a=p.parse_args();a.endpoint,a.model=model_settings(a.endpoint,a.model);root=Path(a.run_dir);client=Client(a.endpoint,a.model,timeout=240,enable_thinking=False,structured_output=True)
    client.discover()
    progress=root/'finalization/progress.json'
    try:
        write_json(progress,{'stage':a.stage,'started_at':time.time(),'model':a.model})
        frozen=finalize(root,client) if a.stage!='classify' else root/'finalization/frozen-vocab.json'
        print(json.dumps({'stage':'frozen','path':str(frozen),'hash':digest(read_json(frozen))}),flush=True)
        if a.stage=='finalize':return
        # Native scheduler creates an immutable full-manifest plan and fresh vision jobs, never old answer mapping.
        result=schedule(root,'final-all',vocab=frozen,execute=True,endpoint=a.endpoint,model=a.model,
            batch_size=a.batch_size,max_batches=10000,timeout=240)
        plan=read_json(root/f"round-{result['round']:03d}.json")
        with closing(connect(root)) as db:
            rows=db.execute("SELECT p.image_hash,p.data,j.input FROM predictions p JOIN jobs j ON j.id=p.job_id WHERE j.phase='final' AND j.status='succeeded'").fetchall()
            predictions={h:json.loads(data) for h,data,inp in rows if json.loads(inp)['metadata'].get('round_hash')==plan['round_hash']}
        expected={r['image_hash'] for r in plan['images']}
        complete=set(predictions)==expected
        write_json(root/'finalization/final-predictions.json',predictions)
        summary={'stage':'complete' if complete else 'stopped-incomplete','completed_unique_images':len(predictions),
            'expected_unique_images':len(expected),'round_hash':plan['round_hash'],'vocab_hash':plan['vocab_hash'],
            'result':result,'published_to_catalog':False,'finished_at':time.time()}
        write_json(progress,summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
        if not complete:raise RuntimeError('Final pass incomplete; rerun exact command after checking STOP/errors')
    except Exception as exc:
        write_json(root/'finalization/last-error.json',{'error':str(exc),'time':time.time()})
        print('BLOCKED: '+str(exc),file=sys.stderr,flush=True);raise


if __name__=='__main__':main()
