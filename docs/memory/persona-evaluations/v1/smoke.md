# P01 smoke validation — 2026-10-02

The smoke gate passed on Ubuntu 26.04.1, Python 3.14.4, OpenShell 0.0.116, and the local `Ornith-1.5-35B-Uncensored-Q6_K` endpoint. It exercised real password accounts, HTTPS certificate verification, CSRF, WebSockets, OpenShell sessions, SQLite persistence, and restart. Only P01 and its sentinel were used before the harness push.

## Explicit attempts

| Attempt | Result | Action |
|---|---|---|
| 01 | Gateway startup failed before a model turn | Preserve the operator's actual HOME/XDG runtime directories in the gateway environment; cloud credentials remain excluded |
| 02 | All ten conversations / thirteen turns executed; final cleanup guard failed | Match server socket reuse semantics so TCP TIME_WAIT is not mistaken for a live listener; preserve reports on cleanup failure |
| 03 | Complete: ten conversations / thirteen turns; restart, isolation and cleanup passed | Retain sanitized evidence; proceed to commit/push |

These were explicit fresh-state attempts, not automatic retries. The successful smoke's collector/source and corpus hashes are in `smoke-results.json`. Its fixed expected facts were unchanged. The final scorer was replayed against saved synthetic events without additional inference: `tool_proposed` contains arguments whereas `tool_started` does not. The temporary-save attempt count now correctly records one. The scoring-source hash and replay flag record that provenance.

Offline regression result before push: **117 passed**. A sandbox restriction caused the initial TestClient processes to hang; they were stopped and the same offline suites ran with normal local-server permissions.

## Model outcomes

- Grade 8 CBSE was automatically stored and recalled, but the matching early memory was a **workspace-scoped temporary draft note**, rather than a clean global user fact.
- Explicit preference, notebook and A/B headings were stored. A/B headings were recalled in the expected workspaces.
- The updated Grade 9 context was recalled after restart, but an old Grade 8 reference remained active, so strict correction replacement failed.
- The notebook was deleted and remained forgotten after restart.
- The temporary `Spark-P01` label was saved and recalled in A after restart: an unnecessary save.
- No permission requests, turn/API errors, malformed tool results, or cross-account control leaks were observed. The sentinel recalled its own control and could not open P01's workspace.

The gate establishes harness correctness, not perfect model memory behavior. Matching uses fixed phrase/concept groups; paraphrases can be undercounted. A save claim without a row change is a diagnostic heuristic, not an independent semantic judgment.

The successful attempt made 25 main and 22 title requests. Main usage was 225,649 input / 12,400 output tokens; title usage was 4,859 input / 1,385 output tokens. All inference used the local endpoint. Cost is unpriced; no OpenRouter requests were made.

Private operational logs remain outside Git in the test operator's private output directories. All three disposable account deployment roots were removed. The full sweep must use new state after the harness push succeeds, and its statistics must exclude smoke attempts.
