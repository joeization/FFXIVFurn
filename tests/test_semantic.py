"""Deterministic tests mock ONLY embedding inference; vec0 uses the real extension.

No test downloads or loads model weights. Live model acceptance is separate.
"""
from contextlib import closing, redirect_stdout, redirect_stderr
import importlib.util
import io
import json
import math
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

from ffxiv_furniture import FurnitureDB
from ffxiv_furniture.__main__ import main
from ffxiv_furniture.semantic import (DIMENSION, MODEL, PIPELINE, E5Embedder,
    SemanticError, SemanticIndex, load_sqlite_vec, text_hash, vector_blob)

ROOT = Path(__file__).resolve().parents[1]


def mocked_vectors(texts, *, query=False, batch_size=32):
    # Explicit synthetic fixture: never used by production code.
    values = {'red': (1, 0), 'near': (0.9, 0.1), 'blue': (0, 1), 'changed': (-1, 0)}
    return [vector_blob([*values.get(t, (1, 0)), *([0] * (DIMENSION-2))]) for t in texts]


class EmbeddingTests(unittest.TestCase):
    def test_vector_validation_and_normalization(self):
        blob = vector_blob([3, 4] + [0] * 382)
        values = struct.unpack('<384f', blob)
        self.assertAlmostEqual(values[0], .6)
        self.assertAlmostEqual(values[1], .8)
        for v in ([0]*384, [1]*383, [math.nan]*384, [math.inf]*384):
            with self.assertRaises(ValueError):
                vector_blob(v)
        self.assertEqual(len(text_hash('描述')), 64)
        self.assertNotEqual(text_hash('red'), text_hash('red '))

    def test_prefixes_real_adapter_no_weights(self):
        model = Mock()
        model.embed.side_effect = lambda texts, **kwargs: [[3,4]+[0]*382 for _ in texts]
        embedder = E5Embedder()
        embedder._model = model  # explicit inference mock
        embedder.embed(['red'], batch_size=2)
        self.assertEqual(model.embed.call_args.args[0], ['passage: red'])
        embedder.embed(['red'], query=True)
        self.assertEqual(model.embed.call_args.args[0], ['query: red'])
        model.embed.return_value = []
        model.embed.side_effect = None
        with self.assertRaises(SemanticError):
            embedder.embed(['red'])
        with self.assertRaises(ValueError):
            E5Embedder(model='another-model')

    def test_extension_failure_is_honest(self):
        c = Mock()
        c.enable_load_extension.side_effect = sqlite3.OperationalError('DLL architecture mismatch')
        fake_module = Mock()
        with patch.dict(sys.modules, {'sqlite_vec': fake_module}):
            with self.assertRaisesRegex(SemanticError, 'no fallback'):
                load_sqlite_vec(c)

    @unittest.skipUnless(importlib.util.find_spec('fastembed'), 'optional fastembed not installed')
    def test_registration_metadata_and_runtime_validation_without_download(self):
        import fastembed
        cls = Mock()
        cls.list_supported_models.side_effect = [[], [{'model': MODEL, 'dim':384}]]
        cls.return_value.embedding_size = 384
        with patch.object(fastembed, 'TextEmbedding', cls):
            E5Embedder(cache_dir='custom-cache', local_files_only=True)._load()
        registration = cls.add_custom_model.call_args.kwargs
        self.assertEqual(registration['model'], MODEL)
        self.assertEqual(registration['model_file'], 'onnx/model.onnx')
        self.assertEqual(registration['pooling'].value, 'MEAN')
        self.assertTrue(registration['normalization'])
        self.assertEqual(registration['sources'].hf, MODEL)
        self.assertTrue(cls.call_args.kwargs['local_files_only'])
        cls = Mock()
        cls.list_supported_models.return_value = [{'model': MODEL, 'dim':768}]
        with patch.object(fastembed, 'TextEmbedding', cls):
            with self.assertRaisesRegex(SemanticError, 'metadata dimension'):
                E5Embedder()._load()
        cls.assert_not_called()
        cls = Mock()
        cls.list_supported_models.return_value = [{'model': MODEL, 'dim':384}]
        cls.return_value.embedding_size = 768
        with patch.object(fastembed, 'TextEmbedding', cls):
            with self.assertRaisesRegex(SemanticError, 'runtime embedding dimension'):
                E5Embedder()._load()


