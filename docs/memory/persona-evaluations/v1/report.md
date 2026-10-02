# Local model memory evaluation — 15 synthetic personas

## Result

The hosted harness completed **15 personas, 150 fresh conversations and 195 scripted turns**, once each, with `Ornith-1.5-35B-Uncensored-Q6_K`. All scheduled conversations, eight gateway/engine restart batches, account-isolation checks and cleanup completed. No skipped scenarios or harness retries; no OpenRouter requests.

Automatic context save and recall succeeded for **5/15** personas; clean global automatic scope succeeded for **2/15**. Explicit context storage succeeded for **15/15**. The primary P01 Grade 8 CBSE anchor **failed automatic save and recall in this full run**. It passed those token checks in the earlier smoke through a temporary workspace note; smoke is separate evidence, not part of these totals.

After explicit correction, corrected-context recall following restart scored **13/15**. Strict replacement of every active original reference scored **3/15**. Forgetting the notebook value and reporting UNKNOWN after restart scored **12/15**. These distinguish storage, retrieval and removal.

## Protocol and provenance

| Item | Actual value |
|---|---|
| Protocol / corpus | `hosted-memory-personas-v1`; expanded static [corpus](../../../../tests/fixtures/memory/personas_v1.json) |
| Corpus SHA-256 | `13b2476e29f9179223a61e1f11b4cff58fa3f3695e16611569bab258d4a3ff88` |
| Collection Git revision | `9d01ebb7965253331fe7ae1cbb2864e30663ff1b` (pushed before sweep) |
| Collection runner SHA-256 | `abed20ccc68dc6f5056eb96eeb4e0bf76bc4813cb078c07c18fae9e85e9cfdaf` |
| Scoring Git revision | `3410716cb12e401bac2ede4a171e02b93b5a4839` |
| Scoring runner SHA-256 | `ff1c1ee46f6e9d1f642fbad87b20da6f5f4964d30d192bff810c1c1259ac6069` |
| Scoring replay | Saved synthetic transcripts/SQLite snapshots only; no new inference. Independent negative-control and tool-failure counters added; corpus, prompts, routing and runtime unchanged. |
| UTC interval | 2026-10-02T16:47:25.363225+00:00 → 2026-10-02T18:14:35.670007+00:00 |
| Wall time | 87.2 minutes, including provisioning, restart and cleanup |
| Host | Ubuntu 26.04.1 LTS VM `10.42.0.248`; Python 3.14.4; Nginx 1.28.3; OpenShell 0.0.116 |
| Local inference | `http://10.42.0.202:8090/v1`; model verified using its `/models` before execution |
| Hosted transport | Nginx `https://127.0.0.1:18453` → gateway `127.0.0.1:18866` → private account engines; explicitly trusted temporary certificate with TLS verification enabled |
| Inference recording | Fixed local upstream through `127.0.0.1:18867`, serialized requests; no redirects, model fallback, paid routing or harness retries |
| Main settings | Reasoning effort low; output 2048; six iterations; 180 seconds/turn; default temperature unset; interactive permissions; both reviewer modes off |
| State | Fresh independent accounts/stores; two plain non-Git workspaces per owner; seven owner pairs and P15/sentinel; A/B outside scratch |

C1/C2 use natural context and preference, C3 probes blind recall, C4 establishes explicit global/workspace controls, C5/C6 test B/A, C7 probes the peer, C8 corrects and forgets, C9 probes B, and C10 probes A after restarting against existing account data and signing in again. No conversation receives prior conversational messages. Only the sentinel is seeded with Guard-P16.

## Automatic memory before explicit instructions

| Measure | Result |
|---|---:|
| Persisted context match before C3, including profiles with consent questions | 7/15 |
| Automatic context save without C1/C2 consent questions | 5/15 |
| Blind context recall in C3 | 7/15 |
| Automatic context save and recall jointly | 5/15 |
| All matching early context rows use global scope | 2/15 |
| Automatic preference-format save / recall / joint | 4/15 / 4/15 / 3/15 |
| Automatic preference-reason save / recall / joint | 4/15 / 4/15 / 3/15 |
| Preference-format / reason clean automatic global scope | 2/15 / 2/15 |

| Persona | Context save | C3 recall | Joint | Clean global scope | Format joint | Reason joint |
|---|---:|---:|---:|---:|---:|---:|
| P01 Mira | no | no | no | no | no | no |
| P02 Dev | no | no | no | no | no | no |
| P03 Noor | no | no | no | no | no | no |
| P04 Ria | no | no | no | no | no | no |
| P05 Ivo | no | yes | no | no | no | no |
| P06 Sia | no | no | no | no | no | no |
| P07 Kian | yes | yes | yes | no | yes | yes |
| P08 Lena | no | no | no | no | no | no |
| P09 Omar | yes | yes | yes | no | no | no |
| P10 Tavi | no | yes | no | no | no | no |
| P11 June | no | no | no | no | no | no |
| P12 Rohan | yes | yes | yes | yes | yes | yes |
| P13 Edda | yes | yes | yes | no | no | no |
| P14 Niko | yes | yes | yes | yes | yes | yes |
| P15 Uma | no | no | no | no | no | no |

