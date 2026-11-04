"""Call the deco MCP server over real stdio MCP (JSON-RPC) from a client.  Usage:
  python scripts/deco_mcp_client.py list
  python scripts/deco_mcp_client.py call <tool> '<json args>' [<tool> '<json args>' ...]
  python scripts/deco_mcp_client.py interactive
Interactive mode keeps ONE server/session open across JSON-line requests:
  {"id":"r1","tool":"render","arguments":{"view":"entry"}}
  {"id":"b1","tool":"batch","arguments_file":"path/to/batch.json"}
Send quit, exit, {"close":true}, or EOF for graceful shutdown.
Env DECO_SESSION selects the session. Images are saved next to the render and their path printed."""

import asyncio, json, os, sys, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def interactive(session, source, sink):
    """Read many commands without replacing the initialized MCP connection."""

    def emit(value):
        print(json.dumps(value, ensure_ascii=False), file=sink, flush=True)

    emit(
        dict(
            event="ready",
            client_pid=os.getpid(),
            session=os.environ.get("DECO_SESSION", "default"),
            python_executable=sys.executable,
        )
    )
    while True:
        line = await asyncio.to_thread(source.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        request = {}
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
            if request.get("close") is True:
                break
            tool = request.get("tool")
            if not isinstance(tool, str) or not tool:
                raise ValueError("tool must be a nonempty name")
            if "arguments_file" in request:
                if "arguments" in request:
                    raise ValueError("use arguments OR arguments_file, not both")
                args = json.loads(Path(request["arguments_file"]).read_text(encoding="utf-8-sig"))
            else:
                args = request.get("arguments", {})
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (ValueError, OSError, TypeError) as error:
            emit(
                dict(
                    id=request.get("id") if isinstance(request, dict) else None,
                    isError=True,
                    error=str(error),
                )
            )
            continue
        start = time.perf_counter()
        res = await session.call_tool(tool, args)
        texts = []
        images = []
        for block in res.content:
            if block.type == "text":
                try:
                    texts.append(json.loads(block.text))
                except json.JSONDecodeError:
                    texts.append(block.text)
            elif block.type == "image":
                images.append(dict(mimeType=block.mimeType, base64_chars=len(block.data)))
        emit(
            dict(
                id=request.get("id"),
                tool=tool,
                isError=bool(res.isError),
                texts=texts,
                images=images,
                elapsed_s=round(time.perf_counter() - start, 4),
            )
        )
    emit(dict(event="closed"))


async def main(argv):
    if not argv or argv[0] not in ("list", "call", "interactive"):
        raise SystemExit("Use list, call <tool> <json> ..., or interactive")
    if argv[0] == "call" and (len(argv) < 3 or (len(argv) - 1) % 2):
        raise SystemExit("call needs tool / JSON argument pairs")
    env = {
        k: v
        for k, v in os.environ.items()
        if k.startswith(("DECO_", "FFXIVFURN_"))
        or k
        in (
            "PATH",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "TMPDIR",
            "USERPROFILE",
            "HOME",
            "LOCALAPPDATA",
            "APPDATA",
        )
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "ffxiv_furniture.deco.server"], cwd=str(ROOT), env=env
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            if argv[0] == "interactive":
                await interactive(s, sys.stdin, sys.stdout)
                return
            print("SERVER", init.serverInfo.name, "protocol", init.protocolVersion, flush=True)
            if argv[0] == "list":
                for t in (await s.list_tools()).tools:
                    print("-", t.name, "|", (t.description or "").split("\n")[0][:90])
                return
            calls = list(zip(argv[1::2], argv[2::2]))
            had_error = False
            for tool, a in calls:
                if a.startswith("@"):
                    a = Path(a[1:]).read_text(encoding="utf-8")
                res = await s.call_tool(tool, json.loads(a))
                had_error = had_error or bool(res.isError)
                print(f"## {tool} isError={res.isError}")
                for c in res.content:
                    if c.type == "text":
                        print(c.text)
                    elif c.type == "image":
                        print(f"[image block {c.mimeType} {len(c.data)} b64 chars]")

            return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
