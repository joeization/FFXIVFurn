"""Persistent MCP CLI protocol and real stdio driver lifecycle and errors."""
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
import unittest
from ffxiv_furniture.deco.core import Session
from scripts.deco_driver import DecoClient, ToolCallError
from tests.support import ROOT, SEEDS, needs_seed, session
from types import SimpleNamespace
from unittest.mock import patch

class DriverLifecycleTests(unittest.TestCase):
    SEED = ROOT / 'data/seeds/small-seed.json'

    def setUp(self):
        self.name = f'zz-driver-lifecycle-{os.getpid()}'
        self.dir = ROOT / 'outputs/deco-sessions' / self.name
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))

    @needs_seed('Small')
    def test_ctor_failure_kills_child_and_closes_stderr(self):
        from scripts import deco_driver
        rec = []
        orig = subprocess.Popen

        class Rec(orig):

            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                rec.append((self, k.get('stderr')))
        with patch.object(deco_driver.subprocess, 'Popen', Rec):
            with self.assertRaises((TimeoutError, deco_driver.ToolCallError)):
                deco_driver.DecoClient(self.name, self.SEED, ready_timeout=0.3)
        p, err = rec[0]
        self.assertIsNotNone(p.poll())
        self.assertTrue(err.closed)

    def test_bad_seed_error_carries_stderr_tail(self):
        from scripts.deco_driver import DecoClient, ToolCallError
        with self.assertRaises(ToolCallError) as c:
            DecoClient(self.name, ROOT / 'data/seeds/zz-does-not-exist.json', ready_timeout=120)
        self.assertIn('exited', str(c.exception))
        self.assertTrue('DECO_SEED' in str(c.exception) or 'Cannot read' in str(c.exception) or 'Traceback' in str(c.exception), str(c.exception)[-400:])

    @needs_seed('Small')
    def test_payload_closed_and_fast_death_detection(self):
        from scripts.deco_driver import DecoClient, ToolCallError
        c = DecoClient(self.name, self.SEED, max_patch='7.2')
        try:
            with self.assertRaises(ToolCallError) as e:
                c('batch', {'operations': [dict(op='place', name='No Such Item', position=[0, 0, 0])]})
            self.assertIsInstance(e.exception.payload, dict)
            self.assertIn('code', e.exception.payload)
            self.assertIn('message', e.exception.payload)
            with self.assertRaises(ToolCallError) as e:
                c('no_such_tool', {})
            self.assertTrue(hasattr(e.exception, 'payload'))
            c._p.kill()
            t = time.time()
            with self.assertRaises(ToolCallError):
                c('status')
            self.assertLess(time.time() - t, 3.0)
        finally:
            c.close()
        with self.assertRaises(ToolCallError) as e:
            c('status')
        self.assertIn('client closed', str(e.exception))

