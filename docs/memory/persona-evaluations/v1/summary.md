# OpenWorker memory evaluation: summary report

**Report date:** 3 October 2026 (Asia/Kolkata)  
**Execution:** 2 October 2026, 22:17–23:44 IST  
**Model:** `Ornith-1.5-35B-Uncensored-Q6_K`  
**Inference endpoint:** `http://10.42.0.202:8090/v1`

## Summary

The hosted evaluation completed **15 synthetic personas, 150 fresh conversations and 195 scripted turns**, with one repetition per persona. The harness passed its routing, memory injection, account isolation, restart and cleanup checks. Model memory behavior was inconsistent: explicit instructions produced stronger storage results than natural recurring context.

The primary school-revision scenario, P01, **did not automatically save or recall Grade 8 CBSE** in the full sweep. After an explicit remember instruction, it stored the context and later recalled the corrected Grade 9 CBSE context after restart. Its earlier smoke result differed and is recorded separately.

This report summarizes existing evidence. Preparing it made no new inference requests. The hosted smoke and full sweep used only local inference, with **no OpenRouter usage**.

## Memory results

| Measure | Result |
|---|---:|
| Automatic context save without consent questions | 5/15 |
| Context recall in a fresh chat before explicit remembering | 7/15 |
| Automatic context save and recall together | 5/15 |
| All matching early context rows correctly use global scope | 2/15 |
| Automatic preference-format save and recall | 3/15 |
| Automatic preference-reason save and recall | 3/15 |
| Explicit context storage | 15/15 |
| All matching explicit context rows correctly use global scope | 10/15 |
| Corrected context recall after restart | 13/15 |
| Strict removal of original context from active memory | 3/15 |
| Notebook forgetting plus UNKNOWN recall after restart | 12/15 |
| Account isolation and peer workspace denial | 15/15 |

An automatic-save success requires matching persisted memory before the blind probe and no consent question during C1/C2. Global scope is checked separately: a fact embedded in a temporary workspace note can pass storage and recall while failing the scope check.

## Failures and observed behavior

- **Temporary information persisted:** five saved rows across four personas contained labels intended only for a draft.
- **Forgetting missed another copy:** P07 deleted its notebook entry, but the label remained inside its workspace-heading entry and was recalled in B.
- **Workspace selection was overridden in an answer:** P11 received correct injected memory, then read account-wide entries and mentioned both workspace headings as a conflict.
- **Three visible consent questions** were recorded; structured consent questions were zero.
- **Two tool failures** occurred: an update referenced a missing memory ID, and an output limit truncated a tool call.
- **Thirteen `todo_write` calls** violated the memory-only prompt. They required no approval.
- Five duplicate active fact matches were recorded. Turn errors, API failures, timeouts and missing labelled probe fields were zero.

## Performance and environment

| Request category | Requests | Input tokens | Output tokens |
|---|---:|---:|---:|
| Main turns and memory-tool iterations | 349 | 3,068,162 | 173,893 |
| Automatic titles | 326 | 71,875 | 20,790 |

Mean scripted-turn latency was **26.21 seconds**, median **24.08 seconds**, and p95 **54.84 seconds**. Total execution took **87.2 minutes**, including provisioning, restart and cleanup. All requests reported usage. Local cost is unpriced.

The evaluation ran on Ubuntu 26.04.1 with Python 3.14.4, Nginx 1.28.3 and OpenShell 0.0.116. It used real HTTPS password login, CSRF-protected REST calls, session WebSockets and private account engines. The temporary certificate was explicitly trusted; TLS verification remained enabled.

Main settings were low reasoning effort, 2,048 output tokens, six iterations and a 180-second turn timeout. Main temperature retained its application default; both reviewer modes were disabled. Existing memory guidance remained unchanged.

## Validation, cleanup and interpretation

The affected deterministic suites passed **120 tests**. The full sweep began after the harness was committed and normally pushed. Collection revision was `9d01ebb`; scoring revision was `3410716`. Scorer-only fixes were replayed against captured evidence without changing prompts or making new inference requests.

Disposable account stores, processes, owned sandboxes, source copies and archives were removed. Ports 18453, 18866 and 18867 were released. The operator's OpenShell gateway and unrelated deployments were preserved; private diagnostics remain outside Git.

The results support explicit remembering as the more consistent path under these settings. Automatic selection of durable facts, correct global scope, exclusion of temporary details and complete forgetting need further attention. Infrastructure isolation passed while some model answers mishandled account-wide memory reads.

One repetition per persona provides descriptive evidence. Fixed matching can miss paraphrases and counts historical or negated original-context references against strict correction. Inference-server hardware was not captured. Earlier model comparisons used a different protocol and should be interpreted separately.

## Supporting evidence

- [Detailed report and per-persona results](report.md)
- [Sanitized transcripts, snapshots and metrics](results.json)
- [Corpus, protocol and reproduction runbook](README.md)
- [Smoke findings](smoke.md)
- [Completed execution checklist](checklist.md)

The detailed report and JSON preserve corpus and source hashes, collection/scoring provenance, request parameters and cleanup verification.
