import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'scripts/finalize_and_classify.py'
spec=importlib.util.spec_from_file_location('finalize_and_classify',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class FinalizationContractTests(unittest.TestCase):
    def value(self,**overrides):
        d={'concept_id':'a','status':'accepted','definition':'Visible reddish hue.','reason':'Observable color.'}
        d.update(overrides);return {'decisions':[d]}

    def test_complete_exact_ids(self):
        self.assertEqual(m.validate_decisions(self.value(),['a']),self.value())
        for v in [{'decisions':[]},{'decisions':self.value()['decisions']*2},self.value(concept_id='other')]:
            with self.assertRaises(ValueError):m.validate_decisions(v,['a'])

    def test_no_unsupported_status_or_empty_acceptance(self):
        for changes in [{'definition':''},{'status':'provisional'},{'reason':''},{'new_key':'x'}]:
            with self.assertRaises(ValueError):m.validate_decisions(self.value(**changes),['a'])
        self.assertEqual(m.validate_decisions(self.value(status='unresolved',definition=''),['a'])['decisions'][0]['status'],'unresolved')

    def test_server_schema_binds_ids_and_disallows_fields(self):
        schema=m.decision_format(['a'])['json_schema']
        self.assertTrue(schema['strict'])
        item=schema['schema']['properties']['decisions']['items']
        self.assertFalse(item['additionalProperties'])
        self.assertEqual(item['properties']['concept_id']['enum'],['a'])

    def test_no_tag_items_or_alias_mapping_output(self):
        with self.assertRaises(ValueError):m.validate_decisions({'items':[]},['a'])
        with self.assertRaises(ValueError):m.validate_decisions(dict(self.value(),aliases=[]),['a'])

if __name__=='__main__':unittest.main()