@unittest.skipUnless(importlib.util.find_spec('sqlite_vec'), 'optional sqlite-vec not installed')
class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.db = FurnitureDB(':memory:')
        self.addCleanup(self.db.close)
        self.index = SemanticIndex(self.db, local_files_only=True)
        self.mock = patch.object(self.index.embedder, 'embed', side_effect=mocked_vectors).start()
        self.addCleanup(patch.stopall)

    def ids(self, **kwargs):
        return [r['furniture']['id'] for r in self.index.search('red', **kwargs)]

    def seed(self):
        self.db.add_furniture(1, 'nearest but ineligible', 'red', marketable=False, cash_shop=True)
        self.db.add_furniture(2, 'eligible', 'near', marketable=True, cash_shop=False)
        self.db.add_furniture(3, 'unknown', 'blue')
        self.db.add_furniture(4, 'blank', ' \n ')
        self.index.refresh(batch_size=1)

    def test_structure_empty_idempotence_batches_and_no_overwrite(self):
        self.assertEqual(self.index.search('red'), [])
        self.assertEqual(self.index.refresh()['indexed'], 0)
        self.mock.assert_not_called()
        self.seed()
        self.assertEqual(self.db.connection.execute('PRAGMA user_version').fetchone()[0], 4)
        sql = self.db.connection.execute("SELECT sql FROM sqlite_master WHERE name='furniture_vectors'").fetchone()[0]
        self.assertIn('vec0', sql)
        self.assertIn('float[384]', sql)
        self.assertIn('cosine', sql)
        self.assertEqual(self.mock.call_count, 3)
        self.mock.reset_mock()
        stats = self.index.refresh()
        self.assertEqual(stats['indexed'], 0)
        self.assertEqual(stats['unchanged'], 3)
        self.mock.assert_not_called()
        self.assertEqual(self.db.get_furniture(2)['description'], 'near')
        rows = self.db.connection.execute('SELECT * FROM furniture_embedding_metadata ORDER BY furniture_id').fetchall()
        self.assertEqual([r['furniture_id'] for r in rows], [1,2,3])
        self.assertEqual(rows[0]['text_hash'], text_hash('red'))
        self.assertEqual(rows[0]['pipeline'], PIPELINE)
        result = self.index.search('red')[0]
        self.assertAlmostEqual(result['distance'], 0, places=6)
        self.assertAlmostEqual(result['similarity'], 1, places=6)
        json.dumps(result, allow_nan=False)

    def test_hard_filters_before_top_k_all_any_and_unknown(self):
        self.seed()
        a = self.db.add_tag('style', 'a')['id']
        b = self.db.add_tag('color', 'b')['id']
        self.db.add_furniture_tag(2, a)
        self.db.add_furniture_tag(2, b)
        self.db.add_furniture_tag(3, a)
        self.assertEqual(self.ids(top_k=1), [1])
        self.assertEqual(self.ids(top_k=1, marketable=True, cash_shop=False), [2])
        self.assertEqual(self.ids(marketable=False), [1])
        self.assertEqual(self.ids(cash_shop=False), [2])
        self.assertEqual(self.ids(top_k=1, tag_ids=[a,b]), [2])
        self.assertEqual(self.ids(tag_ids=[a,b], tag_mode='any'), [2,3])
        self.assertEqual(self.ids(tag_ids=[a,a]), [2,3])
        self.assertEqual(self.ids(tag_ids=[a,999]), [])
        self.assertEqual(self.ids(tag_ids=[999], tag_mode='any'), [])

    def test_changed_blank_deleted_excluded_before_refresh_and_pruned(self):
        self.seed()
        self.db.update_furniture(1, description='changed')
        self.db.update_furniture(2, description='\n\t ')
        self.db.delete_furniture(3)
        self.assertEqual(self.ids(), [])
        stats = self.index.refresh()
        self.assertEqual(stats['removed'], 3)
        self.assertEqual(stats['indexed'], 1)
        self.assertEqual(self.ids(), [1])
        self.assertEqual(self.db.connection.execute('SELECT rowid FROM furniture_vectors').fetchall()[0][0], 1)
        self.assertEqual(self.db.connection.execute('SELECT COUNT(*) FROM furniture_embedding_metadata').fetchone()[0], 1)

    def test_wrong_model_metadata_repaired_and_missing_vector_rebuilt(self):
        self.seed()
        with self.db.connection:
            self.db.connection.execute("UPDATE furniture_embedding_metadata SET model='wrong' WHERE furniture_id=1")
            self.db.connection.execute('DELETE FROM furniture_vectors WHERE rowid=2')
        self.assertEqual(self.ids(), [3])
        stats = self.index.refresh()
        self.assertEqual(stats['indexed'], 2)
        self.assertEqual(self.ids(), [1,2,3])

    def test_failure_preserves_completed_batches_and_concurrent_change_not_published(self):
        self.db.add_furniture(1, 'one', 'red')
        self.db.add_furniture(2, 'two', 'blue')
        def failing(texts, **kwargs):
            if texts == ['blue']:
                raise SemanticError('explicit mock failure')
            return mocked_vectors(texts, **kwargs)
        self.mock.side_effect = failing
        with self.assertRaises(SemanticError):
            self.index.refresh(batch_size=1)
        self.mock.side_effect = mocked_vectors
        self.assertEqual(self.ids(), [1])
        self.assertEqual(self.index.refresh()['indexed'], 1)
        self.db.update_furniture(2, description='changed')
        def concurrent(texts, **kwargs):
            self.db.update_furniture(2, description='blue')
            return mocked_vectors(texts, **kwargs)
        self.mock.side_effect = concurrent
        self.assertEqual(self.index.refresh()['skipped'], 1)
        self.mock.side_effect = mocked_vectors
        self.assertEqual(self.ids(), [1])

    def test_validation(self):
        for kw in ({'top_k':0}, {'top_k':True}, {'top_k':1001}, {'tag_mode':'bad'},
                   {'tag_ids':[True]}, {'marketable':1}, {'cash_shop':'false'}):
            with self.assertRaises(ValueError):
                self.index.search('red', **kw)
        for q in (' ', None, 3):
            with self.assertRaises(ValueError):
                self.index.search(q)
        for size in (0, True, 1001):
            with self.assertRaises(ValueError):
                self.index.refresh(batch_size=size)

    def test_persistence_base_crud_without_extension_and_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'catalog.db'
            with FurnitureDB(path) as db:
                db.add_furniture(55, 'persisted', 'red')
                index = SemanticIndex(db)
                with patch.object(index.embedder, 'embed', side_effect=mocked_vectors):
                    index.refresh()
            # A NEW process deliberately blocks both optional imports, even with vec0 on disk.
            code = '''import sys
sys.modules['sqlite_vec']=None
sys.modules['fastembed']=None
from ffxiv_furniture import FurnitureDB
with FurnitureDB(sys.argv[1]) as db:
    assert db.get_furniture(55)['description']=='red'
    db.update_furniture(55, name='edited without extension')
    assert db.delete_furniture(55)
'''
            p = subprocess.run([sys.executable, '-c', code, str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            with FurnitureDB(path) as db:
                index = SemanticIndex(db)
                with patch.object(index.embedder, 'embed', side_effect=mocked_vectors) as mock:
                    self.assertEqual(index.search('red'), [])
                    self.assertEqual(index.refresh()['removed'], 1)
                    mock.assert_not_called()
                self.assertEqual(db.connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_real_cli_empty_json_and_invalid_model(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'empty.db')
            def run(*args):
                return subprocess.run([sys.executable, '-m', 'ffxiv_furniture', '--db', path, *args],
                    cwd=ROOT, capture_output=True, text=True)
            p = run('embed-index', '--local-files-only')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout)['indexed'], 0)
            p = run('semantic-search', '--query', 'red', '--local-files-only')
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout), [])
            p = run('embed-index', '--model', 'wrong', '--local-files-only')
            self.assertEqual(p.returncode, 1)
            self.assertIn('supports only', json.loads(p.stderr)['error'])

    def test_v1_migration_coexists_with_semantic_and_cli_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'old.db'
            with closing(sqlite3.connect(path)) as c:
                c.executescript("CREATE TABLE furniture(id INTEGER PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',image_path TEXT,length REAL,width REAL,height REAL,patch TEXT); INSERT INTO furniture(id,name,description) VALUES(7,'old','red'); PRAGMA user_version=1;")
            def cli(*args):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(['--db', str(path), *args])
                self.assertEqual(code, 0, stderr.getvalue())
                return json.loads(stdout.getvalue())
            with patch('ffxiv_furniture.semantic.E5Embedder.embed', side_effect=mocked_vectors):
                self.assertEqual(cli('embed-index', '--batch-size', '1')['indexed'], 1)
                self.assertEqual(cli('semantic-search', '--query', 'red', '--top-k', '1')[0]['furniture']['id'], 7)
            with FurnitureDB(path) as db:
                self.assertEqual(db.get_furniture(7)['description'], 'red')
                self.assertEqual(db.connection.execute('PRAGMA user_version').fetchone()[0], 4)


if __name__ == '__main__':
    unittest.main()
