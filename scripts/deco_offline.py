"""Offline driver: starts the ffxiv-deco MCP server as a stdio subprocess ONCE (not the Hermes-registered one), runs the phases of a plan file in order,
runs analyze_layout after each phase, optionally renders views, and writes <session>/offline-<tag>.log + -calls.json.

Plan file (python) defines:  PHASES = [(label, ops_list), ...]   optional: FIXTURES = {'wall':id,...,'level':'ground'} list, VIEWS = [(name, camera_dict_or_name, lighting)], EXPORT = 'name'
Usage: python scripts/deco_offline.py <session> <plan.py> [--style Minimalist]
"""

import asyncio, json, os, runpy, sys, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def payload(res):
    for c in res.content:
        if c.type == "text":
            try:
                return json.loads(c.text)
            except Exception:
                return c.text
    return None


def digest(a):
    r = a["reachability"]
    return dict(
        walkable_m2=r["walkable_m2"],
        unreachable=[(u["area_m2"], u["centre"]) for u in r["unreachable_regions"]],
        no_access=[x["name"] for x in r["instances_without_access"]][:10],
        front_blocked=[(x["name"], x["front_blocked_fraction"]) for x in a["front_clearance"]][:6],
        worst_facing=[(o["name"], o["facing_error_deg"]) for o in a["seat_orientation"][:4]],
        covered=a["balance"]["covered_fraction"],
        thirds=[t["covered_fraction"] for t in a["balance"]["by_third"]],
    )


async def main(session, plan, style):
    mod = runpy.run_path(str(plan))
    out = ROOT / "outputs/deco-sessions" / session
    out.mkdir(parents=True, exist_ok=True)
    tag = Path(plan).stem
    env = {
        k: v
        for k, v in os.environ.items()
        if k.startswith(("DECO_", "FFXIVFURN_"))
        or k
        in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA")
    }
    env["DECO_SESSION"] = session
    if style:
        env["DECO_STYLE"] = style
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "ffxiv_furniture.deco.server"], cwd=str(ROOT), env=env
    )
    calls = []
    log = open(out / f"offline-{tag}.log", "w", encoding="utf-8")

    def say(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        log.write(s + "\n")
        log.flush()

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def call(tool, args):
                t = time.time()
                res = await s.call_tool(tool, args)
                p = payload(res)
                calls.append(
                    dict(
                        tool=tool,
                        args=(
                            args
                            if tool != "batch"
                            else dict(label=args.get("label"), ops=len(args["operations"]))
                        ),
                        ok=not res.isError,
                        sec=round(time.time() - t, 2),
                    )
                )
                return res, p

            failed = False
            for fx in mod.get("FIXTURES", []):
                res, p = await call("set_fixtures", fx)
                say("fixtures", fx, "ok" if not res.isError else p)
            for label, ops in mod["PHASES"]:
                res, p = await call("batch", dict(operations=ops, label=label))
                if res.isError:
                    say("PHASE FAILED", label, str(p)[:1200])
                    failed = True
                    break
                adv = [
                    w_["code"] for w_ in p.get("warnings", []) if w_.get("severity") == "advisory"
                ]
                blocked = [
                    (w_.get("instance_id"), w_["message"][:60])
                    for w_ in p.get("warnings", [])
                    if w_["code"] == "STAIR_ACCESS_BLOCKED"
                ]
                say(
                    f'== {label}: {len(ops)} ops -> count {p["count"]} rev {p["revision"]}; advisory warnings {len(adv)} {sorted(set(adv))}; stair-access blocked: {blocked}'
                )
                for lvl in mod.get("LEVELS", ["ground"]):
                    res, a = await call("analyze_layout", dict(level=lvl))
                    say(f"   analyze[{lvl}]", json.dumps(digest(a), ensure_ascii=False))
            if failed:
                say("aborted: no renders/export after a failed phase")
                json.dump(calls, open(out / f"offline-{tag}-calls.json", "w"), indent=1)
                log.close()
                return
            for name, view, lighting in mod.get("VIEWS", []):
                res, p = await call(
                    "render", dict(view=view, lighting=lighting, width=1000, height=700)
                )
                meta = next(
                    (
                        json.loads(c.text)
                        for c in res.content
                        if c.type == "text" and c.text.startswith("{")
                    ),
                    {},
                )
                say("render", name, meta.get("image"))
            if mod.get("EXPORT"):
                await call("snapshot", dict(label="final"))
                res, p = await call("export_json", dict(name=mod["EXPORT"]))
                say("export", p["layout"]["path"], p["item_count"])
    json.dump(calls, open(out / f"offline-{tag}-calls.json", "w"), indent=1)
    log.close()


if __name__ == "__main__":
    a = sys.argv[1:]
    style = a[a.index("--style") + 1] if "--style" in a else None
    asyncio.run(main(a[0], a[1], style))
