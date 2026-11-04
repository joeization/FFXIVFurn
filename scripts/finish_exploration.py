"""Finish authorized exploration using local Qwen only; NEVER calls final-all.

Resume by reissuing the same command. A failed stage stops with its raw artifacts intact.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffxiv_furniture.classification.state import read_json,write_json,digest
from ffxiv_furniture.classification.scheduler import status
from ffxiv_furniture.classification.vocabulary import apply_vocab,normalize


def equivalence_label(value):
    """Only appearance hedges; never remove color, components or finish qualifiers."""
    value=normalize(value)
    for _ in range(3):
        new=re.sub(r'(?:[- ](?:like|look)| appearance)$','',value).strip()
        if new==value:break
        value=new
    return value


def review_low_risk(root,folder):
    vocab=read_json(root/'vocab-latest.json')
    concepts={c['concept_id']:c for c in vocab['concepts']}
    counts={'strict_equivalents_accepted':0,'other_proposals_deferred_without_merging':0}
    for proposal in vocab.get('proposals',[]):
        if proposal['status']!='pending':continue
        source=concepts[proposal['source']];target=concepts.get(proposal.get('target'))
        equivalent=(proposal['action'] in ('alias','merge') and proposal.get('interchangeable') is True
                    and target is not None and source['category']==target['category']
                    and source.get('status')!='merged' and target.get('status')!='merged'
                    and equivalence_label(source['name'])==equivalence_label(target['name']))
        proposal['reviewer']='deterministic-safety-policy-on-Qwen-proposal'
        proposal['status']='accepted' if equivalent else 'rejected'
        proposal['review_reason']=('Qwen proposed interchangeable names; only appearance hedges differ; qualifiers retained.'
            if equivalent else 'Not adopted automatically: semantic equivalence not established by strict appearance-hedge rule. Preserve source concept and Qwen proposal evidence; may be reconsidered explicitly.')
        counts['strict_equivalents_accepted' if equivalent else 'other_proposals_deferred_without_merging']+=1
    folder.mkdir(parents=True,exist_ok=True)
    candidate=folder/'policy-reviewed-vocab.json';write_json(candidate,vocab)
    result=apply_vocab(root,candidate)
    snapshot=folder/'vocab.json';write_json(snapshot,read_json(root/'vocab-latest.json'))
    write_json(folder/'review-result.json',{'policy':counts,'applied':result,'reviewer_model':'Qwen; deterministic safety adoption only','not_frozen':True})
    return str(snapshot)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',required=True)
    p.add_argument('--endpoint',required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--round3-vocab',required=True)
    a=p.parse_args(argv)
    root=Path(a.run_dir).resolve();work=root/'completion-automation';work.mkdir(exist_ok=True)
    state_path=work/'progress.json'
    state=read_json(state_path) if state_path.exists() else {'completed':{},'attempts':[],
          'final_all_authorized':False,'provider':'local Qwen','endpoint':a.endpoint,'model':a.model}
    if state['endpoint']!=a.endpoint or state['model']!=a.model:raise ValueError('Resume endpoint/model mismatch')
    state['pid']=os.getpid();write_json(state_path,state)
    env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'}
    prefix=[sys.executable,'-u','-m','ffxiv_furniture.classification']
    def run_step(name,args):
        if name in state['completed']:
            print('CACHED_STAGE',name,flush=True);return
        if (root/'STOP').exists():raise RuntimeError('STOP requested')
        for attempt in range(1,3):
            stamp=time.time();log=work/f'{name}-{int(stamp)}-{attempt}.log'
            print('START',name,'attempt',attempt,'log',log,flush=True)
            with log.open('w',encoding='utf-8') as stream:
                result=subprocess.run(prefix+args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
            record={'stage':name,'attempt':attempt,'exit_code':result.returncode,'seconds':time.time()-stamp,'log':str(log)}
            state['attempts'].append(record);write_json(state_path,state)
            if result.returncode==0:
                state['completed'][name]=record;write_json(state_path,state);print('DONE',name,flush=True);return
            print('FAILED',name,log.read_text(encoding='utf-8')[-1500:],flush=True)
        raise RuntimeError(f'Stage {name} failed twice; stopping without fabricated results')
    def visual(name,kind,vocab,seed):
        # Recover a stage that finished inference immediately before its checkpoint write.
        expected={'round3':3,'round4':4}.get(name)
        history=status(root)['rounds']
        found=next((r for r in history if (r['round']==expected if expected else r['kind']==kind)),None)
        if name not in state['completed'] and found and found['complete']:
            state['completed'][name]={'recovered_completed_round':found['round'],'round_hash':found['round_hash']}
            write_json(state_path,state)
        run_step(name,[kind,'--run-dir',str(root),'--vocab',str(vocab),'--seed',str(seed),
          '--execute','--endpoint',a.endpoint,'--model',a.model,'--batch-size','4','--max-batches','1000','--timeout','180'])
    def consolidate(name):
        run_step(name,['consolidate','--run-dir',str(root),'--endpoint',a.endpoint,'--model',a.model,
                       '--max-proposals','1000','--timeout','180'])
        folder=work/name
        if not (folder/'vocab.json').exists():review_low_risk(root,folder)
        return folder/'vocab.json'
    # Only resume/create these bounded authorized stages. No inference of a final pass.
    visual('round3','next-round',Path(a.round3_vocab).resolve(),44)
    v3=consolidate('tags-after-round3')
    visual('round4','next-round',v3,45)
    v4=consolidate('tags-after-round4')
    visual('discover-all-remaining','discover-rest',v4,46)
    final_vocab=consolidate('tags-after-discovery')
    current=status(root)
    if not current['full_library_explored'] or current['unseen_unique_images']!=0:
        raise RuntimeError('Exploration coverage incomplete; not done')
    if any(r['kind']=='final-all' for r in current['rounds']):
        raise RuntimeError('Unexpected final-all plan detected; needs inspection')
    summary={'outcome':'all exploration completed; no final reclassification',
             'status':current,'vocabulary':str(final_vocab),'vocab_hash':digest(read_json(final_vocab)),
             'model':a.model,'taxonomy_model':a.model,'no_remote_model_calls':True,
             'formal_catalog_published':False,'mixed_vocab_versions_preserved':True}
    write_json(work/'completion-report.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
