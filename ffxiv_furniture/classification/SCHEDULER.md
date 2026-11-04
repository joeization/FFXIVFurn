# Subsequent Astra rounds (implemented scheduler)

This extends the original pilot; it does not authorize another model run. All commands below without `--execute` only plan/persist snapshots. `--dry-run` is strictly read-only, including SQLite; it does not discover a server or invoke a model. `status` is also read-only. No command publishes, edits the formal catalog, creates Item IDs, or changes description-only embedding behavior.

## Safe inspection now

From the project root in Windows Git Bash, after preparing your own local run directory (not included in the repo):

```bash
./.venv/Scripts/python.exe -m ffxiv_furniture.classification status --run-dir runs/round1
./.venv/Scripts/python.exe -m ffxiv_furniture.classification next-round --run-dir runs/round1 --vocab runs/round1/vocab-latest.json --seed 43 --dry-run
```

The existing immutable `round-001.json` and its predictions are retained. Later rounds use `round-002.json`, etc., with globally distinct opaque IDs. Each snapshot contains exact selections/mappings, manifest hash, seed, reasons, full fixed vocabulary, vocabulary hash, controls and original anchor references. Hash mismatches fail closed. A staging `rounds` table indexes all snapshots when scheduling; files remain the source of immutable history. Legacy staging migrations are additive and use SQLite backup API to create `state.pre-history.sqlite3` **before** changing the schema. Never remove that backup during an active migration.

## Next 64 unique images

A completed pilot is required. Per round: 32 stratified random, 16 lowest successful coverage, 16 explicit rare/conflict targets; unfilled target quota falls back to stratified random. Stable sorted populations plus saved seed make selection reproducible. Earlier selections, not just successes, are excluded, so failed/pending selections must be resumed instead of silently replaced. Near exhaustion, quotas truncate to available unseen images; no empty round is created. Explicit target SHA-256 hashes may be supplied with `--targets HASH ...`; they must exactly identify manifest images. Target guidance is operator-supplied, not guessed from furniture names.

Eight images from the **32 random selections** receive additional independent unguided jobs with no vocabulary. These are eight extra calls' worth of images (normally two batches of four), not eight additional unique images. Controls have separate cache identities and retain their role/provenance. They are development anti-anchoring comparisons, not gold truth.

```bash
# Persist a plan, NO model/network call:
./.venv/Scripts/python.exe -m ffxiv_furniture.classification next-round --run-dir runs/round1 --vocab runs/round1/vocab-latest.json --seed 43

# ONLY after separate authorization for inference: bounded main + control execution.
# Supply the actual local deployment; placeholders below are not runnable defaults.
./.venv/Scripts/python.exe -m ffxiv_furniture.classification next-round --run-dir runs/round1 --execute --endpoint http://LOCAL_HOST:PORT/v1 --model LOCAL_MODEL --deployment-revision WEIGHT_REVISION --batch-size 4 --max-batches 1
```

Reissue the execution command to resume the exact incomplete snapshot. `--max-batches` is a required positive bound at API level and defaults to **1** on the scheduler CLI; it limits **new** main and control batches together. Endpoint/model/deployment revision/batch size are pinned in an execution record: changing them during resume fails rather than duplicating a pass. Source vocabulary edits cannot affect an existing plan. Supplying a different vocabulary on resume is rejected. `RUN_DIR/STOP` stops before the next batch; cached successes and raw attempts remain. Removing STOP requires operator intent. The original `classify` command remains a pilot-level primitive; use the scheduler to operate subsequent rounds.

Once all main/control jobs succeed, the next `next-round` request creates another round using the explicitly supplied next vocabulary snapshot; consolidation does not occur automatically. Consolidate and review between rounds using the existing vocabulary commands. All-round vocabulary inventory reads guided canonical keys through their own saved snapshot, new proposed tags, and unguided controls separately.

## Discover the remainder, then fresh full-library final

```bash
# Planning preview only; no server calls:
./.venv/Scripts/python.exe -m ffxiv_furniture.classification discover-rest --run-dir runs/round1 --vocab runs/round1/vocab-latest.json --dry-run

# Persist when authorized to schedule, then execute separately with same local arguments:
./.venv/Scripts/python.exe -m ffxiv_furniture.classification discover-rest --run-dir runs/round1 --vocab runs/round1/vocab-latest.json
# Add --execute --endpoint ... --model ... --max-batches N to execute/resume.
```

