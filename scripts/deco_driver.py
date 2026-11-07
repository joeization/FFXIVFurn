"""Drive one long-lived ffxiv-deco MCP server from Python (an agent kernel or a plan script).

    from scripts.deco_driver import DecoClient
    with DecoClient('my-design', 'data/seeds/small-seed.json', max_patch='7.2', journal='outputs/deco-sessions/my-design/calls.jsonl') as c:
        c('status'); c('batch', {'operations': [...]}); c('render_sheet', {'views': [...]})

Wraps `scripts/deco_mcp_client.py interactive` (real stdio MCP). One server per design session keeps decoded assets and
render caches warm across look -> edit rounds. The subprocess runs isolated (-I, no inherited PYTHONPATH/PYTHONHOME), so
an agent's own site-packages cannot shadow the project's MCP/Pydantic. Tool errors raise ToolCallError with the server's
raw text; a rejected batch leaves the session unchanged. If the hosting interpreter restarts, open a new DecoClient for the
same session name: saved state is on disk, only the warm caches are lost.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ToolCallError(RuntimeError):
    pass


class DecoClient:
    def __init__(self, session, seed, *, scope=None, max_patch=None, journal=None, python=None, ready_timeout=300):
        env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
        env.update(DECO_SESSION=str(session), DECO_SEED=str(Path(seed).resolve()), PYTHONIOENCODING='utf-8')
        if scope: env['DECO_SCOPE'] = scope
        if max_patch: env['DECO_MAX_PATCH'] = str(max_patch)
        self.journal = Path(journal) if journal else None
        if self.journal: self.journal.parent.mkdir(parents=True, exist_ok=True)
        exe = python or (ROOT / '.venv/Scripts/python.exe' if (ROOT / '.venv/Scripts/python.exe').exists() else Path(sys.executable))
        sess_dir = ROOT / 'outputs/deco-sessions' / str(session); sess_dir.mkdir(parents=True, exist_ok=True)
        self._err = (sess_dir / 'stderr.log').open('a', encoding='utf-8')   # one server log per session, appended
        self._p = subprocess.Popen([str(exe), '-X', 'utf8', '-I', 'scripts/deco_mcp_client.py', 'interactive'], cwd=ROOT, env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._err,
                                   text=True, encoding='utf-8', bufsize=1)
        assert self._p.stdin is not None and self._p.stdout is not None
        self._in, self._out = self._p.stdin, self._p.stdout
        self._q = queue.Queue(); self._n = 0
        threading.Thread(target=self._pump, daemon=True).start()
        deadline = time.time() + ready_timeout
        while True:
            line = self._next(deadline)
            if '"ready"' in line:
                self.pid = json.loads(line).get('client_pid'); break

    def _pump(self):
        for line in self._out: self._q.put(line)

    def _next(self, deadline):
        while True:
            try: return self._q.get(timeout=max(0.1, min(5, deadline - time.time())))
            except queue.Empty:
                if self._p.poll() is not None: raise ToolCallError(f'MCP client exited with code {self._p.returncode}')
                if time.time() > deadline: raise TimeoutError('MCP client did not answer in time')

    def __call__(self, tool, arguments=None, timeout=600):
        self._n += 1; rid = f'r{self._n}'
        self._in.write(json.dumps({'id': rid, 'tool': tool, 'arguments': arguments or {}}) + '\n'); self._in.flush()
        deadline = time.time() + timeout
        while True:
            try: msg = json.loads(self._next(deadline))
            except json.JSONDecodeError: continue
            if msg.get('id') != rid: continue
            texts = msg.get('texts') or [msg.get('error')]
            out = texts[0] if len(texts) == 1 else texts
            if self.journal:   # one short line per call: what was asked and what happened, not the full result
                row = {'tool': tool, 'arguments': arguments or {}, 'ok': not msg.get('isError')}
                if isinstance(out, dict):
                    row.update({k: out[k] for k in ('revision', 'count', 'image') if k in out})
                if msg.get('isError'):
                    row['error'] = str(out)[:500]
                line = json.dumps(row, ensure_ascii=False, default=str)
                if len(line) > 1500:   # very large argument lists (big batches) keep only their size
                    row['arguments'] = {'_omitted_bytes': len(json.dumps(arguments, default=str))}
                    line = json.dumps(row, ensure_ascii=False, default=str)
                with self.journal.open('a', encoding='utf-8') as f:
                    f.write(line + '\n')
            if msg.get('isError'): raise ToolCallError(str(out))
            return out

    @property
    def returncode(self):
        return self._p.returncode

    def close(self, timeout=60):
        if self._p.poll() is None:
            try:
                self._in.write('quit\n'); self._in.flush(); self._p.wait(timeout=timeout)
            except (OSError, subprocess.TimeoutExpired):
                self._p.kill(); self._p.wait()
        self._err.close()
        return self._p.returncode

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()
