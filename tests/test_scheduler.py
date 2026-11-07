"""Offline scheduler verification: explicit synthetic fixtures, no live endpoint."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
try:
    from tests.test_classification import MockClient, answer, raw   # run from the repo root
except ImportError:
    from test_classification import MockClient, answer, raw         # run from inside tests/
from ffxiv_furniture.classification.manifest import prepare
from ffxiv_furniture.classification.sampling import sample
from ffxiv_furniture.classification.runner import classify
from ffxiv_furniture.classification.scheduler import (schedule, status, round_history,
    exploration_records, exploration_coverage, convergence_report, anchor_qa)
from ffxiv_furniture.classification.state import connect, read_json, write_json, digest
from ffxiv_furniture.classification.vocabulary import consolidate, freeze_vocab
from ffxiv_furniture.classification.reports import report


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


from collections import Counter
if __name__ == '__main__': unittest.main()
