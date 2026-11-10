"""Offline vocabulary decisions, taxonomy provenance, scheduling and tag audits."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
from collections import Counter
from contextlib import closing
from copy import deepcopy
from ffxiv_furniture.classification.audit import check_asset, audit_final
from ffxiv_furniture.classification.manifest import prepare
from ffxiv_furniture.classification.prompts import visual_prompt
from ffxiv_furniture.classification.reports import report
from ffxiv_furniture.classification.runner import classify
from ffxiv_furniture.classification.sampling import sample
from ffxiv_furniture.classification.scheduler import schedule, status, round_history, exploration_records, exploration_coverage, convergence_report, anchor_qa
from ffxiv_furniture.classification.state import connect, read_json, write_json, digest
from ffxiv_furniture.classification.taxonomy import counts, grouping, materialize_observations, reclassify, resolve_id
from ffxiv_furniture.classification.validation import validate_items
from ffxiv_furniture.classification.vocabulary import consolidate, freeze_vocab, apply_vocab, discovery_observations, inventory, save_version, validate_vocab
from pathlib import Path
from tests.test_classification import ClassificationFixture, MockClient, answer, raw
from ffxiv_furniture.classification.client import parse_response
from ffxiv_furniture.classification.validation import validate_items
from ffxiv_furniture.classification.vocabulary import normalize, validate_proposals
from unittest.mock import patch


class GuidedMock(MockClient):
    def chat(self, messages, max_tokens=4096):
        result = super().chat(messages, max_tokens)
        # Guided/final prompt has controlled key schema; explore stays free-name.
        if '"key"' in messages[0]['content'][0]['text']:
            value = json.loads(result['choices'][0]['message']['content'].split('```json\n')[1].split('\n```')[0])
            for item in value['items']:
                item['tags'] = [{'key': 'color:pink', 'confidence': .8, 'evidence': 'Pink surface'}]
            return raw(value)
        return result


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        assets = []
        for i in range(220):
            path = self.root / f'{i}.png'
            Image.new('RGB', (3, 3), (i, 13, 71)).save(path)
            assets.append({'asset_key': f'SECRET/{i}', 'item_id': None, 'name': 'PRIVATE',
                           'scope': 'interior', 'source_category': str(i % 7), 'image_path': str(path)})
        self.manifest = self.root / 'source.jsonl'
        self.manifest.write_text('\n'.join(json.dumps(a) for a in assets), encoding='utf-8')
        prepare(self.manifest, self.run)
        sample(self.run, budget=20)
        classify(self.run, MockClient.endpoint, MockClient.model, client=MockClient())
        mock = MockClient()
        consolidate(self.run, mock.endpoint, mock.model, client=mock)
        self.vocab = self.run / 'vocab-latest.json'

    def guided(self, kind='next-round', **kwargs):
        return schedule(self.run, kind, vocab=self.vocab, **kwargs)

    def execute(self, kind='next-round', max_batches=99, client=None):
        return self.guided(kind, execute=True, max_batches=max_batches, client=client or GuidedMock())

    def test_seed_quotas_unseen_controls_and_immutable_history(self):
        original = (self.run/'round-001.json').read_bytes()
        preview = self.guided(dry_run=True)
        self.assertEqual(preview['selection_counts'], {'random':32,'low_coverage':16,'target_fallback_random':16})
        self.assertEqual(preview['controls'], 8)
        self.assertEqual(preview, self.guided(dry_run=True))
        self.assertFalse((self.run/'round-002.json').exists())
        self.guided()
        plan = round_history(self.run)[1]
        self.assertFalse({r['image_hash'] for r in round_history(self.run)[0]['images']} & set(preview['image_hashes']))
        self.assertEqual(original, (self.run/'round-001.json').read_bytes())
        self.assertEqual(len(set(r['anon_id'] for p in round_history(self.run) for r in p['images'])),84)
        self.assertTrue(self.guided(seed=999)['resumed'])
        self.assertEqual(plan, read_json(self.run/'round-002.json'))
        with closing(connect(self.run)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM rounds').fetchone()[0],2)

    def test_target_quota_and_fallback(self):
        first = self.guided(dry_run=True)
        remaining = set(exploration_coverage(self.run)['unseen_image_hashes']) - set(first['image_hashes'])
        result = self.guided(targets=sorted(remaining)[:20], dry_run=True)
        self.assertEqual(result['selection_counts']['target'],16)
        self.assertEqual(result['selected'],64)

    def test_bound_resume_independent_controls_stop(self):
        client = GuidedMock()
        self.execute(max_batches=1, client=client)
        self.assertEqual(len(client.calls),1)
        (self.run/'STOP').touch()
        stopped = self.execute(max_batches=1, client=client)
        self.assertEqual(stopped['new_batches'],0)
        self.assertEqual(len(client.calls),1)
        (self.run/'STOP').unlink()
        self.execute(client=client)
        self.assertEqual(len(client.calls),18)  # 16 main + 2 independent controls
        records = exploration_records(self.run)
        guided = [r for r in records if r['round']==2]
        self.assertEqual(Counter(r['role'] for r in guided), {'main':64,'control':8})
        main = {r['image_hash']:r for r in guided if r['role']=='main'}
        for control in [r for r in guided if r['role']=='control']:
            self.assertNotEqual(control['job_id'], main[control['image_hash']]['job_id'])
        self.assertEqual(status(self.run)['successful_unique_images'],84)
        next_preview = self.guided(dry_run=True)
        self.assertEqual(next_preview['round'],3)
        self.assertFalse(set(next_preview['image_hashes']) & set(main))

    def test_snapshot_changed_resume_rejected_and_no_prior_answers_sent(self):
        self.guided()
        original = read_json(self.vocab)
        original['concepts'][0]['definition'] = 'changed'
        changed = self.root/'changed.json'; write_json(changed,original)
        with self.assertRaises(ValueError): schedule(self.run,'next-round',vocab=changed)
        client = GuidedMock(); self.execute(max_batches=1,client=client)
        sent = json.dumps(client.calls)
        self.assertNotIn('SECRET',sent)
        self.assertNotIn('PRIVATE',sent)
        self.assertNotIn('image_path',sent)
        self.assertNotIn('A muted pink angular surface.',sent)

    def test_discover_rest_full_coverage_and_fresh_final(self):
        self.execute()
        first = self.guided('discover-rest',dry_run=True)
        self.assertEqual(first['selected'],136)
        self.execute('discover-rest',max_batches=1)
        self.assertFalse(exploration_coverage(self.run)['complete'])
        self.execute('discover-rest')
        self.assertTrue(exploration_coverage(self.run)['complete'])
        self.assertEqual(status(self.run)['successful_unique_images'],220)
        # Integration: all-round inventory and freeze must include guided discovery.
        mock=MockClient(); consolidate(self.run,mock.endpoint,mock.model,client=mock)
        vocabulary=read_json(self.vocab)
        for c in vocabulary['concepts']:
            c['status']='accepted'; c['definition']='Visible pink surface coloration.'
        reviewed=self.root/'reviewed.json'; write_json(reviewed,vocabulary)
        freeze_vocab(self.run,reviewed)
        preview=self.guided('final-all',dry_run=True)
        self.assertEqual(preview['selected'],220)
        client=GuidedMock(); self.execute('final-all',max_batches=1,client=client)
        self.assertEqual(len(client.calls),1)
        self.execute('final-all',client=client)
        self.assertEqual(len(client.calls),55)
        self.execute('final-all',client=client)
        self.assertEqual(len(client.calls),55)
        self.assertNotIn('A muted pink angular surface.',json.dumps(client.calls))
        final_status = status(self.run)['rounds'][-1]
        self.assertTrue(final_status['complete'])
        self.assertEqual(final_status['successful'],220)
        with closing(connect(self.run)) as db:
            self.assertEqual(db.execute("SELECT count(DISTINCT image_hash) FROM predictions p JOIN jobs j ON j.id=p.job_id WHERE j.phase='final' AND j.status='succeeded'").fetchone()[0],220)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_final_blocked_and_tampered_snapshot_rejected(self):
        with self.assertRaises(ValueError): self.guided('final-all',dry_run=True)
        self.guided()
        plan=read_json(self.run/'round-002.json'); plan['seed']=999
        write_json(self.run/'round-002.json',plan)
        with self.assertRaisesRegex(ValueError,'hash mismatch'): status(self.run)

    def test_anchor_explicit_only_and_never_coverage(self):
        before=exploration_coverage(self.run)
        self.execute(max_batches=1)
        self.assertFalse((self.run/'anchor-qa').exists())
        client=GuidedMock()
        anchor_qa(self.run,vocab=self.vocab,execute=True,client=client,max_batches=1)
        self.assertEqual(len(client.calls),1)
        anchor_qa(self.run,vocab=self.vocab,execute=True,client=client,max_batches=99)
        self.assertEqual(len(client.calls),5)
        self.assertEqual(status(self.run)['successful_unique_images'],24)
        self.assertFalse(any(r['role']=='anchor' for r in exploration_records(self.run)))
        self.assertEqual(status(self.run)['anchor_trends'][0]['successful_anchors'],20)

    def test_convergence_never_counts_raw_strings_or_controls(self):
        for _ in range(3): self.execute()
        report=convergence_report(self.run)
        self.assertFalse(report['three_round_low_rate_signal'])
        self.assertTrue(all(r['random_numerator'] is None for r in report['rounds']))
        qa={p['round_hash']:{'genuinely_new_image_hashes': [], 'reviewer':'fixture reviewer',
            'controls_no_repeated_misses':True,'anchors_no_systematic_regression':True,
            'no_high_impact_pending':True} for p in round_history(self.run) if p.get('kind')=='next-round'}
        write_json(self.run/'convergence-qa.json',qa)
        report=convergence_report(self.run)
        self.assertTrue(report['three_round_low_rate_signal'])
        self.assertTrue(report['discover_rest_recommended'])
        self.assertFalse(report['converged'])
        self.assertTrue(all(r['random_denominator']==32 for r in report['rounds']))

    def test_cli_subprocess_dryrun_status_and_reject_unbounded(self):
        args=[sys.executable,'-m','ffxiv_furniture.classification']
        before={p.name:p.read_bytes() for p in self.run.iterdir() if p.is_file()}
        proc=subprocess.run(args+['next-round','--run-dir',str(self.run),'--vocab',str(self.vocab),'--dry-run'],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['selected'],64)
        proc=subprocess.run(args+['status','--run-dir',str(self.run)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['successful_unique_images'],20)
        proc=subprocess.run(args+['next-round','--run-dir',str(self.run),'--vocab',str(self.vocab),'--dry-run','--max-batches','0'],capture_output=True,text=True)
        self.assertNotEqual(proc.returncode,0)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.run.iterdir() if p.is_file()})

    def test_backup_additive_migration(self):
        with closing(sqlite3.connect(self.run/'state.sqlite3')) as db:
            with db: db.execute('DROP TABLE rounds')
        with closing(connect(self.run)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM predictions').fetchone()[0],20)
        backup=self.run/'state.pre-history.sqlite3'
        self.assertTrue(backup.exists())
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM predictions').fetchone()[0],20)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='rounds'").fetchone())


    def test_zero_tags_are_successful_and_failed_predictions_never_count(self):
        class EmptyMock(GuidedMock):
            def chat(inner,messages,max_tokens=4096):
                result=super().chat(messages,max_tokens)
                value=json.loads(result['choices'][0]['message']['content'].replace('```json\n','').replace('\n```',''))
                for item in value['items']: item['tags']=[]
                return raw(value)
        self.execute('discover-rest',client=EmptyMock())
        self.assertTrue(exploration_coverage(self.run)['complete'])
        with closing(connect(self.run)) as db:
            with db:
                db.execute("UPDATE jobs SET status='failed' WHERE phase='guided'")
        self.assertEqual(len(exploration_coverage(self.run)['successful_image_hashes']),20)

    def test_legacy_guided_report_retains_snapshot_and_global_report(self):
        client=GuidedMock()
        classify(self.run,client.endpoint,client.model,phase='guided',vocab=self.vocab,client=client)
        self.assertEqual(report(self.run)['successful_unique_images'],20)
        self.execute()
        summary=report(self.run)
        self.assertEqual(summary['selected_unique_images'],84)
        self.assertEqual(summary['successful_unique_images'],84)
        self.assertEqual(len(summary['scheduler']['rounds']),2)

    def test_near_exhaustion_and_execution_settings_pinned(self):
        for _ in range(3): self.execute()
        tail=self.guided(dry_run=True)
        self.assertEqual(tail['selected'],8)
        self.execute()
        self.assertTrue(exploration_coverage(self.run)['complete'])
        with self.assertRaisesRegex(ValueError,'No unseen'):
            self.guided(dry_run=True)
        with self.assertRaises(ValueError):
            self.guided('discover-rest',targets=['not-a-hash'],dry_run=True)

    def test_changed_execution_settings_rejected(self):
        self.execute(max_batches=1)
        with self.assertRaisesRegex(ValueError,'Execution settings changed'):
            self.guided(execute=True,client=GuidedMock(),batch_size=2)
        with self.assertRaises(ValueError):
            self.guided(execute=True,max_batches=0,client=GuidedMock())


def vocabulary_concept(cid, name, category='material'):
    return {'concept_id': cid, 'key': category+':'+name, 'name': name, 'category': category,
            'definition': 'Visible appearance only.', 'include': [], 'exclude': [], 'examples': [],
            'negative_examples': [], 'original_names': [name], 'aliases': [], 'status': 'provisional'}


def vocabulary_fixture():
    return {'schema_version': 1, 'concepts': [vocabulary_concept('a','wood-like'),vocabulary_concept('b','wood')],
            'proposals': [], 'decisions': [], 'relations': [], 'frozen': False}


def alias_proposal(status='accepted'):
    return {'proposal_id': 'p', 'action':'alias', 'source':'a', 'target':'b',
            'reason':'Reviewed appearance synonyms', 'interchangeable':True,
            'status':status, 'reviewer':'agent'}


class TaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def apply(self, vocab):
        file = self.root/'candidate.json'
        write_json(file, vocab)
        result = apply_vocab(self.root, file)
        return result, read_json(self.root/'vocab-latest.json')

    def test_pending_and_rejected_alias_never_applied(self):
        for status in ('pending','rejected'):
            with self.subTest(status=status):
                other = self.root/status
                vocab = vocabulary_fixture(); vocab['proposals'] = [alias_proposal(status)]
                file = other/'candidate.json'; write_json(file,vocab)
                apply_vocab(other,file)
                self.assertEqual(read_json(other/'vocab-latest.json')['concepts'][0]['status'],'provisional')

    def test_apply_alias_preserves_names_and_records_scoped_provenance(self):
        vocab=vocabulary_fixture(); save_version(self.root,vocab)
        vocab['proposals']=[alias_proposal()]
        result,applied=self.apply(vocab)
        self.assertEqual(result['version'],2)
        self.assertEqual(applied['concepts'][0]['original_names'],['wood-like'])
        self.assertEqual(applied['concepts'][1]['aliases'][0]['source_concept_id'],'a')
        self.assertEqual(resolve_id(applied,'a'),'b')
        self.assertEqual(applied['decisions'][0]['reviewer'],'agent')
        self.assertEqual(len(grouping(applied)),1)
        self.assertEqual(counts(applied)['active_concepts'],1)
        self.assertEqual(self.apply(applied)[1]['decisions'],applied['decisions'])

    def test_alias_cycles_and_conflicting_targets_rejected(self):
        vocab=vocabulary_fixture()
        for source,target in [('a','b'),('b','a')]:
            c=next(c for c in vocab['concepts'] if c['concept_id']==source)
            c.update(status='merged',merged_into=target)
        with self.assertRaises(ValueError): validate_vocab(vocab)
        vocab=vocabulary_fixture()
        vocab['concepts'][0]['aliases']=[{'name':'wood','scope':'material','ambiguous':False}]
        with self.assertRaises(ValueError): validate_vocab(vocab)
        vocab['concepts'][0]['aliases'][0]['ambiguous']=True
        validate_vocab(vocab)

    def test_duplicate_alias_relation_proposal_references_rejected(self):
        for kind in ('alias','relation','proposal'):
            vocab=vocabulary_fixture()
            if kind=='alias':
                alias={'name':'timber appearance','scope':'material','ambiguous':False}
                vocab['concepts'][0]['aliases']=[alias,deepcopy(alias)]
            elif kind=='relation':
                relation={'type':'related','source':'a','target':'b'}
                vocab['relations']=[relation,deepcopy(relation)]
            else:
                vocab['proposals']=[alias_proposal(),alias_proposal()]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.apply(vocab)

    def test_alias_unknown_provenance_rejected(self):
        vocab=vocabulary_fixture()
        vocab['concepts'][0]['aliases']=[{'name':'timber','scope':'material','ambiguous':False,'source_concept_id':'absent'}]
        with self.assertRaises(ValueError): validate_vocab(vocab)

    def test_existing_proposal_payload_cannot_be_rewritten(self):
        vocab=vocabulary_fixture(); vocab['proposals']=[alias_proposal('pending')]; save_version(self.root,vocab)
        vocab['proposals'][0].update(source='b',target='a',status='accepted')
        with self.assertRaises(ValueError): self.apply(vocab)

    def test_decision_status_change_does_not_silently_auto_apply(self):
        vocab=vocabulary_fixture(); vocab['proposals']=[alias_proposal('rejected')]
        _, applied=self.apply(vocab)
        applied['proposals'][0]['status']='accepted'
        with self.assertRaises(ValueError): self.apply(applied)

    def test_category_move_is_new_identity_and_preserves_evidence(self):
        vocab=vocabulary_fixture(); vocab['concepts'][0]=vocabulary_concept('a','carved','style')
        save_version(self.root,vocab)
        raw=[{'concept_id':'a','category':'style','image_hash':'sha','anon_id':'I1',
              'evidence':'incised decoration','raw_name':'carved','confidence':0.9}]
        snapshot=deepcopy(raw)
        target=reclassify(vocab,'a','ornament',raw,'Incision is ornament, not style')
        self.assertNotEqual(target,'a')
        _,applied=self.apply(vocab)
        self.assertEqual(applied['concepts'][0]['category'],'style')
        self.assertEqual(applied['concepts'][0]['original_names'],['carved'])
        self.assertEqual(raw,snapshot)
        derived=materialize_observations(applied,raw)
        self.assertEqual(derived[0]['canonical_category'],'ornament')
        self.assertEqual(derived[0]['raw_concept_id'],'a')
        self.assertEqual(derived[0]['evidence'],'incised decoration')
        self.assertEqual(len(derived),len(raw))
        self.assertNotIn('"key":"style:carved"',visual_prompt('guided',applied))

    def test_in_place_category_move_blocked(self):
        vocab=vocabulary_fixture(); save_version(self.root,vocab)
        vocab['concepts'][0].update(category='form',key='form:wood-like')
        with self.assertRaises(ValueError): self.apply(vocab)

    def test_category_refactor_without_exact_links_or_evidence_blocked(self):
        for change in ('no-evidence','wrong-category','no-reciprocal','duplicate-supersedes'):
            vocab=vocabulary_fixture(); vocab['concepts'][0]=vocabulary_concept('a','carved','style')
            raw=[{'concept_id':'a','category':'style','image_hash':'sha','evidence':'incision'}]
            reclassify(vocab,'a','ornament',raw,'Decoration')
            relation=vocab['relations'][0]
            if change=='no-evidence': relation['source_observations']=[]
            elif change=='wrong-category': relation['source_observations'][0]['category']='material'
            elif change=='no-reciprocal': vocab['concepts'][-1]['supersedes']=[]
            else: vocab['concepts'][-1]['supersedes']=['a','a']
            with self.subTest(change=change), self.assertRaises(ValueError): validate_vocab(vocab)

    def test_missing_source_observations_blocks_category_move(self):
        with self.assertRaises(ValueError): reclassify(vocabulary_fixture(),'a','form',[],'Unsupported')

    def test_normalized_duplicate_visual_tags_rejected(self):
        item={'id':'I1','visual_description':'Brown wood appearance',
              'tags':[{'category':'material','name':name,'confidence':0.8,'evidence':'grain'} for name in ('wood',' WOOD ')],
              'proposed_tags':[],'uncertain':[]}
        with self.assertRaises(ValueError): validate_items({'items':[item]},['I1'])

    def test_guided_proposals_and_control_evidence_include_all_rounds(self):
        image={'anon_id':'I1','image_hash':'sha','mappings':[{'asset_key':'asset','scope':'inside','source_category':'chair'}],
               'selection_reason':'random','stratum':['inside','chair']}
        write_json(self.root/'round-001.json',{'images':[image]})
        image2={**image,'anon_id':'R002I0001','image_hash':'sha2'}
        write_json(self.root/'round-002.json',{'images':[image2]})
        record={'image_hash':'sha','anon_id':'I1','phase':'explore','role':'main','round':1,'job_id':'j1',
                'data':{'tags':[{'category':'color','name':'brown','evidence':'brown','confidence':0.9}], 'proposed_tags':[]}}
        guided={'image_hash':'sha2','anon_id':'R002I0001','phase':'guided','role':'main','round':2,'job_id':'j2',
                'vocabulary':{'concepts':[vocabulary_concept('brown','brown','color')]},
                'data':{'tags':[{'key':'color:brown','evidence':'brown panel','confidence':0.8}],
                        'proposed_tags':[{'category':'ornament','name':'dots','evidence':'dotted trim','confidence':0.7}]}}
        with patch('ffxiv_furniture.classification.scheduler.exploration_records',return_value=[record,guided]):
            concepts,observations=inventory(self.root)
        self.assertEqual(len(concepts),2)
        self.assertEqual(len(observations),3)
        self.assertEqual({o['round'] for o in observations},{1,2})
        self.assertEqual({o['source_kind'] for o in observations},{'controlled','unguided','proposed'})

    def test_guided_key_uses_exact_snapshot_not_latest(self):
        row={'image_hash':'h','anon_id':'x','phase':'guided','role':'main','data':{'tags':[{'key':'absent'}]}}
        with patch('ffxiv_furniture.classification.scheduler.exploration_records',return_value=[row]):
            with self.assertRaises(ValueError): discovery_observations(self.root)


def audit_asset(key='a',name='Manor Dressing Table',category='Furniture/Table'):
    return {'asset_key':key,'name':name,'source_category':category,'scope':'interior','item_id':None,'image_path':'fixture.png'}


def audit_prediction(anon,*tags):
    return {'id':anon,'visual_description':'Explicit test fixture.','tags':[{'key':k,'confidence':.8,'evidence':'fixture'} for k in tags],'uncertain':[],'proposed_tags':[]}


class TagAuditTests(unittest.TestCase):
    def test_known_dressing_table_bed_conflict(self):
        issues=check_asset(audit_asset(),audit_prediction('x','form:bed'),{'form:bed'})
        self.assertEqual({i['rule'] for i in issues},{'category_object_conflict','name_object_conflict'})
        self.assertIn('high',{i['priority'] for i in issues})
        self.assertTrue(check_asset(audit_asset(name='Glade Lantern',category='Lighting'),audit_prediction('x','form:bed')))

    def test_sofa_in_chair_category_not_an_error(self):
        self.assertEqual(check_asset(audit_asset(name='Leather Sofa',category='Furniture/Chair'),audit_prediction('x','form:sofa')),[])
        self.assertEqual(check_asset(audit_asset(name='Bench',category='Furniture/Chair'),audit_prediction('x','form:sofa')),[])

    def test_geometry_and_color_are_not_function(self):
        self.assertEqual(check_asset(audit_asset(),audit_prediction('x','form:rectangular','color:purple','ornament:bat wings')),[])

    def test_bedside_and_compound_names(self):
        self.assertEqual(check_asset(audit_asset(name='Bedside Table'),audit_prediction('x','form:table')),[])
        self.assertEqual(check_asset(audit_asset(name='Sofa Bed',category='Furniture/Chair'),audit_prediction('x','form:bed')),[])
        self.assertEqual(check_asset(audit_asset(name='Miniature Bed',category='Item/Stuffed'),audit_prediction('x','form:table')),[])

    def test_inactive_key_is_review_not_silent_repair(self):
        p=audit_prediction('x','form:bed')
        issues=check_asset(audit_asset(),p,set())
        self.assertIn('inactive_or_unknown_tag',{i['rule'] for i in issues})
        self.assertEqual(p['tags'][0]['key'],'form:bed')

    def setup_run(self,path):
        path.mkdir(exist_ok=True)
        h1,h2='a'*64,'b'*64
        maps=[audit_asset(),audit_asset('variant',name='Other Dressing Table')]
        vocab={'frozen':True,'concepts':[{'key':k,'status':'accepted'} for k in ['form:bed','form:table','form:sofa']]}
        plan={'round':6,'kind':'final-all','vocabulary':vocab,'vocab_hash':digest(vocab),'images':[
            {'image_hash':h1,'anon_id':'I1','representative':maps[0],'mappings':maps},
            {'image_hash':h2,'anon_id':'I2','representative':audit_asset('sofa','Leather Sofa','Furniture/Chair'),'mappings':[audit_asset('sofa','Leather Sofa','Furniture/Chair')]}]}
        plan['round_hash']=digest(plan);write_json(path/'round-006.json',plan)
        with closing(sqlite3.connect(path/'state.sqlite3')) as c:
            c.executescript('CREATE TABLE jobs(id TEXT,kind TEXT,phase TEXT,status TEXT,input TEXT,finished_at REAL);CREATE TABLE predictions(job_id TEXT,anon_id TEXT,image_hash TEXT,data TEXT);')
        return plan

    def add(self,path,plan,jid,index,tag,time=1,round_hash=None):
        row=plan['images'][index]
        metadata={'round_hash':round_hash or plan['round_hash'],'vocab_hash':plan['vocab_hash']}
        with closing(sqlite3.connect(path/'state.sqlite3')) as c:
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',(jid,'visual','final','succeeded',json.dumps({'metadata':metadata}),time))
            c.execute('INSERT INTO predictions VALUES(?,?,?,?)',(jid,row['anon_id'],row['image_hash'],json.dumps(audit_prediction(row['anon_id'],tag))))
            c.commit()

    def test_default_requires_complete_partial_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'run';plan=self.setup_run(root);out=Path(tmp)/'audit'
            self.add(root,plan,'j1',0,'form:bed')
            with self.assertRaisesRegex(ValueError,'incomplete'):audit_final(root,out)
            self.assertFalse(out.exists())
            summary=audit_final(root,out,allow_partial=True)
            self.assertFalse(summary['complete_final_pass'])
            self.assertEqual(summary['missing_unique_images'],1)
            self.assertEqual(summary['flagged_asset_mappings'],2)
            self.assertEqual(summary['flagged_unique_images'],1)

    def test_main_round_only_latest_success_and_no_source_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'run';plan=self.setup_run(root);out=Path(tmp)/'audit'
            self.add(root,plan,'j1',0,'form:bed',time=1)
            self.add(root,plan,'j2',0,'form:table',time=2)
            self.add(root,plan,'j3',1,'form:sofa',time=3)
            self.add(root,plan,'unrelated-recheck',0,'form:bed',time=4,round_hash='other')
            before=(root/'state.sqlite3').read_bytes()
            summary=audit_final(root,out)
            self.assertEqual(summary['checked_unique_images'],2)
            self.assertEqual(summary['checked_asset_mappings'],3)
            self.assertEqual(summary['flagged_asset_mappings'],0)
            self.assertEqual((root/'state.sqlite3').read_bytes(),before)
            self.assertEqual(len(read_json(out/'all-results.json')),3)
            self.assertTrue((out/'needs-review.csv').read_bytes().startswith(b'\xef\xbb\xbf'))


class VocabularyLifecycleTests(ClassificationFixture, unittest.TestCase):
    def test_consolidation_mock_normalization_versions_and_freeze_block(self):
        self.sampled(8); self.classify()
        self.assertEqual(normalize('  ＰＩＮＫ\t '),'pink')
        concepts,obs=inventory(self.run)
        self.assertEqual(len(concepts),1)
        self.assertEqual(len(obs),8)
        self.assertEqual(concepts[0]['original_names'],[' Pink '])
        client=MockClient()
        result=consolidate(self.run,client.endpoint,client.model,client=client)
        self.assertEqual(result['version'],1)
        self.assertIsInstance(client.calls[0][0]['content'],str)
        self.assertNotIn('image_url',json.dumps(client.calls))
        result2=consolidate(self.run,client.endpoint,client.model,client=client)
        self.assertEqual(result2['version'],1)
        self.assertEqual(len(client.calls),1)
        with self.assertRaises(ValueError): freeze_vocab(self.run,self.run/'vocab-latest.json')
        vocab=read_json(self.run/'vocab-latest.json')
        vocab['concepts']=[]; path=self.root/'delete.json'; write_json(path,vocab)
        with self.assertRaises(ValueError): apply_vocab(self.run,path)

    def test_proposal_cycles_cross_category_and_ambiguity(self):
        concepts=[{'concept_id':'a','category':'color'}, {'concept_id':'b','category':'color'}, {'concept_id':'c','category':'form'}]
        def proposal(source,target): return {'action':'merge','source':source,'target':target,'reason':'same','interchangeable':True}
        validate_proposals({'proposals':[proposal('a','b')]},concepts)
        for proposals in ([proposal('a','b'),proposal('b','a')],[proposal('a','c')],[proposal('a','missing')],
                          [{**proposal('a','b'),'interchangeable':False}]):
            with self.assertRaises(ValueError): validate_proposals({'proposals':proposals},concepts)

    def test_vocab_hash_invalidates_cache_and_final_unknown_keys(self):
        self.sampled(4); self.classify()
        client=MockClient(); consolidate(self.run,client.endpoint,client.model,client=client)
        vocab=read_json(self.run/'vocab-latest.json')
        concept=vocab['concepts'][0]
        valid=answer(['I0001'])
        valid['items'][0]['tags']=[{'key':concept['key'],'confidence':0.8,'evidence':'visible'}]
        validate_items(valid,['I0001'],'guided',vocab)
        valid['items'][0]['tags'][0]['key']='color:not-known'
        with self.assertRaises(ValueError): validate_items(valid,['I0001'],'final',vocab)
        with self.assertRaises(ValueError): self.classify(phase='final',vocab=self.run/'vocab-latest.json')
        # Valid mocked guided output; changing vocab definition must trigger actual new job.
        class GuidedMock(MockClient):
            def chat(inner,messages,max_tokens=4096):
                raw_value=super(GuidedMock,inner).chat(messages,max_tokens)
                value=parse_response(raw_value)
                for item in value['items']:
                    item['tags']=[{'key':concept['key'],'confidence':0.8,'evidence':'visible'}]
                return raw(value)
        guided=GuidedMock()
        self.classify(guided,phase='guided',vocab=self.run/'vocab-latest.json')
        vocab['concepts'][0]['definition']='changed definition'
        write_json(self.run/'changed.json',vocab)
        self.classify(guided,phase='guided',vocab=self.run/'changed.json')
        self.assertEqual(len(guided.calls),2)
        self.assertNotIn('SECRET',json.dumps(guided.calls))
        self.assertNotIn('image_path',json.dumps(guided.calls))

    def test_vocab_apply_merge_preserves_original_and_split_blocks(self):
        self.sampled(4)
        class TwoNames(MockClient):
            def chat(inner, messages, max_tokens=4096):
                response = super(TwoNames,inner).chat(messages,max_tokens)
                value = parse_response(response)
                for index,item in enumerate(value['items']):
                    item['tags'][0]['name'] = 'rose' if index % 2 else 'pink'
                return raw(value)
        self.classify(TwoNames())
        mock=MockClient(); consolidate(self.run,mock.endpoint,mock.model,client=mock)
        vocab=read_json(self.run/'vocab-latest.json')
        source,target=vocab['concepts']
        proposal={'action':'merge','source':source['concept_id'],'target':target['concept_id'],
                  'reason':'explicitly reviewed synonyms','interchangeable':True,
                  'status':'accepted','policy':'explicit','proposal_id':'reviewed-merge-1'}
        vocab['proposals']=[proposal]
        reviewed=self.root/'reviewed.json'; write_json(reviewed,vocab)
        apply_vocab(self.run,reviewed)
        applied=read_json(self.run/'vocab-latest.json')
        self.assertEqual(len(applied['concepts']),2)
        merged=next(c for c in applied['concepts'] if c['concept_id']==source['concept_id'])
        self.assertEqual(merged['merged_into'],target['concept_id'])
        self.assertTrue(merged['original_names'])
        self.assertEqual(len(applied['decisions']),1)
        self.assertTrue(applied['revisions'])
        applied['proposals'].append({'action':'split','source':target['concept_id'],
            'reason':'needs rejudgement','status':'accepted','policy':'explicit','proposal_id':'split-1'})
        write_json(reviewed,applied)
        with self.assertRaises(ValueError): apply_vocab(self.run,reviewed)
        self.assertEqual(len(read_json(self.run/'vocab-latest.json')['decisions']),1)

    def test_freeze_requires_decisions_and_defined_accepted_concepts(self):
        self.sampled(100); self.classify()
        mock=MockClient(); consolidate(self.run,mock.endpoint,mock.model,client=mock)
        path=self.root/'freeze.json'
        vocab=read_json(self.run/'vocab-latest.json')
        write_json(path,vocab)
        with self.assertRaises(ValueError): freeze_vocab(self.run,path)
        for concept in vocab['concepts']:
            concept['status']='accepted'
            concept['definition']='Muted pink visible surface coloration.'
        write_json(path,vocab)
        freeze_vocab(self.run,path)
        self.assertTrue(read_json(self.run/'vocab-latest.json')['frozen'])


if __name__ == '__main__':
    unittest.main()
