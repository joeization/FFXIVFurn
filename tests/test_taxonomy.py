"""Taxonomy safety tests, entirely local: no image inference or model services."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ffxiv_furniture.classification.state import read_json, write_json
from ffxiv_furniture.classification.taxonomy import (counts, grouping, materialize_observations,
    reclassify, resolve_id)
from ffxiv_furniture.classification.validation import validate_items
from ffxiv_furniture.classification.vocabulary import (apply_vocab, discovery_observations, inventory,
    save_version, validate_vocab)
from ffxiv_furniture.classification.prompts import visual_prompt


def concept(cid, name, category='material'):
    return {'concept_id': cid, 'key': category+':'+name, 'name': name, 'category': category,
            'definition': 'Visible appearance only.', 'include': [], 'exclude': [], 'examples': [],
            'negative_examples': [], 'original_names': [name], 'aliases': [], 'status': 'provisional'}


def fixture():
    return {'schema_version': 1, 'concepts': [concept('a','wood-like'),concept('b','wood')],
            'proposals': [], 'decisions': [], 'relations': [], 'frozen': False}


def proposal(status='accepted'):
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
                vocab = fixture(); vocab['proposals'] = [proposal(status)]
                file = other/'candidate.json'; write_json(file,vocab)
                apply_vocab(other,file)
                self.assertEqual(read_json(other/'vocab-latest.json')['concepts'][0]['status'],'provisional')

    def test_apply_alias_preserves_names_and_records_scoped_provenance(self):
        vocab=fixture(); save_version(self.root,vocab)
        vocab['proposals']=[proposal()]
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
        vocab=fixture()
        for source,target in [('a','b'),('b','a')]:
            c=next(c for c in vocab['concepts'] if c['concept_id']==source)
            c.update(status='merged',merged_into=target)
        with self.assertRaises(ValueError): validate_vocab(vocab)
        vocab=fixture()
        vocab['concepts'][0]['aliases']=[{'name':'wood','scope':'material','ambiguous':False}]
        with self.assertRaises(ValueError): validate_vocab(vocab)
        vocab['concepts'][0]['aliases'][0]['ambiguous']=True
        validate_vocab(vocab)

    def test_duplicate_alias_relation_proposal_references_rejected(self):
        for kind in ('alias','relation','proposal'):
            vocab=fixture()
            if kind=='alias':
                alias={'name':'timber appearance','scope':'material','ambiguous':False}
                vocab['concepts'][0]['aliases']=[alias,deepcopy(alias)]
            elif kind=='relation':
                relation={'type':'related','source':'a','target':'b'}
                vocab['relations']=[relation,deepcopy(relation)]
            else:
                vocab['proposals']=[proposal(),proposal()]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.apply(vocab)

    def test_alias_unknown_provenance_rejected(self):
        vocab=fixture()
        vocab['concepts'][0]['aliases']=[{'name':'timber','scope':'material','ambiguous':False,'source_concept_id':'absent'}]
        with self.assertRaises(ValueError): validate_vocab(vocab)

    def test_existing_proposal_payload_cannot_be_rewritten(self):
        vocab=fixture(); vocab['proposals']=[proposal('pending')]; save_version(self.root,vocab)
        vocab['proposals'][0].update(source='b',target='a',status='accepted')
        with self.assertRaises(ValueError): self.apply(vocab)

    def test_decision_status_change_does_not_silently_auto_apply(self):
        vocab=fixture(); vocab['proposals']=[proposal('rejected')]
        _, applied=self.apply(vocab)
        applied['proposals'][0]['status']='accepted'
        with self.assertRaises(ValueError): self.apply(applied)

    def test_category_move_is_new_identity_and_preserves_evidence(self):
        vocab=fixture(); vocab['concepts'][0]=concept('a','carved','style')
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
        vocab=fixture(); save_version(self.root,vocab)
        vocab['concepts'][0].update(category='form',key='form:wood-like')
        with self.assertRaises(ValueError): self.apply(vocab)

    def test_category_refactor_without_exact_links_or_evidence_blocked(self):
        for change in ('no-evidence','wrong-category','no-reciprocal','duplicate-supersedes'):
            vocab=fixture(); vocab['concepts'][0]=concept('a','carved','style')
            raw=[{'concept_id':'a','category':'style','image_hash':'sha','evidence':'incision'}]
            reclassify(vocab,'a','ornament',raw,'Decoration')
            relation=vocab['relations'][0]
            if change=='no-evidence': relation['source_observations']=[]
            elif change=='wrong-category': relation['source_observations'][0]['category']='material'
            elif change=='no-reciprocal': vocab['concepts'][-1]['supersedes']=[]
            else: vocab['concepts'][-1]['supersedes']=['a','a']
            with self.subTest(change=change), self.assertRaises(ValueError): validate_vocab(vocab)

    def test_missing_source_observations_blocks_category_move(self):
        with self.assertRaises(ValueError): reclassify(fixture(),'a','form',[],'Unsupported')

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
                'vocabulary':{'concepts':[concept('brown','brown','color')]},
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


if __name__=='__main__': unittest.main()
