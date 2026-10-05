# Parallel-agent change review

Reviewed 2026-10-05 after the user requested selective retention/reversion with Git history preserved. Scope: commits `6f32cc7`, `1e91646`, `52f071c`, and the two existing progress changes. Commit `53ef1c2` implements the user's authorized 12288-token limit and is retained.

## Decisions

| Change | Inferred intent | Decision |
|---|---|---|
| Offline acceptance and launch records (`6f32cc7`) | Establish provenance for attempt 03 | Keep the recorded checks and historical access limitations. Correct the conclusion that exact-wheel portability remains open using the existing wheel and acceptance report. |
| Response-shape analyzer and tests (`1e91646`) | Diagnose JSON failures without inference or changing frozen scores | Keep. Correct generated claims, derive coverage from the manifest, require held-out input, and validate resolved output paths and labels. |
| Interim measurements and reports (`52f071c`) | Explain progress and rejected answer text | Keep measurements and exploratory caveats. Remove unsupported grammar-enforcement, causal and superiority conclusions; clarify the UNKNOWN-field metric and timeout-containing control sample. |
| Overwritten snapshot 07 | Record later progress | Restore the committed 15:51 snapshot used by historical references; preserve the 22:32 contents as snapshot 07b. |
| Snapshot 08 | Record completed collection | Keep. |
| Deleted attempt-01 snapshot | Fulfil the user's earlier deletion request | Keep deletion; its original history remains in Git. |

The failing sample had zero parseable JSON responses and thirteen responses containing braces in prose. The heuristic cannot establish that those thirteen contained usable envelopes or rule out all near misses. Exploratory counts of 50/56 correct rejected answers and 23/34 correct control answers remain descriptive because the samples are unmatched. The control population includes deadlines. The frozen `unknown` measure checks only fields requiring UNKNOWN; it does not mean every field in the response was UNKNOWN.

## Verified evidence

The wheel at `benchmarks/memory/build/portability-nzzdizy3/wheels/standalone_memory_bench-0.1.0-py3-none-any.whl` hashes to `e929272f2d1f41154f09afb02aca53bf385ceadb5178c3d5274f18b183b749bf`. Its existing isolated report records successful validation, 359 passing tests, no OpenWorker, no installation network and no inference. The installed client requests 12288 tokens. This review read the existing evidence; it did not repeat portability execution.

[Snapshot 08](progress-snapshot-08.json) records complete collection: 540 tracks, 6,660 checkpoints, 3,458 complete, 3,181 format errors, 21 deadlines and zero unexecuted. All 9,707 inference requests finished; 9,686 returned responses. Cleanup is complete. The private offline replay completed with zero inference and scorer hash `f5cfb1e2a52df159790ee589f2a977a255f66f19607856a8787f24b7994a323e`. Raw capture and replay remain in OS temporary directories labelled `memory-bench-heldout-20261003-attempt-03` and `memory-bench-heldout-20261003-attempt-03-replay-01`.

## Validation and history

Targeted analyzer suite: 31 passed, one file-symlink test skipped because Windows symlink privileges are unavailable. Traversal-label and capture-directory protection tests passed. The initial test invocation could not access pytest's default temporary directory; the successful invocation used a fresh workspace build directory. `git diff --check` passed.

Historical response-shape JSON and its numerical counts remain unchanged. Snapshot 07 was restored from commit `52f071c`; snapshot 07b preserves its pre-review replacement. Frozen runner, prompts, corpus, protocol, scorer and token settings were not edited by this review.

Git history uses a progress checkpoint commit (`8a3b574`), analyzer correction commit (`4057c8e`) and a separate documentation correction commit. Original commits remain intact. Changes are committed locally. Final Phase 5 report publication is a separate outstanding deliverable.
