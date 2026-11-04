# Image classification and vocabulary consolidation

This package never imports `FurnitureDB`, changes the formal database, publishes tags, or creates Item IDs. `item_id: null` remains null. Assets are **unconfirmed candidates**, not a confirmed placeable inventory. Existing description-only E5 behavior is unchanged.

[Back to README](../../README.md) · [Data and distribution policy](../../docs/distribution.md)

All images, manifests, run databases and model outputs are local-only and are not supplied with the repository. Replace YOUR_MODEL_ID with your actual served model; these commands perform inference and send image bytes to the configured endpoint. Do not run them as an installation check.

## Run (project root, Windows Git Bash)

Pillow is required for manifest image verification; no SDK/HTTP dependency is added:

```bash
./.venv/Scripts/python.exe -m pip install -r requirements-classification.txt
./.venv/Scripts/python.exe -m ffxiv_furniture.classification prepare --manifest data/classification-manifest.jsonl --run-dir runs/round1
./.venv/Scripts/python.exe -m ffxiv_furniture.classification sample --run-dir runs/round1 --budget 96 --seed 42 --min-per-stratum 2
# Explicit endpoint/model; discovery GET /models rejects unavailable requested models.
./.venv/Scripts/python.exe -m ffxiv_furniture.classification classify --run-dir runs/round1 --endpoint http://127.0.0.1:8000/v1 --model YOUR_MODEL_ID --phase explore --batch-size 4 --max-batches 1 --timeout 180
# Same command without max-batches resumes successes, then handles remaining selected images.
./.venv/Scripts/python.exe -m ffxiv_furniture.classification classify --run-dir runs/round1 --endpoint http://127.0.0.1:8000/v1 --model YOUR_MODEL_ID --phase explore --batch-size 4 --timeout 180
./.venv/Scripts/python.exe -m ffxiv_furniture.classification consolidate --run-dir runs/round1 --endpoint http://127.0.0.1:8000/v1 --model YOUR_MODEL_ID --max-proposals 96 --timeout 180
./.venv/Scripts/python.exe -m ffxiv_furniture.classification report --run-dir runs/round1
```

The model name above is an example deployment identifier, **not hardcoded in the client**. No cloud fallback. `--deployment-revision` optionally pins the operator's immutable server-weight revision in job identity; absent it the report explicitly warns that server aliases cannot guarantee reproducibility. The original `classify` command handles a selected round. Later-round, remaining-library and all-library final scheduling are available through `next-round`, `discover-rest`, `final-all`, `status`, and explicit `anchor-qa`; see [SCHEDULER.md](SCHEDULER.md). Actual inference requires `--execute` and defaults to a bounded new batch. Do not interpret pilot completion as convergence or full-library classification.

## Manifest and sampling

JSONL fields: `asset_key`, nullable `item_id`, optional `name`, `source_category`, `scope`, absolute `image_path`, optional `patch` and other metadata. Preparation rejects missing/corrupt images, relative paths, duplicate asset keys or non-null duplicate Item IDs. Pillow verifies and decodes every image, storing byte SHA-256, dimensions and MIME. All metadata is retained locally. Run manifest and round are immutable; source changes require a new run directory.

Unique byte image hashes are sampled without replacement. Duplicate-image asset mappings are preserved, not merged into one furniture item. Their representative stratum is the lexicographically first `(scope, source_category, asset_key)`, recorded as a policy; coverage reports include all mappings. Selection seeds shuffle stable sorted inputs, take up to two per `(scope, source_category)` stratum (small groups all), then allocate remaining slots in proportion to square roots of remaining population using deterministic weighted-fair rounding. An insufficient minimum budget is visibly reported, not described as full coverage. Patch is retained without filtering or creating a huge crossed stratum grid.

`round-001.json` persists opaque IDs, exact choices, seed, hashes, allocation, stratum, selection reason, eight unguided-control IDs, and up to 24 cross-stratum anchor IDs. All first-round explore calls are already unguided: controls identify a subset rather than spending another eight image calls. Anchors are a development consistency set, not gold truth or held-out accuracy.

## Visual contract, resume and errors

Only opaque ID + source category and actual `image_url` data URLs go to the vision model. Names, asset keys, scope and local paths never enter the VLM request. Each image remains native resolution; original bytes are verified again before sending. Source-category strings must be trusted category metadata, not item names. First-round free tags use exactly `style/material/color/form/ornament/theme`, aim for 3–6 total but allow zero when uncertain. Tags have short visible evidence and numeric finite 0–1 uncalibrated confidence; descriptions are brief and visual. No dimensions, hidden construction, dye channels or authoritative material guesses.

Batch IDs must match the **actual variable batch's exact set** (default four), once each. JSON fences are accepted; `reasoning_content` (or `reasoning`) never substitutes for missing answer content. Schema/category/confidence/evidence are validated. One JSON repair is allowed. HTTP 429/transient 5xx/network failures get at most three transport attempts with bounded backoff; other 4xx stop. Image and text output caps are 4096 and 2048 tokens. **Qwen text consolidation explicitly sends `chat_template_kwargs: {"enable_thinking": false}`**, because this server can otherwise consume the entire 2048-token budget in reasoning with no JSON answer. That setting is part of persisted requests/cache identity; unsupported servers fail visibly rather than silently changing modes. Vision requests retain the server default thinking mode. Every request has a timeout. There are no fake fallback predictions.