Automatic saves require persisted matching content before C3 and no C1/C2 consent request. The raw persisted-match row above makes that stricter definition visible. A temporary note containing the context can satisfy storage and recall while failing global scope. Recall without stored matching memory cannot satisfy the joint metric.

## Explicit memory, correction and forgetting

| Measure | Result |
|---|---:|
| Explicit context / format / reason / notebook saves | 15/15 / 15/15 / 15/15 / 15/15 |
| All matching rows have requested global context / format / reason / notebook scope | 10/15 / 12/15 / 12/15 / 12/15 |
| A and B heading saves / correct scope | A: 15/15 / 15/15; B: 14/15 / 14/15 |
| Correction / forgetting prerequisite present | 15/15 / 15/15 |
| Strict corrected-value replacement after C8 | 3/15 |
| Corrected context recall in B (C9) / after restart in A (C10) | 11/15 / 13/15 |
| Notebook value removed after C8 / survives restart plus UNKNOWN reply | 14/15 / 12/15 |
| Preference format / reason recall after restart | 11/15 / 12/15 |
| Heading recall A C6 / B C9 / A after restart | 15/15 / 14/15 / 15/15 |

| Persona | Explicit context | Strict correction | Corrected recall after restart | Forgetting after restart | Temporary rows |
|---|---:|---:|---:|---:|---:|
| P01 | yes | no | yes | yes | 0 |
| P02 | yes | yes | yes | yes | 0 |
| P03 | yes | no | no | yes | 0 |
| P04 | yes | yes | yes | yes | 1 |
| P05 | yes | no | yes | yes | 0 |
| P06 | yes | no | yes | yes | 0 |
| P07 | yes | no | no | no | 2 |
| P08 | yes | no | yes | yes | 0 |
| P09 | yes | no | yes | no | 0 |
| P10 | yes | no | yes | yes | 1 |
| P11 | yes | no | yes | yes | 0 |
| P12 | yes | yes | yes | yes | 0 |
| P13 | yes | no | yes | yes | 1 |
| P14 | yes | no | yes | no | 0 |
| P15 | yes | no | yes | yes | 0 |

A missing earlier memory makes correction/forgetting unexercised (`null`). Strict correction also rejects active historical or negated mentions of the original context; it does not interpret the semantics of “updated from” or “not anymore.” Explicit scope checks are conservative when both correctly scoped and older incorrectly scoped matching rows remain.

## Isolation, noise and errors

| Check | Result |
|---|---:|
| Fresh UUID, expected account/model/workspace routing, injection matches SQLite scope | 150/150 conversations |
| Owner controls excluded from peer listing/prompt/tools/answer; owner-folder access denied | 15/15 |
| Peer recalls its own notebook control | 15/15 |
| A heading absent from B C5 injection; B absent from A C6/C10 injection | 15/15 / 15/15 / 15/15 |
| Wrong-workspace heading mentions in owner probe answers | 1 |
| Temporary-label save attempts / distinct saved rows | 5 / 5 |
| Personas with persisted temporary labels | 4/15 (P04, P07, P10, P13) |
| Temporary label absent from active memory / answer after restart | 11/15 / 11/15 |
| Duplicate active fact matches / unmatched saved rows | 5 / 0 |
| Consent questions: structured / visible-text detection | 0 / 3 |
| Unrelated approval requests (denied) / non-memory tool calls | 0 / 13 |
| Tool failures / turn errors / timeouts / malformed tool results / missing labelled fields | 2 / 0 / 0 / 0 / 0 |
| Save claims without a persisted row change (heuristic) | 2 |

Non-memory `todo_write` calls violate the per-message memory-only instruction. They request no approval, so they are counted separately from approval requests. Tool-failure counts include both framework errors and error-valued memory results; they do not disappear merely because a turn finishes successfully. Workspace scope controls prompt injection. Within one account, `memory_read` and listing are account-wide: a model can read another workspace entry and then use it incorrectly. That is scored independently from injection. Unknown replies cannot prove a value was deleted; active SQLite rows are checked separately.

## Requests, tokens and latency

| Kind | Requests | Failed | Missing usage | Input tokens | Output tokens | Upstream seconds | Queue seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| main | 349 | 0 | 0 | 3068162 | 173893 | 4592.56 | 399.88 |
| title | 326 | 0 | 0 | 71875 | 20790 | 565.68 | 175.36 |