Discover-rest snapshots **all globally not-yet-successful images** under one fixed guided vocabulary. This includes failed selections from earlier rounds; failures are never called successful. Later invocation resumes the same pass. New concepts remain proposals; no batch mutates the dictionary. Once discover-rest has been scheduled, use it rather than creating additional sampling rounds. A completed pass remains idempotently resumable; it does not create an empty new pass.

After every eligible image has successful main exploration, perform final consolidation/decisions and `vocab-freeze`. Freeze uses `scheduler.exploration_coverage`, not just original 96 images. Zero-tag but valid classifications count as successful; failed jobs, controls, anchors and final jobs cannot inflate global main exploration coverage. Vocabulary legality, definitions and proposal decisions are additional freeze gates.

```bash
./.venv/Scripts/python.exe -m ffxiv_furniture.classification final-all --run-dir runs/round1 --vocab runs/round1/vocab-latest.json --dry-run
# Persist and then explicitly execute/resume with bounded local arguments, as above.
```

Final-all requires a frozen vocabulary and complete exploration. It snapshots **all unique manifest images, including original pilot images**, and uses fresh `final` inference with the same fixed vocabulary. Only image bytes, opaque IDs, source category and dictionary definitions enter the visual request; prior per-image predictions/descriptions are never fed back. Final phase/cache identity is independent of exploratory jobs. Final completion is reported separately per plan; global exploration completion is not final completion. A different vocabulary is not silently substituted into an existing final plan: it requires a separately designed new-version/reclassification lifecycle.

## Explicit anchors and convergence QA

The original up-to-24 cross-stratum anchor IDs never change. No scheduler automatically reruns them.

```bash
./.venv/Scripts/python.exe -m ffxiv_furniture.classification anchor-qa --run-dir runs/round1 --vocab runs/round1/vocab-latest.json --dry-run
# Actual QA requires --execute and bounded local endpoint/model arguments.
```

Anchor QA retains immutable dictionary snapshots and resumes through cache. Status reports successful anchors and changed tag sets versus the previous evaluated dictionary on overlapping anchors. These are **development consistency trends**, not accuracy; revisions of canonical keys can change sets without any quality change. Human review must check systematic regressions and omissions. Rerunning is explicit; there is no unbounded QA loop.

Convergence status never treats raw proposed-string counts as genuinely new concepts. An optional `RUN_DIR/convergence-qa.json` is keyed by immutable round hashes:

```json
{
  "ROUND_HASH": {
    "reviewer": "operator identity",
    "genuinely_new_image_hashes": ["REVIEWED_RANDOM_IMAGE_SHA256"],
    "controls_no_repeated_misses": true,
    "anchors_no_systematic_regression": true,
    "no_high_impact_pending": true
  }
}
```

The reviewed image hashes must belong to that round's **random 32**, not low-coverage, targeted, fallback or control groups. Numerator is distinct random images with adjudicated genuinely-new concepts; denominator is successfully classified random images. The three most recent rounds must be complete (including controls), with reviewed rates strictly below 5%, and all manual gates explicitly true, before `discover_rest_recommended` can become true. Missing QA yields a null numerator/rate, never zero. `converged` deliberately stays false: even this signal proves neither completeness nor statistical coverage and cannot skip discover-rest/freeze gates. Additional source-group details and raw proposals remain available in round images and vocabulary observation provenance.

## Verification / limits

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_scheduler.py' -v
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Scheduler tests use explicit synthetic images and mock inference, including all-round discovery → consolidation → freeze → fresh 220-image final, batch caps/STOP/resume, independent controls, immutable snapshots, seed/quotas, tail exhaustion, legacy guided snapshots, zero-tag successes, failed-job exclusion, migration backups, read-only CLI subprocesses, QA gates and integrity checks. This establishes local execution mechanics, not model quality or throughput.

Deferred: publishing, automatic target diagnosis, unattended human-concept adjudication, gold-label accuracy, failed-image administrative exclusions, and replacing a completed final with a newly revised frozen vocabulary. No full-library real inference was performed for this implementation.
