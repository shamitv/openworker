# Phase 2 — Independent memory store and scorer

## Implementation

Implement the Phase 1 contract using Python's SQLite support. Create an independent store for each condition/track/repetition, with separate starting snapshots for write/read checkpoints and continuity only within a sequence. Resolve user/workspace context from the runner, and namespace all reads and writes by that context. Selected prompt memory contains the user's global facts and the current workspace's facts. Account-wide reads within the same abstract user are permitted where defined by the frozen contract; they must never select another user.

Implement remember, read, update, forget and permission decisions through one operation dispatcher used by both interfaces. Remember must not silently deduplicate facts or change scope to manufacture a good score. Invalid schemas, invalid scope and missing IDs produce recorded errors. Mutation success and committed rows establish save evidence; visible promises do not.

Score stored current values and supplied answers with the fixed aliases and matching rules. Keep storage precision, storage recall, scope correctness, unnecessary/temporary saves, duplicates, correction, forgetting, consent requests and tool/format errors separate. Score preference format and reason separately. Retain raw persisted state so unmatched or unsupported facts can be inspected.

Freeze these scoring rules before inference:

- Match facts one-to-one by canonical fact identity/key under frozen accepted key aliases, accepted current value, user namespace and scope. Each expected fact and persisted record can earn at most one true positive. Extra copies are false positives and are also reported as duplicates. A correct value under the wrong fact key or scope is a false positive and leaves the expected fact missing.
- In write checkpoints, compare actual and expected changes relative to the supplied starting snapshot. Match unchanged prior facts first, ignoring row-ID churn; added copies and changes in canonical fact identity, value or scope enter new-write precision/recall. Expected deletions and preservation of required prior facts are checked against full final state. Reasserting an unchanged fact earns no new-write credit, though it may satisfy conformance. Correction and forgetting retain their separate current-state checks.
- For sequence storage, use actual accumulated current state at the annotated checkpoints. Prepared-memory read tracks report recall and any unintended mutations; seeded records earn no save credit.
- Let TP be matched facts, FP unmatched actual facts and FN unmatched expected facts in the scored set. Precision is `TP / (TP + FP)` and recall is `TP / (TP + FN)`. A zero denominator is `null`. With expected facts but no actual saves, recall is `0`; with unnecessary saves and no expected facts, precision is `0`. Correct empty decisions are evaluated through policy conformance.
- Compute storage precision/recall against policy-specific expectations; report the corpus's fixed common behavioral targets separately. Aggregate TP/FP/FN within each reported condition and track before division. Publish counts, zero-denominator cases, exercised controls and failed/unexecuted coverage. An unscorable failure cannot become a successful no-op case.

Measure current-value correction independently from old-value retirement. Deletion checks must inspect every active copy of the target fact, not only the success of one forget call. UNKNOWN responses must satisfy the frozen format and exclusion rules. A correct positive field must not conceal an incorrect workspace or forgotten control elsewhere in the answer.

Write checkpoints use their correctly prepared prior state independently, even if another checkpoint would fail. Read tests use prepared memory independent of writing. Sequence tests retain actual earlier failures: absent prerequisites make correction/forgetting unexercised, with null outcomes and explicit reasons. Do not count an unexercised control as a pass.

Report policy conformance and common behavioral outcomes separately. Use correct conservative no-save decisions as conformance successes where annotated; report their lower automatic storage as a separate outcome. Preserve case-level denominators and errors when aggregating.

## Acceptance

Deterministic fixtures prove operation success/failure, namespace and scope boundaries, persistence, missing-ID handling, schema errors, duplicates, temporary saves, correction, deletion of multiple copies and permission decisions. Test verbal save claims without rows, UNKNOWN answers, malformed/missing fields, negative controls and historical/current-value separation. Cover empty expected/actual sets, unchanged prepared records, row-ID churn, duplicate additions, equal values under different fact keys, scope-only changes, destructive changes to required prior facts and aggregate numerators/denominators.

Test the shared dispatcher directly, including ordered batches with mixed successful and failed operations. JSON/native adapter parity is a Phase 3 acceptance check. Write/read prerequisites and sequence unexercised outcomes are verified without inference. Store and scorer run without OpenWorker imports or installation. Record scorer revision/hash and executed checks in status.md.
