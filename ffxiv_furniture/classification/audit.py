"""Conservative, read-only final-tag review flags; never rewrite classifications."""
from collections import Counter
from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from .state import digest,read_json,write_json

POLICY_VERSION='source-name-conflicts-v1'
# Exact canonical object-type tags only. Generic geometry, color/material/style and
# ornaments are NOT treated as furniture function or mutually exclusive evidence.
FORM_FAMILIES={
 'form:bed':'bed','form:bunk bed':'bed',
 'form:sofa':'sofa','form:bench':'seat','form:lounge chair':'seat','form:high-back chair':'seat',
 'form:table':'table','form:rectangular table':'table','form:low rectangular table':'table',
 'form:cabinet':'cabinet','form:tall cabinet':'cabinet','form:connected cabinets':'cabinet',
 'form:shelving unit':'shelf','form:open rectangular shelving':'shelf',
 'form:grand piano':'instrument','form:stringed instrument':'instrument',
 'form:lamp':'lamp',
}
CATEGORY_CONFLICTS={
 'Furniture/Table':{'bed','sofa','seat'},
 'Furniture/Chair':{'bed','table','cabinet','shelf','instrument'},
 'Furniture/Cabinet':{'bed','sofa','seat','table','instrument'},
 'Furniture/Shelf':{'bed','sofa','seat','instrument'},
 'Furniture/Rug':{'bed','sofa','seat','table','cabinet','shelf','instrument'},
 'Furniture/Wall-Mounted':{'bed','sofa','seat','table','cabinet'},
}
NAME_PATTERNS={
 'bed':r'\b(?:bed|beds|bunkbed)\b',
 'sofa':r'\b(?:sofa|couch|settee)\b',
 'seat':r'\b(?:chair|armchair|bench|stool|armoire-seat)\b',
 'table':r'\b(?:table|desk|counter)\b',
 'cabinet':r'\b(?:cupboard|cabinet|wardrobe|armoire|dresser)\b',
 'shelf':r'\b(?:bookshelf|bookcase|shelving|shelf|shelves)\b',
 'instrument':r'\b(?:piano|harpsichord|organ|guitar|harp)\b',
 'lamp':r'\b(?:lamp|lantern|chandelier|sconce)\b',
 'rug':r'\b(?:rug|carpet|doormat|mat)\b',
}
# Multiple objects/depictions/composites are deliberately not resolved by names.
NAME_AMBIGUITY=r'\b(?:miniature|replica|toy|figurine|doll|stuffed|portrait|painting|poster|mural|imitation|model)\b'
MAJOR_FAMILIES={'bed','sofa','seat','table','cabinet','shelf','instrument'}
COMPATIBLE={'sofa':{'sofa','seat'},'seat':{'sofa','seat'}}


def name_families(name):
    if not isinstance(name,str) or re.search(NAME_AMBIGUITY,name,re.I):return set()
    return {family for family,pattern in NAME_PATTERNS.items() if re.search(pattern,name,re.I)}


def check_asset(asset,prediction,accepted_keys=None):
    """Return suspicions, NOT a correctness verdict. Source category remains authoritative."""
    issues=[];tags=prediction.get('tags',[]);source=asset.get('source_category','');name=asset.get('name','')
    named=name_families(name)
    for tag in tags:
        key=tag['key'];family=FORM_FAMILIES.get(key)
        if accepted_keys is not None and key not in accepted_keys:
            issues.append({'rule':'inactive_or_unknown_tag','priority':'high','tag':key,
                'reason':'Tag is not accepted in the exact final vocabulary snapshot.'})
        if not family:continue
        # A sofa-bed or table/chair composite named explicitly is not an obvious mismatch.
        if len(named)>1 and family in named:continue
        if family in CATEGORY_CONFLICTS.get(source,set()):
            issues.append({'rule':'category_object_conflict','priority':'high' if source=='Furniture/Table' and family=='bed' else 'medium',
                'tag':key,'reason':f'Object-type tag {key} conflicts with source category {source}; may be a misread thumbnail or a depicted/component object.'})
        if len(named)==1:
            expected=next(iter(named));compatible=COMPATIBLE.get(expected,{expected})
            if family in MAJOR_FAMILIES and family not in compatible:
                issues.append({'rule':'name_object_conflict','priority':'medium','tag':key,
                    'reason':f'Name {name!r} suggests {expected}, while the visual tag suggests {family}; name is only a review signal, not a proof.'})
    return issues


