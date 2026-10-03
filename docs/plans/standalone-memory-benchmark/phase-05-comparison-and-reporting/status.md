# Phase 5 status

Status: In progress — authorized full matrix; report implementation acceptance pending

Planning date: 2026-10-03 (Asia/Kolkata). Dependencies: Phases 1–4 and a later explicit full-sweep request.

The user explicitly requested **“Implement phase 5”** after the completed Phase 4
delivery and an explanation of the full held-out matrix. This authorizes the Phase 5
sweep. [execution-request.json](execution-request.json) records the selections and
initial schedule hash before inference: one exact model, fifteen held-out personas,
both policies, three variants, both interfaces, all three tracks and one repetition.
This is 180 persona-condition repetitions, 540 track runs, 6,660 checkpoints and
7,740 scheduled user turns. No Phase 5 inference has started at this checkpoint.

Phase 4 acceptance is complete and normally pushed at 0a85530. Its source and
installed-wheel suites pass 345 tests. A fresh direct catalog check verified the
selected `Ornith-1.5-35B-Uncensored-Q6_K` at `http://10.42.0.202:8090/v1` without
inference. Collection will verify its own catalog again. Corpus, instruction,
policy, lifecycle and scorer hashes remain frozen; report-only changes add
controlled comparisons, detailed denominators, turn coverage and server metadata.
New source/installed-wheel acceptance remains pending before collection.

Only the already selected model is used. The run can compare policies/instructions
with interfaces kept separate; it cannot establish a comparison between models.
Existing historical benchmarks remain separate. At the smoke's observed throughput,
the complete sequential collection may take roughly sixty hours; actual throughput
and failures will be recorded rather than changing the matrix or requested settings.

Raw collection will live outside Git in the OS temporary directory with label
`memory-bench-heldout-20261003-attempt-01`. Final reports, replay, reviewed synthetic
exports, cleanup and normal push are required before marking Phase 5 complete.
