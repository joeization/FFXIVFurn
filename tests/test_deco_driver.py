"""Real stdio round-trip through the reusable DecoClient (one long-lived server per design session)."""
import json
import os
import shutil
import unittest
from pathlib import Path

from scripts.deco_driver import DecoClient, ToolCallError

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data/seeds/small-seed.json'


@unittest.skipUnless(SEED.exists(), 'local Small seed absent')
class DecoDriverTests(unittest.TestCase):
    def setUp(self):
        self.name = f'zz-driver-test-{os.getpid()}'
        self.dir = ROOT / 'outputs/deco-sessions' / self.name
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))

    def test_round_trip_errors_and_clean_close(self):
        journal = self.dir / 'journal.jsonl'
        with DecoClient(self.name, SEED, max_patch='7.2', journal=journal) as c:
            st = c('status')
            self.assertEqual((st['house_size'], st['limit'], st['max_patch'], st['count']), ('Small', 300, 7.2, 0))
            r = c('batch', {'operations': [dict(op='place', instance_id='a', name='Hingan Bench', position=[0, -3, 0], yaw_deg=0)]})
            self.assertTrue(r['ok']); self.assertEqual(r['count'], 1)
            with self.assertRaises(ToolCallError) as e:
                c('batch', {'operations': [dict(op='place', name='No Such Item', position=[0, 0, 0])]})
            self.assertIn('UNKNOWN', str(e.exception).upper())
            self.assertEqual(c('status')['count'], 1)   # rejected batch changed nothing
        self.assertEqual(c.returncode, 0)
        rows = [json.loads(x) for x in journal.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([r['tool'] for r in rows], ['status', 'batch', 'batch', 'status'])
        self.assertEqual([r['ok'] for r in rows], [True, True, False, True])
        self.assertEqual(rows[1]['revision'], 1); self.assertIn('error', rows[2])
        self.assertTrue(all(len(json.dumps(r)) < 2000 for r in rows))   # one short line per call, not the full result
        self.assertTrue(all('result' not in r for r in rows))
        self.assertTrue((self.dir / 'stderr.log').is_file())   # one server log per session


if __name__ == '__main__':
    unittest.main()
