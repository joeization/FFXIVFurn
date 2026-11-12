import importlib.util
from pathlib import Path
import tempfile
import unittest
from PIL import Image


class SheetJudgeTests(unittest.TestCase):
    def test_layout_and_parser(self):
        path = Path(__file__).resolve().parents[1] / 'scripts/gemini_sheet_judge.py'
        self.assertTrue(path.exists(), 'sheet judge implementation missing')
        spec = importlib.util.spec_from_file_location('sheet_judge', path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'input.png'
            Image.new('RGB', (40, 80), 'red').save(image)
            items = [dict(id=i, image_path=str(image)) for i in range(5)]
            layout = module.render_sheet(items, root / 'sheet.png', columns=4, cell_size=256)
            with Image.open(root / 'sheet.png') as sheet:
                self.assertEqual(sheet.size, (1024, 576))
            self.assertEqual([r['cell'] for r in layout], [1, 2, 3, 4, 5])
        self.assertEqual(module.parse_response('```json\n[{"cell":1,"answer":[]} ]\n```', 1)[0]['answer'], [])
        for text in ['[]', '[{"cell":2}]', '[{"cell":1},{"cell":1}]', '[{"cell":true}]']:
            with self.assertRaises(ValueError):
                module.parse_response(text, 1)

    def test_retry_and_cache_without_network(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('sheet_judge', Path(__file__).resolve().parents[1] / 'scripts/gemini_sheet_judge.py')
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'input.png'
            Image.new('RGB', (10, 10), 'blue').save(image)
            args = dict(task='test', question='colors?', vocabulary=['blue'], cache_dir=root / 'cache')
            item = dict(id=123, image_path=str(image))
            responses = [SimpleNamespace(returncode=0, stdout=json.dumps({'response': '[]'}), stderr=''),
                         SimpleNamespace(returncode=0, stdout=json.dumps({'response': '[{"cell":1,"colors":["blue"]}]'}), stderr='')]
            with patch.object(module.shutil, 'which', return_value='agy'), patch.object(module.time, 'sleep'), patch.object(module.subprocess, 'run', side_effect=responses) as run:
                result = module.judge([item], **args)
                self.assertEqual(run.call_count, 2)
                self.assertEqual(module.judge([item], **args), result)
                self.assertEqual(run.call_count, 2)
                self.assertEqual(result[0]['id'], 123)


if __name__ == '__main__':
    unittest.main()