class PersistentClientTests(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        with patch('asyncio.run', side_effect=lambda c: c.close()):
            cls.mod = runpy.run_path(str(ROOT / 'scripts/deco_mcp_client.py'), run_name='deco_client_test')

    def api(self):
        self.assertTrue('interactive' in self.mod, 'persistent command loop is missing')
        return self.mod['interactive']

    async def test_many_commands_share_one_session_and_keep_request_ids(self):
        call = self.api()
        seen = []

        class Session:

            async def call_tool(self, tool, args):
                seen.append((tool, args))
                return SimpleNamespace(isError=False, content=[SimpleNamespace(type='text', text=json.dumps({'sequence': len(seen)}))])
        source = io.StringIO('\n'.join([json.dumps({'id': 0, 'tool': 'status'}), json.dumps({'id': 'second', 'tool': 'inspect', 'arguments': {'level': 'ground'}}), 'quit', '']))
        sink = io.StringIO()
        await call(Session(), source, sink)
        rows = [json.loads(x) for x in sink.getvalue().splitlines()]
        self.assertEqual(rows[0]['event'], 'ready')
        replies = [r for r in rows if 'tool' in r]
        self.assertEqual([r['id'] for r in replies], [0, 'second'])
        self.assertEqual(seen, [('status', {}), ('inspect', {'level': 'ground'})])
        self.assertEqual(rows[-1]['event'], 'closed')

    async def test_server_uses_current_interpreter_not_a_repository_venv(self):
        import sys
        commands = []

        def stop_before_spawn(params):
            commands.append(params.command)
            raise RuntimeError('test barrier before process spawn')
        main = self.mod['main']
        with patch.dict(main.__globals__, {'stdio_client': stop_before_spawn}):
            with self.assertRaisesRegex(RuntimeError, 'test barrier'):
                await main(['list'])
        self.assertEqual(commands, [sys.executable])

    async def test_one_shot_call_reports_tool_failure_as_nonzero_exit(self):
        from contextlib import asynccontextmanager, redirect_stdout
        from unittest.mock import AsyncMock
        session = SimpleNamespace(initialize=AsyncMock(return_value=SimpleNamespace(serverInfo=SimpleNamespace(name='mock'), protocolVersion='test')), call_tool=AsyncMock(return_value=SimpleNamespace(isError=True, content=[])))

        @asynccontextmanager
        async def stdio(params):
            yield ('reader', 'writer')

        @asynccontextmanager
        async def client(*args):
            yield session
        main = self.mod['main']
        with patch.dict(main.__globals__, {'stdio_client': stdio, 'ClientSession': client}), redirect_stdout(io.StringIO()):
            self.assertEqual(await main(['call', 'status', '{}']), 1)
            session.call_tool.return_value.isError = False
            self.assertEqual(await main(['call', 'status', '{}']), 0)

    async def test_invalid_request_does_not_close_connection(self):
        call = self.api()

        class Session:

            async def call_tool(self, tool, args):
                return SimpleNamespace(isError=True, content=[SimpleNamespace(type='text', text='Tool error: not JSON')])
        sink = io.StringIO()
        await call(Session(), io.StringIO('not json\n{"id":"x","tool":"status"}\nquit\n'), sink)
        rows = [json.loads(x) for x in sink.getvalue().splitlines()]
        self.assertTrue(rows[1]['isError'])
        self.assertEqual(rows[2]['id'], 'x')
        self.assertTrue(rows[2]['isError'])
        self.assertEqual(rows[2]['texts'], ['Tool error: not JSON'])

@needs_seed('Small')
class DecoDriverTests(unittest.TestCase):

    def setUp(self):
        self.name = f'zz-driver-test-{os.getpid()}'
        self.dir = ROOT / 'outputs/deco-sessions' / self.name
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))

    def test_round_trip_errors_and_clean_close(self):
        journal = self.dir / 'journal.jsonl'
        with DecoClient(self.name, SEEDS / 'small-seed.json', max_patch='7.2', journal=journal) as c:
            st = c('status')
            self.assertEqual((st['house_size'], st['limit'], st['max_patch'], st['count']), ('Small', 300, 7.2, 0))
            r = c('batch', {'operations': [dict(op='place', instance_id='a', name='Hingan Bench', position=[0, -3, 0], yaw_deg=0)]})
            self.assertTrue(r['ok'])
            self.assertEqual(r['count'], 1)
            with self.assertRaises(ToolCallError) as e:
                c('batch', {'operations': [dict(op='place', name='No Such Item', position=[0, 0, 0])]})
            self.assertIn('UNKNOWN', str(e.exception).upper())
            self.assertEqual(c('status')['count'], 1)
        self.assertEqual(c.returncode, 0)
        rows = [json.loads(x) for x in journal.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([r['tool'] for r in rows], ['status', 'batch', 'batch', 'status'])
        self.assertEqual([r['ok'] for r in rows], [True, True, False, True])
        self.assertEqual(rows[1]['revision'], 1)
        self.assertIn('error', rows[2])
        self.assertTrue(all((len(json.dumps(r)) < 2000 for r in rows)))
        self.assertTrue(all(('result' not in r for r in rows)))
        self.assertTrue((self.dir / 'stderr.log').is_file())
