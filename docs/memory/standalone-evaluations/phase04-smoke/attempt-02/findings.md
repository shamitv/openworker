# Smoke attempt 02 — infrastructure accepted, model misses retained

Date: 2026-10-03 (Asia/Kolkata). Collection source: commit 70962bb. The
independently installed collection wheel has SHA-256
`16c690f591b7adcad151989db3012d2ac5033d9b2aca29bba67b20c81606e418`.

The fixed P01 development smoke completed all twelve track runs: conservative and
recurring baseline instructions, JSON and native interfaces, write/read/sequence,
one repetition. All 148 checkpoints have final evidence: 78 completed, 70 failed
with model format errors, none unexecuted. Of 172 scheduled user turns, 160 ran
(90 completed, 70 failed); twelve follow-ups were skipped after an earlier turn
failed. Infrastructure acceptance does not imply successful model behavior.

The fresh catalog advertised `Ornith-1.5-35B-Uncensored-Q6_K`; every one of the 198
inference responses named that exact model and returned HTTP 200. There were no
retries, fallback, routing failures or store errors. The server identified itself
as llama.cpp with fingerprint `b11342-f1cee9941`. Every request submitted
temperature 0, reasoning effort low, max_tokens 2048 and stream false. Server-effective
settings were unavailable and remain null. All requests reported usage: 414,580
input tokens and 248,903 output tokens; local cost remains unpriced/null.

Sixty-seven requests ended with `finish_reason=length`; three further JSON responses
omitted required envelope fields. The resulting seventy failed turns/checkpoints
remain visible. Instructions, gold expectations, model ID and requested settings
were not tuned after observing these outcomes. Error entries can occur at both
turn and checkpoint levels; their summed diagnostic count is not a count of distinct
failed checkpoints.

Both interfaces executed real operations: twenty JSON and thirty-two native.
There were thirty successful remembers, ten forgets, four updates, six reads and
one permission request. One additional remember returned `invalid_scope`. The
permission request received the scripted denial; saving without the required
consent also occurred and is scored as a violation. The report keeps policy
conformance, common outcomes and each track separate. Prepared-write controls and
actual sequence controls retain their own exercised/unexercised denominators;
missing sequence prerequisites earn no manufactured correction/forgetting credit.

Captured request history verifies 148 fresh conversation boundaries, each beginning
with one system message and the new user message. All captured user/workspace
namespaces are qualified by track. Sequence starting snapshots equal the preceding
actual final snapshots, including the four store reopens before C10. Injected
memories, ordered operations, errors and persisted before/after snapshots are
included in the reviewed synthetic [JSON](results.json).

All eighty owned SQLite stores were removed and the attempt's stores directory is
absent. Raw request/response diagnostics remain outside Git. The published JSON
contains no raw messages, provisional answers, reasoning, HTTP headers, credentials
or private output paths.

Offline replay and report commands from the latest independently installed wheel
(`5ab19722e0dfeba5befc73064ea5410aea8b91c6f42489650a1e865d6fc03c7c`)
each made zero inference requests. Both preserve the collection/scoring provenance
and reproduce identical condition scores. Collection hash:
`e100e6ebc2ea0b92516a64f8ba5e9d5968ed6119fe2e6afb1853667081da1d65`.
Scorer hash: `f5cfb1e2a52df159790ee589f2a977a255f66f19607856a8787f24b7994a323e`.

The [first attempt](../attempt-01/findings.md) remains preserved as an infrastructure
failure. This explicitly labelled fresh-state attempt followed the single-system
request-assembly fix and repeated offline acceptance. It establishes the bounded
smoke gate, with the model misses above; it does not establish model/policy
superiority. Fixed lexical matching can miss paraphrases. Phase 5 remains pending;
no held-out inference was performed.
