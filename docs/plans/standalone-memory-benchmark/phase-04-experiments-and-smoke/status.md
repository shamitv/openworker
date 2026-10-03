# Phase 4 status

Status: Complete — offline controls and bounded live smoke accepted

Date: 2026-10-03 (Asia/Kolkata). Dependencies: Phases 1–3.

Stable condition/track/checkpoint IDs, sequential schedules, isolated namespaces,
six instruction variants, frozen hashes and separate-track reports are implemented.
Rules/examples retain each full baseline policy. Examples use development P02 only.
The final source and independently installed-wheel suites each pass **345 tests**.
The wheel tests run from an unrelated working directory with source fallback
disabled and OpenWorker absent; dependency installation and tests make no network
or inference calls. Python 3.14.2, Windows 11, httpx 0.28.1 and pytest 9.1.1 were
used. Python 3.10 syntax compatibility was checked separately. The full commands,
versions, revisions, hashes and attempt records are in [acceptance.json](acceptance.json)
and the [Phase 3 follow-up acceptance](../phase-03-model-runner/followup-acceptance.json).

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
Collection completed with **78 completed, 70 failed and zero unexecuted checkpoints**.
Of 172 scheduled user turns, 160 executed (90 completed, 70 format failures); twelve
follow-ups were skipped after earlier turn failures. All twelve track runs are
accounted for. There are no unresolved infrastructure errors: 198 inference HTTP
requests succeeded and each response named the exact requested model. Sixty-seven
responses reached the output limit; three JSON envelopes omitted required fields.
These remain measured model failures and were not used to retune the settings or gold.

Both interfaces exercised the actual dispatcher/store: twenty JSON and thirty-two
native operations, including remembers, updates, forgets, reads and a denied
permission request. One invalid-scope operation and consent violations remain
visible. Private capture verifies 148 fresh conversation starts, one initial system
message, isolated user/workspace namespaces, unchanged actual sequence snapshots
between conversations and all four C10 store reopens. Public evidence includes
injected memory and before/after snapshots. Each track, policy and interface has
separate conformance/common-outcome scores and explicit control denominators.

The server reports llama.cpp and fingerprint `b11342-f1cee9941`. Requested settings
remain temperature 0, reasoning effort low, output limit 2048 and stream false;
server-effective settings remain null. All 198 requests supplied usage (414,580
input and 248,903 output tokens); local cost is null. Collection source is 70962bb,
wheel SHA-256 `16c690f591b7adcad151989db3012d2ac5033d9b2aca29bba67b20c81606e418`.
The later connection/pool-timeout classification fix is separately accepted in
f42305e, with wheel SHA-256
`5ab19722e0dfeba5befc73064ea5410aea8b91c6f42489650a1e865d6fc03c7c`.

Offline `replay` and `report` commands from that latest installed wheel each
succeeded with zero inference requests, preserving collection/scoring provenance
and reproducing identical condition scores. The asset bundle hash is
`37673a35e7bcf37058d705133e75ab676ef73345fbc49c6a9e13284161ae24bf`;
collection hash is `e100e6ebc2ea0b92516a64f8ba5e9d5968ed6119fe2e6afb1853667081da1d65`;
scorer hash is `f5cfb1e2a52df159790ee589f2a977a255f66f19607856a8787f24b7994a323e`.
Full source and per-asset hashes remain in the reviewed JSON and acceptance records.

Reviewed attempt 02 [findings](../../../memory/standalone-evaluations/phase04-smoke/attempt-02/findings.md),
[JSON](../../../memory/standalone-evaluations/phase04-smoke/attempt-02/results.json) and
[report](../../../memory/standalone-evaluations/phase04-smoke/attempt-02/report.md)
are committed. Raw request/response messages, provisional text, reasoning, HTTP
headers, credentials and private output paths are absent from the public report.

Raw output for each attempt remains outside Git under the operating system temporary
directory, named memory-bench-smoke-20261003-attempt-01 and
memory-bench-smoke-20261003-attempt-02. Disposable stores belong only to that attempt.
Attempt 02 removed all eighty owned SQLite files and its stores directory;
cleanup is complete. Implementation and evidence were committed in small batches
and normally pushed on `codex/standalone-memory-benchmark`.

The gate establishes the requested bounded infrastructure smoke, with the model
misses above. It does not establish model/policy superiority; fixed lexical scoring
can miss paraphrases and unexercised controls retain null denominators. Phase 5
remains **Not started**. No held-out inference was executed.
