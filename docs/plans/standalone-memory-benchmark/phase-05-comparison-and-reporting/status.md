# Phase 5 status

Status: In progress — software accepted; full held-out attempt 01 collecting

Planning date: 2026-10-03 (Asia/Kolkata). Dependencies: Phases 1–4 and a later explicit full-sweep request.

The user explicitly requested **“Implement phase 5”** after the completed Phase 4
delivery and an explanation of the full held-out matrix. This authorizes the Phase 5
sweep. [execution-request.json](execution-request.json) records the selections and
initial schedule hash before inference: one exact model, fifteen held-out personas,
both policies, three variants, both interfaces, all three tracks and one repetition.
This is 180 persona-condition repetitions, 540 track runs, 6,660 checkpoints and
7,740 scheduled user turns. The complete initial schedule was committed before
inference. Collection started at Unix time 1791029079.02329; its captured schedule
matches the committed SHA-256
`dfb39db1ed13de098888c0aac897cf25392a7cbbd680900979dd973e971c9d59`.

Phase 4 acceptance is complete and normally pushed at 0a85530. Its source and
installed-wheel suites pass 345 tests. A fresh direct catalog check verified the
selected `Ornith-1.5-35B-Uncensored-Q6_K` at `http://10.42.0.202:8090/v1` without
inference. Collection will verify its own catalog again. Corpus, instruction,
policy, lifecycle and scorer hashes remain frozen; report-only changes add
controlled comparisons, detailed denominators, turn coverage and server metadata.
The Phase 5 source and independently installed-wheel suites each pass **359 tests**
(157.00 and 155.20 seconds). The installed tests run from an unrelated directory
with source fallback disabled, OpenWorker absent and offline dependencies; validation
and tests make no network/inference requests. Forty source/test/tool files pass
Python 3.10 syntax checks; runtime acceptance uses Python 3.14.2 on Windows 11,
httpx 0.28.1 and pytest 9.1.1. Full environment, source/asset/scorer/reporting hashes
and commands are recorded in [offline-acceptance.json](offline-acceptance.json).

An earlier offline run had 354 passes and one transient Windows atomic-manifest
sharing failure. The correction retries only publication of an already-written
manifest, at most four attempts with 175 milliseconds total delay; persistent and
non-Windows failures still surface. It never repeats model requests, SQLite mutations
or appended evidence. Focused tests and both complete suites passed before inference.

The comparison/report implementation is committed at 14964e4 and normally pushed;
its accepted wheel SHA-256 is
`671768c23ec356d74695f11b731900b4375eb69e8ab121257de0eeb9712aa905`.
Collection hash: `4f417fd9a4ea45cbc0246ee8afda6baa98b23e87ddacdef795dac7acf0877253`.
Frozen scorer hash: `f5cfb1e2a52df159790ee589f2a977a255f66f19607856a8787f24b7994a323e`.
Reporting hash: `9b162ef7340457b6df43a2682ea6746e3739f532edab20357bccc05f2d813df8`.

The direct `run` command is active in managed terminal session **1333**, using that
wheel under `build/portability-ytaar7zd` from its unrelated working directory. Its
fresh catalog check advertised the exact selected model. First checkpoints retain
model format failures; no infrastructure failure had occurred when this launch
record was written. [live-launch.json](live-launch.json) records the full command
and frozen identity. The rejected detached Windows launch executed no collection
or inference; the managed CLI is the sole actual attempt.

An inference-free report preview on the retained Phase 4 capture verifies that the
new presentation preserves every previous condition score and both original
collection/scoring provenance objects. The preview remains outside Git; it is not
held-out evidence and is not pooled with this run.

Only the already selected model is used. The run can compare policies/instructions
with interfaces kept separate; it cannot establish a comparison between models.
Existing historical benchmarks remain separate. At the smoke's observed throughput,
the complete sequential collection may take roughly sixty hours; actual throughput
and failures will be recorded rather than changing the matrix or requested settings.

Raw collection will live outside Git in the OS temporary directory with label
`memory-bench-heldout-20261003-attempt-01`. Final reports, replay, reviewed synthetic
exports, cleanup and normal push are required before marking Phase 5 complete.
The active CLI automatically generates raw results/report and cleans its owned
stores when collection ends. Offline replay, manual review/export and final commits
remain pending until the full live run completes. Do not silently rerun, change
prompts/gold/settings or call this completed while it is collecting.
