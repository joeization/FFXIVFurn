"""Persistent CLI protocol: many requests on one already-initialized MCP session."""

import asyncio, io, json, runpy, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class PersistentClientTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Import outside the asynchronous test loop; legacy versions ran main
        # unconditionally, so close that coroutine rather than spawning a server.
        with patch("asyncio.run", side_effect=lambda c: c.close()):
            cls.mod = runpy.run_path(
                str(ROOT / "scripts/deco_mcp_client.py"), run_name="deco_client_test"
            )

    def api(self):
        self.assertTrue("interactive" in self.mod, "persistent command loop is missing")
        return self.mod["interactive"]

    async def test_many_commands_share_one_session_and_keep_request_ids(self):
        call = self.api()
        seen = []

        class Session:
            async def call_tool(self, tool, args):
                seen.append((tool, args))
                return SimpleNamespace(
                    isError=False,
                    content=[
                        SimpleNamespace(type="text", text=json.dumps({"sequence": len(seen)}))
                    ],
                )

        source = io.StringIO(
            "\n".join(
                [
                    json.dumps({"id": 0, "tool": "status"}),
                    json.dumps(
                        {"id": "second", "tool": "inspect", "arguments": {"level": "ground"}}
                    ),
                    "quit",
                    "",
                ]
            )
        )
        sink = io.StringIO()
        await call(Session(), source, sink)
        rows = [json.loads(x) for x in sink.getvalue().splitlines()]
        self.assertEqual(rows[0]["event"], "ready")
        replies = [r for r in rows if "tool" in r]
        self.assertEqual([r["id"] for r in replies], [0, "second"])
        self.assertEqual(seen, [("status", {}), ("inspect", {"level": "ground"})])
        self.assertEqual(rows[-1]["event"], "closed")

    async def test_server_uses_current_interpreter_not_a_repository_venv(self):
        import sys

        commands = []

        def stop_before_spawn(params):
            commands.append(params.command)
            raise RuntimeError("test barrier before process spawn")

        main = self.mod["main"]
        with patch.dict(main.__globals__, {"stdio_client": stop_before_spawn}):
            with self.assertRaisesRegex(RuntimeError, "test barrier"):
                await main(["list"])
        self.assertEqual(commands, [sys.executable])

    async def test_one_shot_call_reports_tool_failure_as_nonzero_exit(self):
        from contextlib import asynccontextmanager, redirect_stdout
        from unittest.mock import AsyncMock

        session = SimpleNamespace(
            initialize=AsyncMock(
                return_value=SimpleNamespace(
                    serverInfo=SimpleNamespace(name="mock"), protocolVersion="test"
                )
            ),
            call_tool=AsyncMock(return_value=SimpleNamespace(isError=True, content=[])),
        )

        @asynccontextmanager
        async def stdio(params):
            yield ("reader", "writer")

        @asynccontextmanager
        async def client(*args):
            yield session

        main = self.mod["main"]
        with patch.dict(
            main.__globals__, {"stdio_client": stdio, "ClientSession": client}
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(await main(["call", "status", "{}"]), 1)
            session.call_tool.return_value.isError = False
            self.assertEqual(await main(["call", "status", "{}"]), 0)

    async def test_invalid_request_does_not_close_connection(self):
        call = self.api()

        class Session:
            async def call_tool(self, tool, args):
                return SimpleNamespace(
                    isError=True,
                    content=[SimpleNamespace(type="text", text="Tool error: not JSON")],
                )

        sink = io.StringIO()
        await call(Session(), io.StringIO('not json\n{"id":"x","tool":"status"}\nquit\n'), sink)
        rows = [json.loads(x) for x in sink.getvalue().splitlines()]
        self.assertTrue(rows[1]["isError"])
        self.assertEqual(rows[2]["id"], "x")
        self.assertTrue(rows[2]["isError"])
        self.assertEqual(rows[2]["texts"], ["Tool error: not JSON"])


if __name__ == "__main__":
    unittest.main()
