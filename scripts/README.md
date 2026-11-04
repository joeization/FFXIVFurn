# Script entry points

[Back to README](../README.md) · [Code guide](../WORKSPACE.md)

Prefer package entry points. Do not infer that a historical script is an installer from its filename:

| Task | Recommended entry point | Side effects |
|---|---|---|
| Build a runtime catalog | `python -m ffxiv_furniture.bootstrap --sources ... --output <new-file>` | Writes a new database only; reads your assets/CSVs without inference or private runs |
| Basic catalog | `python -m ffxiv_furniture --db <test-database> ...` | CRUD writes to the specified database |
| Environment checks | `python -m ffxiv_furniture.doctor` | Read-only; tests OpenGL only with `--gpu` |
| Interactive decorating | `deco_mcp_client.py interactive` | MCP edits sessions, renders, exports |
| Staged decorating | `deco_offline.py` | Commits plans; do not replay committed creation operations |
| Native rendering | `python -m ffxiv_furniture.rendering` | PNG output; diagnostics require opt-in |
| Distribution checks | `check_distribution.py` | Reads Git index; `--directory` checks a prepared distribution directory |
| Local model image inspection | `describe_render.py <PNG> <question>` | Sends images to an explicitly configured model; may incur charges |
| Maintenance/experiments | `build_*`, `fill_*`, `review_*`, etc. | Read the code first; may depend on private history, write databases, or call models |

Python MCP/offline/audit launchers use the current `sys.executable`, not a hardcoded external venv. Bash wrappers accept an executable through `PYTHON`, otherwise selecting `.venv/bin/python`/`.venv/Scripts/python.exe`. They still use GNU timeout; prefer Python entry points for portability. Filenames remain unchanged to preserve existing calls and historical references.

One-shot `call` exits 1 if any tool reports an error and 0 on success. Multiple calls are not atomic; use batch for atomic edits. Interactive mode reports `isError` per request while retaining the connection, leaving subsequent decisions to the caller.

## Model settings are explicit

Legacy helper scripts use `VLM_URL`/`VLM_MODEL` rather than connecting to the maintainer's private IP or guessing a model alias. Git Bash example:

```bash
export VLM_URL=http://127.0.0.1:8000/v1
export VLM_MODEL=YOUR_SERVED_MODEL_ID
# The following is a real model request, not an installation test.
# python scripts/describe_render.py <image.png> "Describe visible issues"
```

`describe_render.py` and `finalize_and_classify.py` also accept explicit `--endpoint`/`--model`. The plan-only mode of `iterate_render.py` does not require model settings; actual `--execute` does. The classification CLI already uses explicit endpoints/models. Historical reviewer/source fields preserve original model identities rather than fabricating provenance.

Users must check model/image rights and network risks. The local configuration example does not start a service, download weights, or begin inference automatically.
