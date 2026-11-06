"""Build an isolated full-candidate test DB and an ID-backed ReMakePlace demo.

No game resources/saves or production DB are modified. Missing Item IDs stay NULL.
"""
from __future__ import annotations
import argparse
from collections import defaultdict,Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.layout import build_layout
from ffxiv_furniture.classification.scheduler import exploration_records
from ffxiv_furniture.classification.state import digest,read_json,write_json
from ffxiv_furniture.classification.vocabulary import normalize,validate_vocab


def compact(value):
    return re.sub('[^a-z0-9]','',value.lower())


def verified_mappings(catalog,names,sources):
    by=defaultdict(list)
    for row in catalog:by[(row['scope'],compact(row['name_key_candidate']))].append(row)
    options=defaultdict(list)
    for source in sources:
        layout=json.loads(source.read_bytes())
        for scope,field in [('interior','interiorFurniture'),('exterior','exteriorFurniture')]:
            queue=list(layout.get(field,[]))
            while queue:
                item=queue.pop();queue.extend(item.get('attachments',[]))
                name=item.get('name');iid=item.get('itemId')
                if name not in names or type(iid) is not int or iid<=0:continue
                matches=by.get((scope,compact(name)),[])
                if len(matches)!=1:continue
                options[matches[0]['asset_folder']].append({'item_id':iid,'name':name,'source':str(source),
                  'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'method':'Real layout Item ID + exact local AssetNames key + unique scope/alphanumeric asset-name match'})
    accepted={};conflicts=[];ids={}
    for asset,rows in sorted(options.items()):
        pairs={(r['item_id'],r['name']) for r in rows}
        if len(pairs)!=1:
            conflicts.append({'asset_key':asset,'evidence':rows});continue
        evidence=rows[0]
        if evidence['item_id'] in ids and ids[evidence['item_id']]!=asset:
            raise ValueError('One Item ID maps to multiple candidate assets; review required')
        ids[evidence['item_id']]=asset;accepted[asset]={**evidence,'all_sources':rows}
    return accepted,conflicts


def canonical_id(concepts,cid):
    seen=set()
    while True:
        if cid in seen:raise ValueError('Concept cycle')
        seen.add(cid)
        concept=concepts[cid]
        successor=concept.get('merged_into') if concept['status']=='merged' else concept.get('superseded_by')
        if successor:cid=successor;continue
        return cid if concept['status'] in ('accepted','provisional') else None


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',default=str(ROOT/'runs/round1'))
    p.add_argument('--inspection-dir',default=os.environ.get('FFXIVFURN_INSPECTION_DIR'),help='default: $FFXIVFURN_INSPECTION_DIR')
    p.add_argument('--seed',default=os.environ.get('DECO_SEED'),help='complete layout JSON (default: $DECO_SEED)')
    p.add_argument('--db',default=str(ROOT/'data/furniture-test.sqlite3'))
    p.add_argument('--output-dir',default=str(ROOT/'outputs/test-db-demo'))
    a=p.parse_args(argv)
    root=Path(a.run_dir);source=Path(a.inspection_dir);target=Path(a.db).resolve();output=Path(a.output_dir).resolve()
    if target.exists():raise ValueError('Refuse overwrite of existing test DB; choose another --db')
    output.mkdir(parents=True,exist_ok=True)
    catalog=read_json(source/'asset-folder-catalog.json')
    manifest=read_json(root/'manifest.json')['assets']
    completion=read_json(root/'completion-automation/completion-report.json')
    vocab=validate_vocab(read_json(completion['vocabulary']))
    concepts={c['concept_id']:c for c in vocab['concepts']}
    assetrows={x['asset_key']:x for x in manifest}
    latest={}
    for row in sorted(exploration_records(root),key=lambda r:(r['finished_at'],r['job_id'])):
        if row['role']=='main':latest[row['image_hash']]=row
    expected={x['image_hash'] for x in manifest}
    if set(latest)!=expected:raise ValueError('Incomplete or extra source image coverage')
    mappings,conflicts=verified_mappings(catalog,set(read_json(source/'AssetNames.json')['entries']),
                                          sorted((source/'schema-reference').glob('example*.json')))
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=target.with_suffix('.building.sqlite3')
    if stage.exists():raise ValueError('Existing stage must be inspected before retry')
    skipped=[];counts=Counter()
    with FurnitureDB(stage) as db:
        c=db.connection
        c.executescript('''
        CREATE TABLE candidate_assets(
          asset_key TEXT PRIMARY KEY, item_id INTEGER REFERENCES furniture(id), name TEXT NOT NULL,
          source_category TEXT NOT NULL, scope TEXT NOT NULL, image_path TEXT NOT NULL,
          image_hash TEXT NOT NULL, visual_description TEXT NOT NULL,
          source_job TEXT NOT NULL, source_round INTEGER NOT NULL, source_vocab_hash TEXT,
          item_id_evidence TEXT, metadata_status TEXT NOT NULL);
        CREATE TABLE candidate_tags(
          asset_key TEXT NOT NULL REFERENCES candidate_assets(asset_key),
          tag_id INTEGER NOT NULL REFERENCES tags(id),confidence REAL,evidence TEXT NOT NULL,
          source_concept TEXT NOT NULL,PRIMARY KEY(asset_key,tag_id));
        CREATE TABLE classification_records(image_hash TEXT PRIMARY KEY,source_job TEXT NOT NULL,data TEXT NOT NULL);
        CREATE TABLE tag_concepts(concept_id TEXT PRIMARY KEY,tag_id INTEGER REFERENCES tags(id),data TEXT NOT NULL);
        CREATE TABLE build_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE INDEX candidate_category_scope ON candidate_assets(source_category,scope);
        CREATE INDEX candidate_tags_tag ON candidate_tags(tag_id,asset_key);
        ''')
        tagids={}
        for cid,concept in sorted(concepts.items()):
            resolved=canonical_id(concepts,cid)
            if resolved and resolved not in tagids:
                dst=concepts[resolved];tagids[resolved]=db.add_tag(dst['category'],dst['name'])['id']
        for cid,concept in concepts.items():
            resolved=canonical_id(concepts,cid)
            c.execute('INSERT INTO tag_concepts VALUES(?,?,?)',(cid,tagids.get(resolved),json.dumps(concept,ensure_ascii=False)))
        c.commit()
        for key,row in sorted(assetrows.items()):
            prediction=latest[row['image_hash']];data=prediction['data'];mapping=mappings.get(key)
            if mapping:
                db.add_furniture(mapping['item_id'],mapping['name'],description=data['visual_description'],image_path=row['image_path'],scope=row['scope'])
            c.execute('INSERT INTO candidate_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (key,mapping['item_id'] if mapping else None,mapping['name'] if mapping else row.get('name') or key.rsplit('/',1)[-1],
                 row['source_category'],row['scope'],row['image_path'],row['image_hash'],data['visual_description'],
                 prediction['job_id'],prediction['round'],digest(prediction['vocabulary']) if prediction.get('vocabulary') else None,
                 json.dumps(mapping,ensure_ascii=False) if mapping else None,
                 'reference-layout ID association; app placement untested' if mapping else 'candidate only; Item ID unknown'))
            snapshot={x['key']:x for x in (prediction.get('vocabulary') or {}).get('concepts',[])}
            resolved_tags={}
            for tag in data['tags']:
                cid=(snapshot[tag['key']]['concept_id'] if 'key' in tag else
                     'c_'+digest([tag['category'],normalize(tag['name'])])[:24])
                resolved=canonical_id(concepts,cid)
                if resolved is None:
                    skipped.append({'asset_key':key,'source_concept':cid,'reason':'not active; raw classification retained'});continue
                if resolved not in resolved_tags or tag['confidence']>resolved_tags[resolved][0]['confidence']:
                    resolved_tags[resolved]=(tag,cid)
            for cid,(tag,sourcecid) in resolved_tags.items():
                c.execute('INSERT INTO candidate_tags VALUES(?,?,?,?,?)',
                          (key,tagids[cid],tag['confidence'],tag['evidence'],sourcecid))
                if mapping:
                    # Store all original evidence above; the catalog API exposes source/confidence.
                    db.add_furniture_tag(mapping['item_id'],tagids[cid],source='qwen-visual:'+prediction['job_id'],confidence=tag['confidence'])
            if mapping:
                for category,name in [('function',row['source_category']),('scope',row['scope'])]:
                    found=c.execute('SELECT id FROM tags WHERE category=? AND name=?',(category,name)).fetchone()
                    tid=found[0] if found else db.add_tag(category,name)['id']
                    db.add_furniture_tag(mapping['item_id'],tid,source='packaged-asset-path',confidence=None)
            c.commit()
        for image_hash,prediction in latest.items():
            c.execute('INSERT INTO classification_records VALUES(?,?,?)',(image_hash,prediction['job_id'],json.dumps(prediction['data'],ensure_ascii=False)))
        c.execute('INSERT INTO build_metadata VALUES(?,?)',('classification_description_source','description in mapped furniture is a copy of Qwen visual_description, not original game flavor text'))
        c.execute('INSERT INTO build_metadata VALUES(?,?)',('vocab_hash',digest(vocab)))
        c.execute('INSERT INTO build_metadata VALUES(?,?)',('test_only','true; unknown game metadata and dimensions remain NULL'))
        c.commit()
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        for table in ['furniture','tags','furniture_tags','candidate_assets','candidate_tags','classification_records']:
            counts[table]=c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
        assert counts['candidate_assets']==len(catalog)==len(manifest)
        assert counts['classification_records']==len(expected)
    stage.replace(target)
    # Selection is performed through the catalog API; native names/IDs come from DB.
    roles=[('sofa','Leather Sofa',(0,0),0),('table','Oriental Round Table',(0,180),0),
           ('cabinet','Riviera Cupboard',(-380,0),0),('desk','Manor Desk',(380,0),180),
           ('stool','Riviera Stool',(380,160),0),('light','Glade Lantern',(-200,180),0)]
    seedbytes=Path(a.seed).read_bytes();seed=json.loads(seedbytes)
    existing=seed.get('interiorFurniture',[])
    anchor=next((x['transform']['location'] for x in existing if x.get('itemId')==28639),[0,0,0])
    selections=[];placements=[]
    with FurnitureDB(target) as db:
        for role,name,offset,yaw in roles:
            rows=[r for r in db.search_furniture(name=name,limit=1000) if r['name']==name]
            if len(rows)!=1:raise ValueError('Need exactly one DB match for '+name)
            item=rows[0];selections.append({'role':role,'query':{'name':name},'selected':item})
            placements.append({'item_id':item['id'],'location':[anchor[0]+offset[0],anchor[1]+offset[1],anchor[2]],'yaw_degrees':yaw})
        layout=build_layout(db,seed,placements)
        for item in layout['interiorFurniture']:
            assert db.get_furniture(item['itemId'])['name']==item['name']
    encoding='utf-16' if seedbytes.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8'
    layoutpath=output/'ReMakePlace_DB_Test.json'
    layoutpath.write_bytes((json.dumps(layout,ensure_ascii=False,indent='\t',allow_nan=False)+'\n').encode(encoding))
    assert json.loads(layoutpath.read_bytes())==layout
    write_json(output/'db-selection.json',{'selections':selections,'placements':placements,'geometry_calibrated':False})
    write_json(output/'id-mappings.json',{'accepted':mappings,'conflicts':conflicts})
    report={'database':str(target),'counts':dict(counts),'mapped_item_ids':len(mappings),
       'unmapped_assets':len(manifest)-len(mappings),'id_conflicts':conflicts,
       'raw_predictions_preserved':len(latest),'skipped_inactive_tag_observations':len(skipped),
       'skipped_observations':skipped,'layout':str(layoutpath),'layout_instances':len(placements),
       'encoding':encoding,'house_size':seed['houseSize'],'metadata_version':seed.get('metaData'),
       'vocab_hash':digest(vocab),'all_non_furniture_seed_fields_preserved':True,
       'geometry_verified':False,'app_import_tested':False,'original_save_modified':False,
       'production_db_modified':False,'seed_sha256':hashlib.sha256(seedbytes).hexdigest()}
    write_json(output/'build-report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='skipped_observations'},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':sys.exit(main())