def audit_final(run_dir,output_dir,*,allow_partial=False,round_number=None):
    root=Path(run_dir);out=Path(output_dir)
    plans=[read_json(p) for p in sorted(root.glob('round-*.json'))]
    plans=[p for p in plans if p.get('kind')=='final-all' and (round_number is None or p['round']==round_number)]
    if not plans:raise ValueError('No matching final-all plan; rechecks/exploration are not final full-library results')
    plan=max(plans,key=lambda p:p['round'])
    if digest({k:v for k,v in plan.items() if k!='round_hash'})!=plan['round_hash']:raise ValueError('Final plan hash mismatch')
    vocab=plan['vocabulary']
    if not vocab.get('frozen') or digest(vocab)!=plan['vocab_hash']:raise ValueError('Invalid final vocabulary snapshot/hash')
    accepted={c['key'] for c in vocab['concepts'] if c['status']=='accepted'}
    expected={r['image_hash']:r for r in plan['images']}
    if len(expected)!=len(plan['images']):raise ValueError('Duplicate image hashes in final plan')
    selected={}
    # Read one consistent snapshot while the classifier may be appending jobs.
    uri=(root/'state.sqlite3').resolve().as_uri()+'?mode=ro'
    with closing(sqlite3.connect(uri,uri=True,timeout=20)) as db:
        db.execute('BEGIN')
        rows=db.execute("""SELECT p.image_hash,p.anon_id,p.data,j.id,j.input,j.finished_at
            FROM predictions p JOIN jobs j ON j.id=p.job_id
            WHERE j.kind='visual' AND j.phase='final' AND j.status='succeeded'
            ORDER BY j.finished_at,j.id,p.anon_id""")
        for h,anon,data,jid,inp,finished in rows:
            metadata=json.loads(inp)['metadata']
            if metadata.get('round_hash')!=plan['round_hash'] or metadata.get('role','main')!='main':continue
            if metadata.get('vocab_hash')!=plan['vocab_hash']:raise ValueError('Mixed vocabulary hashes in final result')
            if h not in expected or anon!=expected[h]['anon_id']:raise ValueError('Unexpected final image/ID')
            prediction=json.loads(data)
            if prediction.get('id')!=anon:raise ValueError('Prediction ID mismatch')
            selected[h]={'prediction':prediction,'job_id':jid,'finished_at':finished}
    missing=sorted(set(expected)-set(selected));complete=not missing
    if missing and not allow_partial:
        raise ValueError(f'Final pass incomplete: {len(selected)}/{len(expected)} images. Use --allow-partial for a clearly marked interim audit; no reports were overwritten.')
    all_rows=[];flagged=[]
    for h in sorted(selected):
        planrow=expected[h];record=selected[h]
        mappings=planrow.get('mappings') or [planrow['representative']]
        for asset in sorted(mappings,key=lambda a:a['asset_key']):
            issues=check_asset(asset,record['prediction'],accepted)
            row={'asset_key':asset['asset_key'],'item_id':asset.get('item_id'),'name':asset.get('name',''),
                'name_source':'prepared manifest label; not proof of game identity',
                'source_category':asset['source_category'],'scope':asset['scope'],'image_path':asset['image_path'],
                'image_hash':h,'job_id':record['job_id'],'visual_description':record['prediction']['visual_description'],
                'tags':record['prediction']['tags'],'uncertain':record['prediction'].get('uncertain',[]),
                'needs_review':bool(issues),'priority':'high' if any(i['priority']=='high' for i in issues) else 'medium' if issues else '',
                'issues':issues}
            all_rows.append(row)
            if issues:flagged.append(row)
    assetkeys=[r['asset_key'] for r in all_rows]
    if len(assetkeys)!=len(set(assetkeys)):raise ValueError('Duplicate asset mappings; counts would be misleading')
    total_assets=sum(len(r.get('mappings') or [r['representative']]) for r in expected.values())
    summary={'policy_version':POLICY_VERSION,'round':plan['round'],'round_hash':plan['round_hash'],'vocab_hash':plan['vocab_hash'],
        'complete_final_pass':complete,'expected_unique_images':len(expected),'checked_unique_images':len(selected),
        'missing_unique_images':len(missing),'total_asset_mappings':total_assets,'checked_asset_mappings':len(all_rows),
        'flagged_asset_mappings':len(flagged),'flagged_unique_images':len({r['image_hash'] for r in flagged}),
        'flagged_assets_by_priority':dict(Counter(r['priority'] for r in flagged)),
        'issue_counts_by_rule':dict(Counter(i['rule'] for r in flagged for i in r['issues'])),
        'requires_manual_decision':True,'source_data_modified':False,'model_calls':0,
        'limitations':['Flags are review candidates, not confirmed errors. No flags does not prove correctness.',
            'Only exact strong object-type tags and selected source/name conflicts are checked; colors/styles/materials are not inferred from names.',
            'Decorative depictions, integrated objects and deliberately composite furniture can be false positives.',
            'Missing/unfinished images are not counted as passed; partial reports cannot represent the final corpus.'],
        'policy':{'form_families':FORM_FAMILIES,'category_conflicts':{k:sorted(v) for k,v in CATEGORY_CONFLICTS.items()},
            'name_patterns':NAME_PATTERNS,'name_ambiguity_regex':NAME_AMBIGUITY},
        'checker_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.mkdir(parents=True,exist_ok=True)
    write_json(out/'report.json',{'summary':summary,'missing_image_hashes':missing,'needs_review':flagged})
    write_json(out/'all-results.json',all_rows)
    fields=['asset_key','item_id','name','source_category','scope','priority','tag_keys','review_rules','reasons','visual_description','image_path','image_hash','job_id']
    with (out/'needs-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in flagged:
            data={k:row[k] for k in fields if k in row}
            data.update(tag_keys=' | '.join(t['key'] for t in row['tags']),review_rules=' | '.join(sorted({i['rule'] for i in row['issues']})),reasons=' | '.join(i['reason'] for i in row['issues']))
            # Keep Excel from interpreting any source strings as formulas.
            writer.writerow({k:("'"+v if isinstance(v,str) and v[:1] in ('=','+','-','@') else v) for k,v in data.items()})
    return summary
