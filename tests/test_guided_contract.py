import unittest
from ffxiv_furniture.classification.prompts import visual_prompt
from ffxiv_furniture.classification.validation import validate_items


class GuidedContractTests(unittest.TestCase):
    def test_guided_example_never_shows_explore_tag_schema(self):
        p=visual_prompt('guided',{'concepts':[]})
        self.assertNotIn('"tags":[{"category"',p)
        self.assertIn('"tags":[{"key"',p)
        self.assertIn('EXACTLY key, confidence, evidence',p)
        self.assertIn('definition,reason,confidence,evidence',p)

    def test_explore_still_uses_free_names(self):
        self.assertIn('"tags":[{"category"',visual_prompt('explore'))

    def test_repair_error_explains_exact_fields(self):
        value={'items':[{'id':'x','visual_description':'visible','tags':[{'key':'color:red','category':'color','confidence':1,'evidence':'red'}], 'proposed_tags':[],'uncertain':[]}]}
        vocab={'concepts':[{'key':'color:red','status':'accepted'}]}
        with self.assertRaisesRegex(ValueError,'expected.*confidence.*evidence.*key.*got'):
            validate_items(value,['x'],'guided',vocab)
