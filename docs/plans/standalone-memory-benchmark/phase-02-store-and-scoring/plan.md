# Phase 2 — Independent memory store and scorer

## Implementation

Implement the Phase 1 contract using Python's SQLite support. Create an independent store for each condition/repetition. Resolve user/workspace context from the runner, and namespace all reads and writes by that context. Selected prompt memory contains the user's global facts and the current workspace's facts. Account-wide reads within the same abstract user are permitted where defined by the frozen contract; they must never select another user.

Implement remember, read, update, forget and permission decisions through one operation dispatcher used by both interfaces. Remember must not silently deduplicate facts or change scope to manufacture a good score. Invalid schemas, invalid scope and missing IDs produce recorded errors. Mutation success and committed rows establish save evidence; visible promises do not.

Score stored current values and supplied answers with the fixed aliases and matching rules. Keep storage precision, storage recall, scope correctness, unnecessary/temporary saves, duplicates, correction, forgetting, consent requests and tool/format errors separate. Score preference format and reason separately. Retain raw persisted state so unmatched or unsupported facts can be inspected.

Measure current-value correction independently from old-value retirement. Deletion checks must inspect every active copy of the target fact, not only the success of one forget call. UNKNOWN responses must satisfy the frozen format and exclusion rules. A correct positive field must not conceal an incorrect workspace or forgotten control elsewhere in the answer.

Write checkpoints use their correctly prepared prior state independently, even if another checkpoint would fail. Read tests use prepared memory independent of writing. Sequence tests retain actual earlier failures: absent prerequisites make correction/forgetting unexercised, with null outcomes and explicit reasons. Do not count an unexercised control as a pass.

Report policy conformance and common behavioral outcomes separately. Use correct conservative no-save decisions as conformance successes where annotated; report their lower automatic storage as a separate outcome. Preserve case-level denominators and errors when aggregating.

## Acceptance

Deterministic fixtures prove operation success/failure, namespace and scope boundaries, persistence, missing-ID handling, schema errors, duplicates, temporary saves, correction, deletion of multiple copies and permission decisions. Test verbal save claims without rows, UNKNOWN answers, malformed/missing fields, negative controls and historical/current-value separation.

The same operations executed through JSON and native adapters produce identical store results. Write/read prerequisites and sequence unexercised outcomes are verified without inference. Store and scorer run without OpenWorker imports or installation. Record scorer revision/hash and executed checks in status.md.
