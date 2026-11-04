# Development status and remaining work

[Back to code guide](../WORKSPACE.md)

## Completed

- Public README, data prerequisites, MCP, catalog, and rendering documentation have separate roles. Example remains reserved for the maintainer.
- Databases/native assets are ignored at any location and excluded from Git archives, with read-only distribution checks. Local data is not deleted and releases are not published automatically.
- Rendering requirements include moderngl, a Pillow range covering the tested version 13, and MCP limited to 1.x. All three requirements files were installed in a fresh Windows Python 3.12 venv, followed by pip check, a real OpenGL context, and real interior/yard MCP calls.
- MCP/offline/audit Python launchers use the current interpreter. Bash wrappers accept a PYTHON override or select the local venv; grep no longer hides failure exit statuses. Client ready messages report the actual Python. One-shot calls exit 1 on any tool failure. Multiple calls are not atomic; use batch for atomic edits.
- Private IPs and guessed model defaults were removed from runtime settings. config.model_settings explicitly requires VLM_URL/VLM_MODEL. Historical source/reviewer identities remain intact rather than inventing provenance.
- Private historical seeds are no longer loaded implicitly. Shared complete-layout/scale validation rejects missing data. A mismatched house size cannot resume a same-name session or rewrite its saved state. doctor is a standard-library, read-only diagnostic without downloads, inference, or manufactured data.
- Main MCP/exterior entry points were formatted with Black safe mode to expand dense statements while preserving filenames/references. scripts/README documents entry points and side effects; historical scripts were not moved blindly.
- Stale tests were corrected: the persisted geometry token remains DarkMinimalist, while app export uses DarkMinimalist's display name, Dark Minimalist. The production output contract was not changed. The full suite passed with explicit skips; details remain in local verification records.
- No restricted database/native-asset paths were found in the locally reachable history/tags inspected during cleanup. No remote was configured at inspection time, so remote attachment contents were not audited. This is not a legal or content-safety determination.
- Explicit source settings, atomic new-database construction, and a source-only-copy test are available. MCP/rendering read native structures directly, without a private native-bounds inventory. Bootstrap makes no model calls and records unknown patches/identities and unsupported geometry explicitly.

## Incomplete or not established

1. **Private visual data reproduction:** runtime catalog bootstrap is available (see [bootstrap](bootstrap.md)) without private history. Private visual tags, manual corrections, and vectors are not reconstructed automatically; users must create them separately. doctor remains diagnostic only. Databases/raw assets must not be provided as downloads.
2. **Non-Windows verification:** removing platform-fixed paths from major Python launchers does not verify Linux/macOS GPU execution, native paths, or the complete dependency stack. Bash wrappers still use GNU timeout, which may require separate installation outside Windows/Linux setups.
3. **Further refactoring:** remaining historical/one-off scripts have not all been split or moved. Build a reference graph and regression coverage before doing so to avoid unrelated breakage.
4. **Remote release/history content audit:** requires a remote/repository URL. Current checks cover restricted names in locally reachable history only, without automatic history rewriting or access to remote releases absent locally.
5. **Example:** code and original documentation use MIT as specified by the maintainer (see LICENSE); databases/third-party assets are excluded. The maintainer still needs to add the README example and confirm image/layout distribution rights.
6. **Future wheel/Docker/CI releases:** this work added local bootstrap only, as requested, not packaging/release workflows. Future workflows require their own allowlists and inspection of actual package contents; gitignore alone is insufficient.

Local evidence is stored in outputs/public-source-cleanup/ and excluded from source distributions. The cleanup did not publish releases, distribute game data, or perform real model classification/inference.
