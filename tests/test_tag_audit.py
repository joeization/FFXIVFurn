"""Local fixtures only; audit never calls a model or modifies source SQLite."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from ffxiv_furniture.classification.audit import check_asset,audit_final
from ffxiv_furniture.classification.state import digest,write_json,read_json


def asset(key='a',name='Manor Dressing Table',category='Furniture/Table'):
    return {'asset_key':key,'name':name,'source_category':category,'scope':'interior','item_id':None,'image_path':'fixture.png'}


def prediction(anon,*tags):
    return {'id':anon,'visual_description':'Explicit test fixture.','tags':[{'key':k,'confidence':.8,'evidence':'fixture'} for k in tags],'uncertain':[],'proposed_tags':[]}


class TagAuditTests(unittest.TestCase):
    def test_known_dressing_table_bed_conflict(self):
        issues=check_asset(asset(),prediction('x','form:bed'),{'form:bed'})
        self.assertEqual({i['rule'] for i in issues},{'category_object_conflict','name_object_conflict'})
        self.assertIn('high',{i['priority'] for i in issues})
        self.assertTrue(check_asset(asset(name='Glade Lantern',category='Lighting'),prediction('x','form:bed')))

    def test_sofa_in_chair_category_not_an_error(self):
        self.assertEqual(check_asset(asset(name='Leather Sofa',category='Furniture/Chair'),prediction('x','form:sofa')),[])
        self.assertEqual(check_asset(asset(name='Bench',category='Furniture/Chair'),prediction('x','form:sofa')),[])

    def test_geometry_and_color_are_not_function(self):
        self.assertEqual(check_asset(asset(),prediction('x','form:rectangular','color:purple','ornament:bat wings')),[])

    def test_bedside_and_compound_names(self):
        self.assertEqual(check_asset(asset(name='Bedside Table'),prediction('x','form:table')),[])
        self.assertEqual(check_asset(asset(name='Sofa Bed',category='Furniture/Chair'),prediction('x','form:bed')),[])
        self.assertEqual(check_asset(asset(name='Miniature Bed',category='Item/Stuffed'),prediction('x','form:table')),[])

    def test_inactive_key_is_review_not_silent_repair(self):
        p=prediction('x','form:bed')
        issues=check_asset(asset(),p,set())
        self.assertIn('inactive_or_unknown_tag',{i['rule'] for i in issues})
        self.assertEqual(p['tags'][0]['key'],'form:bed')

    def setup_run(self,path):
        path.mkdir(exist_ok=True)
        h1,h2='a'*64,'b'*64
        maps=[asset(),asset('variant',name='Other Dressing Table')]
        vocab={'frozen':True,'concepts':[{'key':k,'status':'accepted'} for k in ['form:bed','form:table','form:sofa']]}
        plan={'round':6,'kind':'final-all','vocabulary':vocab,'vocab_hash':digest(vocab),'images':[
            {'image_hash':h1,'anon_id':'I1','representative':maps[0],'mappings':maps},
            {'image_hash':h2,'anon_id':'I2','representative':asset('sofa','Leather Sofa','Furniture/Chair'),'mappings':[asset('sofa','Leather Sofa','Furniture/Chair')]}]}
        plan['round_hash']=digest(plan);write_json(path/'round-006.json',plan)
        with closing(sqlite3.connect(path/'state.sqlite3')) as c:
            c.executescript('CREATE TABLE jobs(id TEXT,kind TEXT,phase TEXT,status TEXT,input TEXT,finished_at REAL);CREATE TABLE predictions(job_id TEXT,anon_id TEXT,image_hash TEXT,data TEXT);')
        return plan

    def add(self,path,plan,jid,index,tag,time=1,round_hash=None):
        row=plan['images'][index]
        metadata={'round_hash':round_hash or plan['round_hash'],'vocab_hash':plan['vocab_hash']}
        with closing(sqlite3.connect(path/'state.sqlite3')) as c:
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',(jid,'visual','final','succeeded',json.dumps({'metadata':metadata}),time))
            c.execute('INSERT INTO predictions VALUES(?,?,?,?)',(jid,row['anon_id'],row['image_hash'],json.dumps(prediction(row['anon_id'],tag))))
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

if __name__=='__main__':unittest.main()
