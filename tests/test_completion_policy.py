import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('finish_exploration',Path(__file__).resolve().parents[1]/'scripts/finish_exploration.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class CompletionPolicyTests(unittest.TestCase):
    def test_only_appearance_hedges_are_equivalent(self):
        for label in ['wood','wood-like','wood-look','wood appearance','wood-like appearance']:
            self.assertEqual(module.equivalence_label(label),'wood')
        self.assertNotEqual(module.equivalence_label('dark wood appearance'),'wood')
        self.assertNotEqual(module.equivalence_label('wood-like frame'),'wood')
        self.assertNotEqual(module.equivalence_label('painted wood'),'wood')
        self.assertNotEqual(module.equivalence_label('white fabric'),'fabric')

    def test_finish_script_has_no_final_execution_stage(self):
        source=(Path(__file__).resolve().parents[1]/'scripts/finish_exploration.py').read_text(encoding='utf-8')
        self.assertNotIn("visual('final",source)
        self.assertIn("visual('discover-all-remaining','discover-rest'",source)
        self.assertIn("'no_remote_model_calls':True",source)
