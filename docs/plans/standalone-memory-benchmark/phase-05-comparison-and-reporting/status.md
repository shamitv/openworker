# Phase 5 status

Status: In progress — attempt 03 collection and offline replay complete; final reviewed report publication remains pending.

Planning date: 2026-10-03 (Asia/Kolkata). Dependencies: Phases 1–4 and explicit full-sweep request. The user asked to delete the prior short-limit run, start over, and then explicitly selected the available model when the previously selected ID was absent.

Attempt 03 is the full matrix: 15 held-out personas, both policies, three prompt variants, both interfaces, all three tracks, once each. This is 180 persona-condition repetitions, 540 track runs, 6,660 checkpoints and 7,740 scheduled user turns. The complete schedule hash `368722b0f71611dd51c61918ea08ad6335ebd91da18fb42e42d9052e0e58c310` was computed and recorded before inference. Effective requested settings are `max_tokens=12288`, `temperature=0`, `reasoning_effort=low`, `stream=false`.

Attempt 03 uses the exact model `Ornith-1.5-35B-A3B-Q4_K_M`, which was advertised by the fresh catalog check. It runs from the rebuilt standalone package in an unrelated working directory; initial manifest confirms the selected model, settings, 540 scheduled track runs and 6,660 checkpoints. Raw output label: `memory-bench-heldout-20261003-attempt-03` in the OS temporary directory, outside Git. See [live launch](live-launch.json).

The package wheel SHA-256 is `e929272f2d1f41154f09afb02aca53bf385ceadb5178c3d5274f18b183b749bf`. Offline portability validation and 359 tests passed; Python 3.14.2, httpx 0.28.1 and pytest 9.1.1; OpenWorker absent and no network used for installation. Frozen asset bundle SHA-256 is `37673a35e7bcf37058d705133e75ab676ef73345fbc49c6a9e13284161ae24bf`; scorer SHA-256 is `f5cfb1e2a52df159790ee589f2a977a255f66f19607856a8787f24b7994a323e`.

Attempt 01 used `max_tokens=2048` and failed with an API error after 128 complete and 159 failed checkpoints; the user requested its private output be deleted, and it was deleted. Attempt 02 used the prior model selection, but the ID was no longer advertised; it failed catalog preflight with zero inference requests and all 6,660 checkpoints unexecuted. Its private preflight evidence remains outside Git.

## Progress at 2026-10-04 15:51 IST

[Snapshot 07](progress-snapshot-07.json) records 3,392 of 6,660 checkpoints finalized and 276 of 540 track runs started, 18.99 hours in. All six `conservative` conditions are complete and `recurring` has just begun. Native finished 1,664 of 1,665 finalized checkpoints; JSON completed 70 of 1,727. Thirteen requests hit the 180-second whole-turn deadline and there are no collection errors. Extrapolating the six completed conditions, the run should finish around 2026-10-05 10:00–11:00 IST.

## Interim findings

The [interim report](interim-report-01.md) consolidates authorization, coverage and JSON findings. None of 150 sampled failures parsed as JSON; 13 contained braces in prose. Exploratory answer scoring found 50 of 56 rejected answers and 23 of 34 control answers fully correct. The samples are unmatched and do not establish superiority. Format failures limit conclusions about memory behavior, and the capture does not establish whether the server applied a grammar. See [sampled response shapes](json-interface-response-shapes-01.md).

One evidence-model finding matters for the final deliverable: a failing response is absent from the turn transcript because the adapter raises before the assistant message is appended, so representative failures can only be quoted from the durable request journal, not from `checkpoints.jsonl`.

Two JSON pass rates are both correct and must always carry their denominator: 20.5% of received JSON responses passed the adapter contract at 11:15 IST, while 4.1% of finalized JSON checkpoints completed at 15:51 IST.

The [attempt 03 offline acceptance](offline-acceptance.json) block records collection `8a142dbd402db5c759bfc6f49b6f2236f7d387d252aa046584a986feed949e1c`, whose only source difference from attempt 02 is the 12288 token limit, with scorer and assets unchanged. The recording context could not locate portability evidence. Review on 2026-10-05 found the exact wheel, recomputed its matching hash, and verified the existing isolated report records validation and 359 passing tests. The earlier context's access limitation is retained as history; portability acceptance is resolved.

At the [final collection snapshot](progress-snapshot-08.json), all 540 tracks and 6,660 checkpoints are accounted for: 269 complete and 271 failed tracks; 3,458 complete checkpoints, 3,181 format errors and 21 deadlines; zero unexecuted. There were 9,707 inference requests and 9,686 returned responses. Collection errors are empty and cleanup is complete. Offline replay completed with zero inference requests and the unchanged frozen scorer. Final report review/publication and delivery remain pending. Keep these results separate from historical benchmarks; one selected model supports instruction/policy comparisons.

An inference-free [interim quality analysis](interim-quality-analysis-01.md) uses a private snapshot at 2026-10-04 11:15 IST and the frozen installed scorer. It contains 186 finished track runs and 2,294 unique finalized checkpoints, with complete conservative baseline/rules persona coverage. Its key-matching diagnostic is explicitly exploratory and leaves frozen scores unchanged. This partial analysis does not satisfy final coverage or Phase 5 acceptance.
