"""Source-only distribution tests: no production DB/assets or network required."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/check_distribution.py'
spec = importlib.util.spec_from_file_location('distribution_policy', SCRIPT)
assert spec is not None and spec.loader is not None
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class DistributionTests(unittest.TestCase):
    def test_restricted_paths(self):
        for path in ('data/seed.json', 'outputs/view.png', 'runs/result.json',
                     'nested/catalog.db', 'nested/CATALOG.DB-wal', 'db/backup.sqlite3.bak',
                     'mesh/Tree.UASSET', 'mesh/map.umap', '.env', '.env.local', 'HANDOFF.md'):
            with self.subTest(path=path):
                self.assertTrue(policy.restricted(path))
        for path in ('README.md', 'docs/catalog.md', '.env.example',
                     'ffxiv_furniture/database.py', 'tests/test_distribution.py'):
            self.assertFalse(policy.restricted(path), path)

    def test_directory_audit_fails_closed_and_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'README.md').write_text('source', encoding='utf-8')
            clean = subprocess.run([sys.executable, str(SCRIPT), '--directory', tmp], capture_output=True)
            self.assertEqual(clean.returncode, 0, clean.stderr)
            banned = base / 'backup.sqlite3'
            banned.write_bytes(b'policy test marker, not a database')
            dirty = subprocess.run([sys.executable, str(SCRIPT), '--directory', tmp], capture_output=True)
            self.assertEqual(dirty.returncode, 1)
            self.assertIn(b'backup.sqlite3', dirty.stdout)
            self.assertEqual(banned.read_bytes(), b'policy test marker, not a database')

    def test_git_ignore_rules_cover_outside_data_and_uppercase(self):
        paths = ['data/furniture.sqlite3', 'nested/catalog.db', 'nested/CATALOG.DB-wal',
                 'nested/catalog.sqlite3.bak', 'mesh/Tree.UASSET', 'mesh/map.umap']
        result = subprocess.run(['git', 'check-ignore', '--no-index', '-z', '--stdin'],
                                input=('\0'.join(paths)+'\0').encode(), cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.decode().strip('\0').split('\0')), set(paths))


if __name__ == '__main__':
    unittest.main()