Each job identity includes endpoint, requested model, deployment revision, phase, exact image-bearing prompt/input bytes, prompt version, vocabulary snapshot hash, round hash and inference settings. Request/response JSON files preserve exact audit inputs, raw outputs, usage, elapsed time, attempts and validation errors. SQLite `jobs`, `responses`, `predictions`, `vocab_versions`, `tag_decisions` remain entirely under the run directory. Validated predictions and job success are committed atomically. Cache successes resume without inference. Failed jobs can be retried explicitly by rerunning; stale running leases expire after at least 900 seconds (or eight request timeouts). Concurrent runners cannot claim a live lease. Changing batch size changes jobs, so keep batch size fixed for efficient resume.

`--max-batches` limits **new** batches, not cached ones. A file `RUN_DIR/STOP` stops before the next visual batch/text chunk; it does not interrupt an active request. CLI failures return nonzero and best-effort reports; no failed batch is counted as successful.

## Consolidation and vocabulary primitives

1. Deterministically NFKC-normalize, trim/collapse whitespace and case-fold exact names within each category. These low-risk duplicates are consolidated automatically; semantic similarity never automatically merges concepts.
2. Save full raw `tag-observations.json` with evidence, image, round and provenance, plus `candidate-inventory.json`. Original spellings remain attached to permanent content-derived concept IDs. Frequencies separately count unique images, candidate assets and source strata. Rare single-image concepts stay provisional.
3. Call the actual configured Qwen **text endpoint** on at most 32 concepts from one category, with at most three evidence examples each. No images, entire history or full-library content is sent. At most 12 proposals/chunk, bounded overall `--max-proposals`. Cross-chunk synonym discovery is not exhaustive; reaching the cap is not a convergence claim.
4. Validate all references, categories, duplicate/conflicting targets, and merge cycles. Save proposed alias/merge/split/rename/reject/broader/related actions as pending advisory decisions. A non-destructive `keep` proposal is automatically adopted only to preserve provisional status. Normalization and preserve-only decisions are persisted. The model's assertion of synonymy alone is not a sufficient safe autoapply policy. Exact normalized duplicates already need no human review; semantic ambiguous/destructive proposals require explicit adoption.
5. Write content-versioned `vocab-vNNN.json` and `vocab-latest.json` snapshots, with canonical concepts, definitions, include/exclude boundaries, aliases with scope/language, examples/negative examples, statuses, revisions, proposals, decisions and relations. No raw concept or observation is removed.

To adopt decisions, copy/edit a vocabulary snapshot, set relevant proposal `status` to `accepted` or `rejected`, add/clarify definitions/boundaries/statuses, then:

```bash
python -m ffxiv_furniture.classification vocab-apply --run-dir runs/round1 --file reviewed-vocab.json
python -m ffxiv_furniture.classification vocab-freeze --run-dir runs/round1 --file runs/round1/vocab-latest.json
```

Apply preserves permanent IDs/category/original spellings and proposal history, saves revision before/after images and adoption reasons, checks cycles and prevents concept deletion. Merge retains the source concept as `merged` with `merged_into`; relations are not aliases. Split acceptance stops because it requires explicit reclassification rather than stamping both tags on every prior hit. Freeze is intentionally **blocked after a sampled pilot**: every manifest image must have successful exploration, every concept decided, accepted concepts defined, and proposals resolved. Freeze alone never triggers full-library inference or publication.

Guided/final remain low-level selected-round primitives. The scheduler adds automatic later-round 32/16/16 selection, discover-rest, reviewed convergence/anchor trend checks and fresh full-library final classification; see [SCHEDULER.md](SCHEDULER.md). No subsequent real image inference was performed during this implementation. Formal-catalog publication remains deferred.

## Reports and tests

`report.json` and `report.md` include eligible/selected/successful/unseen counts per source stratum, candidate counts per visual category, per-tag unique-image/candidate/stratum frequencies, rare tags, job IDs/failures/retries, raw usage sums, elapsed time and proposal/concept decision statuses. Failed attempts remain visible even if a subsequent explicit resume succeeds. No accuracy is claimed without gold labels. Raw usage includes repairs; transport retries that never return usage cannot be cost-accounted exactly.

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Tests use **explicit mocked inference** and cover malformed/missing inputs, sampling/reproducibility/unique hashes/small groups, immutable rounds, exact variable ID sets, images/privacy, raw replies, one-repair bound, transport retry limit, failure without synthetic output, resume and expired leases, vocabulary hash invalidation, final-key rejection, normalization/proposals/cycles and premature freeze rejection. Mock tests are not evidence of model quality; actual endpoint round results are separate run artifacts ignored by version control.
