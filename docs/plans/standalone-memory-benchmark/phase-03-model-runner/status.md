# Phase 3 status

Status: Complete

Implementation and acceptance date: 2026-10-03 (Asia/Kolkata). Dependencies: Phases 1 and 2.

## Delivered and verified

The standalone package now provides a direct httpx client, JSON/native adapters,
one shared ordered response lifecycle, isolated condition/track/checkpoint stores,
durable captures, all five CLI actions, and offline replay/Markdown/sanitized JSON
reporting. No OpenWorker, SDK/provider router, browser or hosted environment is used.

The client accepts explicit loopback/private IP endpoints or localhost, with an empty
root path or /v1. It verifies exact advertised IDs, refuses provider aliases, public
routes and redirects, and disables credentials/proxy inheritance, retries and fallback.
Fixed submitted settings are temperature=0, reasoning_effort=low, max_tokens=2048,
stream=false. Server-effective settings remain null unless reported. Unsupported
settings and API/configuration/prerequisite failures remain explicit failures.

Both adapters execute operations serially through the same dispatcher, feed results
and errors back in order, preserve successful mutations and retain provisional text
only as diagnostics. Finals must be nonempty and operation-free. Six operation batches
plus one final-answer request, at most seven requests, share a 180-second turn deadline.
SQLite lock waits and queries are bounded by the remaining budget. No malformed response
repair, parameter removal, fallback or failed-request retry occurs.

Prepared write/read checkpoints restore their own snapshots. Sequence alone retains
actual writes and reopens its store at prescribed restarts. Abstract namespaces are
qualified per condition/track. Fresh conversations contain one initial system envelope
and their current user turn; only follow-ups retain actual current-conversation history.
Shared policy/state and interface-specific instructions remain distinct sections.

Captured evidence includes injected state, requests/responses and metadata, usage,
operations/results, provisional/final answers, snapshots, schedule and partial coverage.
Each request attempt is flushed before sending and each operation is durably recorded.
Interruption and failures preserve evidence and unexecuted coverage; owned clients and
SQLite files are released. Missing usage, empty ratios and local price remain null.

## Executed acceptance

From benchmarks/memory, with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 for source pytest:

```text
C:\work\openworker\.venv\Scripts\python.exe -m pytest -c pyproject.toml --confcutdir=tests --basetemp build/phase34-source-acceptance-02 -q -p no:cacheprovider
C:\work\openworker\.venv\Scripts\python.exe tools/verify_portability.py --wheelhouse build/wheelhouse
```

- Source suite: **343 passed in 148.64s**.
- Copied, built and installed wheel: **343 passed in 146.82s** from an unrelated
  working directory, with source fallback disabled and OpenWorker absent.
- Offline checks include every frozen lifecycle fixture executed through both adapters,
  ordered mixed batches, read-dependent answers, consent granted/denied, malformed native
  arguments, duplicate JSON keys/nonfinite numbers, deadlines, SQLite lock waits,
  six batches followed by a final and refusal to execute a seventh batch.
- Execution checks cover follow-ups/fresh chats, injection, namespace and track-order
  isolation, persisted writes, store restarts, interrupted/failed/unexecuted coverage,
  catalog/API failures and cleanup. Replay/report cannot construct an inference client.
- A complete mocked fixed smoke checks 12 track runs, 148 checkpoints and 172 user turns.
  These mocked calls are deterministic checks, not live model measurements.
- All prior corpus/store/scoring suites remain green. Network and OpenWorker imports
  are blocked during tests. Python 3.10 syntax parsing passes for 38 Python files.
- Installation uses the offline wheelhouse. Acceptance inference requests: **0**.

Full environment, source/asset hashes, commands and wheel evidence are recorded in
[acceptance.json](acceptance.json). The private detailed report is retained at
benchmarks/memory/build/portability-zwr6mw49/report.json.

## Revisions and limitations

Implementation was committed in small tested batches: 8475631, 78695fc, 746fee7,
8ebe803, 2714144 and 2649a7d. Commit 70962bb corrects request assembly after Phase 4
attempt 01 exposed a server template that rejects two system messages. The failed
attempt remains preserved; both full suites passed again before a fresh attempt.
No policy text, gold labels, model IDs or requested settings changed.

Bundle SHA-256: 37673a35e7bcf37058d705133e75ab676ef73345fbc49c6a9e13284161ae24bf.
Scorer SHA-256: f5cfb1e2a52df159790ee589f2a977a255f66f19607856a8787f24b7994a323e.
Wheel SHA-256: 16c690f591b7adcad151989db3012d2ac5033d9b2aca29bba67b20c81606e418.

Runtime acceptance used Python 3.14.2 on Windows; Python 3.10 received syntax checks,
not runtime execution. The fixed lexical scorer can miss paraphrases or overmatch
text and does not interpret negation; unmatched records remain inspectable. The
server may accept a parameter without reporting its effective value; the report
records the submitted values and leaves server-effective values unavailable.
Live acceptance belongs to Phase 4. Phase 5 remains pending.
