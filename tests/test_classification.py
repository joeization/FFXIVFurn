"""Unit tests use explicitly mocked inference, never contact the local model."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from PIL import Image
from ffxiv_furniture.classification.client import Client, parse_response
from ffxiv_furniture.classification.manifest import prepare
from ffxiv_furniture.classification.sampling import sample
from ffxiv_furniture.classification.runner import classify
from ffxiv_furniture.classification.reports import report
from ffxiv_furniture.classification.state import connect, read_json, write_json
from ffxiv_furniture.classification.validation import validate_items
from ffxiv_furniture.classification.vocabulary import (apply_vocab, consolidate, freeze_vocab,
    inventory, normalize, validate_proposals, validate_vocab)


def answer(ids):
    return {'items': [{'id': item, 'visual_description': 'A muted pink angular surface.',
             'tags': [{'category':'color','name':' Pink ','confidence':0.8,'evidence':'Pink visible surface'}],
             'proposed_tags': [], 'uncertain': []} for item in ids]}


def raw(value):
    return {'choices':[{'message':{'content': '```json\n'+json.dumps(value)+'\n```',
                                   'reasoning_content':'not used'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}


class MockClient:
    endpoint = 'http://mock.invalid/v1'
    model = 'explicit-mock-model'
    timeout = 1

    def __init__(self, bad=0, fail=False):
        self.calls = []
        self.bad = bad
        self.fail = fail
        self.discovered = 0

    def discover(self):
        self.discovered += 1
        return [self.model]

    def chat(self, messages, max_tokens=4096):
        self.calls.append(copy.deepcopy(messages))
        if self.fail:
            raise RuntimeError('Explicit mocked transport failure')
        if self.bad:
            self.bad -= 1
            return raw({'items': []})
        content = messages[0]['content']
        if isinstance(content, str):
            # Text consolidation mock explicitly returns no semantic proposals.
            return raw({'proposals': []})
        ids = []
        for block in content:
            if block['type'] == 'text' and block['text'].startswith('{'):
                ids.append(json.loads(block['text'])['id'])
        return raw(answer(ids))


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        rows = []
        for group, count in [('small',1),('medium',4),('large',12)]:
            for index in range(count):
                path = self.root / f'{group}-{index}.png'
                Image.new('RGB', (4,4), (len(rows)*11, index*13, 30)).save(path)
                rows.append({'asset_key':f'SECRET/{group}/{index}','item_id':None,
                             'name':'SECRET furniture name', 'scope':'interior', 'source_category':group,
                             'image_path':str(path.resolve()), 'patch':None})
        rows.append({**rows[-1], 'asset_key':'SECRET/shared-image', 'scope':'exterior'})
        self.rows = rows
        self.manifest = self.root / 'manifest.jsonl'
        self.write_manifest(rows)
        prepare(self.manifest, self.run)

    def write_manifest(self, rows):
        self.manifest.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')

    def sampled(self, budget=8):
        sample(self.run, budget=budget)
        return read_json(self.run / 'round-001.json')

    def classify(self, client=None, **kwargs):
        return classify(self.run, MockClient.endpoint, MockClient.model, client=client or MockClient(), **kwargs)

    def test_manifest_duplicate_image_preserves_mappings(self):
        result = prepare(self.manifest, self.run)
        self.assertEqual(result['assets'],18)
        self.assertEqual(result['unique_images'],17)
        self.assertTrue(all(r['item_id'] is None for r in read_json(self.run/'manifest.json')['assets']))

    def test_prepare_rejects_missing_corrupt_and_duplicate(self):
        for change in ('missing','corrupt','duplicate','id'):
            rows = copy.deepcopy(self.rows)
            if change == 'missing': rows[0]['image_path'] = str(self.root/'absent.png')
            elif change == 'corrupt':
                bad = self.root/'bad.png'; bad.write_bytes(b'not image'); rows[0]['image_path'] = str(bad)
            elif change == 'duplicate': rows.append(rows[0])
            else: rows[0]['item_id'] = 1; rows[1]['item_id'] = 1
            self.write_manifest(rows)
            with self.assertRaises((ValueError,OSError)):
                prepare(self.manifest, self.root/change)

    def test_prepare_immutable(self):
        rows=copy.deepcopy(self.rows); rows[0]['name']='changed'; self.write_manifest(rows)
        with self.assertRaises(ValueError): prepare(self.manifest,self.run)

    def test_sampling_reproducible_unique_small_groups(self):
        result=self.sampled()
        before=(self.run/'round-001.json').read_bytes()
        sample(self.run,budget=8)
        self.assertEqual(before,(self.run/'round-001.json').read_bytes())
        images=result['images']
        self.assertEqual(len(images),8)
        self.assertEqual(len({r['image_hash'] for r in images}),8)
        self.assertTrue(any(r['representative']['source_category']=='small' for r in images))
        self.assertEqual(len(result['anchor_ids']),8)
        # Different run, same source and seed produces byte-identical persisted round.
        other=self.root/'other'; prepare(self.manifest,other); sample(other,budget=8)
        self.assertEqual(before,(other/'round-001.json').read_bytes())
        with self.assertRaises(ValueError): sample(self.run,budget=8,seed=43)

    def test_sampling_shortfall_and_budget_cap(self):
        result=self.sampled(1)
        self.assertTrue(result['minimum_coverage_shortfall'])
        other=self.root/'full'; prepare(self.manifest,other)
        self.assertEqual(sample(other,budget=100)['selected'],17)

    def test_exact_ids_and_validation_failures(self):
        valid=answer(['I0001','I0002'])
        validate_items(valid,['I0001','I0002'])
        for change in ('missing','duplicate','extra','category','nan','evidence','count'):
            bad=copy.deepcopy(valid)
            if change=='missing': bad['items'].pop()
            elif change=='duplicate': bad['items'][1]['id']='I0001'
            elif change=='extra': bad['items'].append(answer(['I0003'])['items'][0])
            elif change=='category': bad['items'][0]['tags'][0]['category']='function'
            elif change=='nan': bad['items'][0]['tags'][0]['confidence']=float('nan')
            elif change=='evidence': bad['items'][0]['tags'][0]['evidence']=''
            else: bad['items'][0]['tags']*=7
            with self.assertRaises(ValueError): validate_items(bad,['I0001','I0002'])

    def test_reasoning_and_fenced_content(self):
        self.assertEqual(parse_response(raw(answer(['I0001']))), answer(['I0001']))
        with self.assertRaises(ValueError): parse_response({'choices':[{'message':{'content':None,'reasoning_content':'{}'}}]})

    def test_real_image_payload_privacy_and_resume(self):
        self.sampled()
        client=MockClient()
        first=self.classify(client,max_batches=1)
        self.assertEqual(first['new_batches'],1)
        encoded=json.dumps(client.calls)
        self.assertNotIn('SECRET',encoded)
        self.assertNotIn('image_path',encoded)
        blocks=client.calls[0][0]['content']
        images=[b for b in blocks if b['type']=='image_url']
        self.assertEqual(len(images),4)
        self.assertTrue(all(b['image_url']['url'].startswith('data:image/png;base64,') for b in images))
        resumed=self.classify(client)
        self.assertEqual(resumed['cached_batches'],1)
        self.assertEqual(resumed['new_batches'],1)
        again=self.classify(client)
        self.assertEqual(again['cached_batches'],2)
        self.assertEqual(len(client.calls),2)
        summary=report(self.run)
        self.assertEqual(summary['successful_unique_images'],8)
        self.assertTrue(summary['round_complete'])
        self.assertFalse(summary['full_library_complete'])
        self.assertEqual(summary['usage']['total_tokens'],60)

    def test_batch_variable_last_id_set(self):
        self.sampled(5)
        client=MockClient(); self.classify(client)
        self.assertEqual(len(client.calls),2)
        self.assertEqual(report(self.run)['successful_unique_images'],5)

    def test_one_repair_and_raw_attempts(self):
        self.sampled(4)
        client=MockClient(bad=1)
        self.classify(client)
        self.assertEqual(len(client.calls),2)
        self.assertEqual(len(list((self.run/'responses').glob('*.json'))),2)
        self.assertEqual(report(self.run)['repair_or_rerun_attempts'],1)

    def test_invalid_repair_failure_then_resume(self):
        self.sampled(4)
        with self.assertRaises(ValueError): self.classify(MockClient(bad=3))
        failed=report(self.run)
        self.assertEqual(failed['successful_unique_images'],0)
        self.assertEqual(failed['job_status_counts'],{'failed':1})
        self.classify()
        self.assertEqual(report(self.run)['successful_unique_images'],4)

    def test_transport_failure_no_synthetic_success(self):
        self.sampled(4)
        with self.assertRaises(RuntimeError): self.classify(MockClient(fail=True))
        summary=report(self.run)
        self.assertEqual(summary['successful_unique_images'],0)
        self.assertEqual(summary['job_status_counts'],{'failed':1})

    def test_changed_image_and_stop(self):
        round_data=self.sampled(4)
        (self.run/'STOP').touch()
        client=MockClient(); self.classify(client)
        self.assertEqual(len(client.calls),0)
        (self.run/'STOP').unlink()
        path=Path(round_data['images'][0]['representative']['image_path'])
        Image.new('RGB',(2,2),'black').save(path)
        with self.assertRaises(ValueError): self.classify(client)
        self.assertEqual(len(client.calls),0)

    def test_discover_explicit_model_and_bounded_http_retries(self):
        client=Client('http://mock.invalid/v1','wanted',1)
        with patch.object(client,'_request',return_value={'data':[{'id':'other'}]}):
            with self.assertRaises(ValueError): client.discover()
        error=urllib.error.HTTPError('http://mock',503,'busy',{},None)
        with patch('urllib.request.urlopen',side_effect=error) as request, patch('time.sleep'):
            with self.assertRaises(RuntimeError): client.chat([])
            self.assertEqual(request.call_count,3)
        error=urllib.error.HTTPError('http://mock',400,'bad',{},None)
        with patch('urllib.request.urlopen',side_effect=error) as request:
            with self.assertRaises(RuntimeError): client.chat([])
            self.assertEqual(request.call_count,1)

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

    def test_qwen_text_template_setting_is_explicit_and_cached_separately(self):
        transport=Client('http://mock.invalid/v1','wanted',1,enable_thinking=False)
        with patch.object(transport,'_request',return_value=raw({'proposals':[]})) as request:
            transport.chat([{'role':'user','content':'text'}],max_tokens=2048)
            self.assertEqual(request.call_args.args[1]['chat_template_kwargs'],{'enable_thinking':False})
        self.sampled(4)
        default=MockClient(); self.classify(default)
        no_thinking=MockClient(); no_thinking.enable_thinking=False
        self.classify(no_thinking)
        self.assertEqual(len(no_thinking.calls),1)
        self.classify(no_thinking)
        self.assertEqual(len(no_thinking.calls),1)
        self.assertEqual(report(self.run)['successful_unique_images'],4)

    def test_expired_lease_is_reclaimed(self):
        self.sampled(4); self.classify()
        db=connect(self.run)
        with db:
            db.execute("UPDATE jobs SET status='running',started_at=0,result=NULL")
            db.execute('DELETE FROM predictions')
        db.close()
        client=MockClient(); self.classify(client)
        self.assertEqual(len(client.calls),1)
        self.assertEqual(report(self.run)['successful_unique_images'],4)


if __name__=='__main__': unittest.main()
