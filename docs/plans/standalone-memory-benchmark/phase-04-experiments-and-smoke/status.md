# Phase 4 status

Status: In progress — offline controls accepted; live attempt 02 collecting

Date: 2026-10-03 (Asia/Kolkata). Dependencies: Phases 1–3.

Stable condition/track/checkpoint IDs, sequential schedules, isolated namespaces,
six instruction variants, frozen hashes and separate-track reports are implemented.
Rules/examples retain each full baseline policy. Examples use development P02 only.
The complete source and installed-wheel suites each pass 343 tests; the current
wheel's source fallback is disabled and OpenWorker is absent. Phase 3 acceptance
records the environment, commands and full source/asset/scorer hashes.

## Explicit live attempts

Attempt 01 used the fixed P01 schedule and one advertised exact model. Its first
inference request returned HTTP 500 because the server template rejects two system
messages. The client stopped without retry or fallback: one failed checkpoint,
147 unexecuted, missing usage null, no operations, and successful owned-store cleanup.
The reviewed [findings](../../../memory/standalone-evaluations/phase04-smoke/attempt-01/findings.md),
[JSON](../../../memory/standalone-evaluations/phase04-smoke/attempt-01/results.json) and
[report](../../../memory/standalone-evaluations/phase04-smoke/attempt-01/report.md) are preserved.

Commit 70962bb corrected assembly to one initial system message with unchanged
common policy/state and a separately headed interface envelope. Both complete
343-test suites passed again before attempt 02 began. The new collection uses fresh
state, a new explicit output label and a freshly checked /models catalog. No gold
expectations, policy requirements, model IDs or requested settings were changed.

Attempt 02 uses http://10.42.0.202:8090/v1 and Ornith-1.5-35B-Uncensored-Q6_K,
from the independently installed wheel under build/portability-zwr6mw49. Its fixed
schedule is P01 development, both baseline policies, JSON/native, write/read/sequence,
one repetition: twelve track runs, 148 checkpoints and 172 scheduled user turns.
Real model responses and measured format failures are being captured. Completion,
final coverage, model outcomes, replay, reviewed exports and cleanup remain pending.

Raw output for each attempt remains outside Git under the operating system temporary
directory, named memory-bench-smoke-20261003-attempt-01 and
memory-bench-smoke-20261003-attempt-02. Disposable stores belong only to that attempt.
No full held-out sweep or Phase 5 inference is authorized or executed.