Across 195 scripted turns: mean **26.21s**, median **24.08s**, p95 **54.84s**, maximum **114.05s**. Turn time includes memory-tool iterations and queueing. Local cost is **unpriced (`null`)**. Missing usage stays `null`; token totals include only reported usage.

Effective wire parameters captured by the recording proxy:

```json
{
  "main": [
    {
      "max_tokens": 2048,
      "reasoning_effort": "low",
      "stream": true
    }
  ],
  "title": [
    {
      "max_tokens": 64,
      "reasoning_effort": "none",
      "temperature": 0.2
    }
  ]
}
```

Main request failures: 0; title request failures: 0. Request counts include all application calls, so they exceed scripted turns. Automatic titles are auxiliary requests; their application defaults and any application-level parameter repair are visible in the ledger. The harness does not rerun conversations or retry failed turns.

## Representative synthetic evidence

### P01: primary anchor and strict correction

C3 starts with no stored memory. Its answer includes:

```text
context: UNKNOWN
style: UNKNOWN
temporary_label: UNKNOWN
```

After explicit C4, P01 stores the context. C8 changes the active row to Grade 9 but retains “updated from Grade 8.” Strict old-value removal fails, while C10 recalls Grade 9, preserves the preference and A heading, and reports the forgotten notebook and temporary label as UNKNOWN.

### P07: a deleted value survives in another row

Deleting the dedicated notebook row did not remove Solace-P07 from the B-heading row. C9 used that surviving value as the notebook answer. An early draft label also survived in A. This is why deletion is checked across all active content rather than by the success of one delete tool call.

### P11: account-wide tool read crosses a workspace preference

B received the expected injection, but the model read account-wide entries and answered that Anchor-P11 and Harbor-P11 conflicted. Positive B-heading recall therefore coexists with a failed exclusion check. After restart in A, the reply used Anchor-P11 correctly.

## Validation, deployment and cleanup

Offline corpus validation: **15 profiles, 150 conversations, 195 turns**. Affected deterministic suites: **120 passed**, including memory, memory API, hosted fixture helpers and supervisor regressions. The first harness push followed the limited P01/sentinel smoke; two explicitly recorded earlier smoke attempts exposed environment and TIME_WAIT handling defects. No other personas ran before that push.

The full sweep deployed a Git archive of the pushed collection revision, verified source/corpus hashes, used the existing sandbox-ready VM dependencies and built SPA, and allocated fresh evaluation roots. Eight batches restarted the gateway and private engines without reprovisioning the stores. Completed sessions were disconnected/deleted and their owned sandboxes released.

Collector cleanup: **complete: owned deployments removed and ports released**. Private logs/checkpoints/request metadata remain in the evaluation output directory, outside Git. The post-run check confirmed ports 18453/18866/18867 released, deployment roots and temporary source copies/archives removed, and the preserved operator OpenShell gateway on port 17670 reachable through its backend. Each batch verified its owned sandboxes absent before deleting account state; unrelated deployments were untouched. The deployed SPA index hash matches the local build and is recorded in the JSON.

Private diagnostics remain at `/home/ubuntu/.cache/openworker-persona-full-results-20261002-01/private`; the console log is `/home/ubuntu/.cache/openworker-persona-full-console-01.log`. Smoke evidence remains in its separate private output directories.

## Limits

- One local model, one repetition per profile. These are observations under the current policy, not a stable model ranking. Main temperature is left at the application default; smoke and full outcomes can differ.
- Fixed matching can undercount abbreviated/paraphrased answers, such as “landscape” without “photography.” It can also match the original context in negated or historical wording. No LLM grader or changed aliases were used after seeing results.
- Matching checks the requested facts and controls, not every detail in an answer or memory. Some model memories add unsupported details. Unmatched-row and false-save-claim counts are diagnostics, not full semantic accuracy scores.
- This is HTTPS REST/WebSocket acceptance with real engines and memory storage. It does not add interactive browser rendering coverage, public tunnel acceptance or the separate Windows sandbox gate.
- Inference-server hardware and backend version were not captured; latency reflects the current local service and its queue.
- Earlier model benchmarks used a different conversation protocol and isolated tool loop. Their percentages and tokens are retained separately and cannot be pooled with this hosted evaluation.

## Evidence and reproduction

See [sanitized full results](results.json), [smoke findings](smoke.md), [smoke results](smoke-results.json), [runbook](README.md) and [execution checklist](checklist.md). The full JSON preserves injected memory, tool results, transcripts, read-only snapshots, per-persona scores and request metadata. No credentials, cookies, CSRF tokens, engine keys or private logs are included.
