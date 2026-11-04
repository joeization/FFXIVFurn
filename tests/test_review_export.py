import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('export_tag_review',Path(__file__).resolve().parents[1]/'scripts/export_tag_review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ReviewExportTests(unittest.TestCase):
    def test_export_preserves_original_and_escapes_spreadsheet_formulas(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'vocab.json'
            value={'concepts':[{'concept_id':'c1','key':'color:red','category':'color','name':'=bad',
                   'status':'accepted','definition':'紅色','frequency':{'unique_images':2}}],
                   'proposals':[{'proposal_id':'p1','action':'keep','source':'c1','reason':'@danger'}]}
            source.write_text(json.dumps(value),encoding='utf-8');before=source.read_bytes()
            stats=module.export(source,root/'out')
            self.assertEqual(stats['concept_rows'],1)
            self.assertEqual(source.read_bytes(),before)
            with (root/'out/tags.csv').open(encoding='utf-8-sig',newline='') as f:
                row=next(csv.DictReader(f));self.assertEqual(row['name'],"'=bad");self.assertEqual(row['source_unique_images'],'2')
            with (root/'out/decisions.csv').open(encoding='utf-8-sig',newline='') as f:
                self.assertEqual(next(csv.DictReader(f))['reason'],"'@danger")

    def test_duplicate_concept_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'v.json';p.write_text(json.dumps({'concepts':[{'concept_id':'c'},{'concept_id':'c'}]}))
            with self.assertRaises(ValueError):module.export(p,Path(temp)/'out')
