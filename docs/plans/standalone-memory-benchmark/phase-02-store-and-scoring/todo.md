# Phase 2 todo

- [x] Implement independent SQLite state and user/workspace namespace selection.
- [x] Implement the shared operation dispatcher and explicit success/error results.
- [x] Verify persistent rows, not assistant claims, as save evidence.
- [x] Implement fixed fact/answer scoring and separate format/reason metrics.
- [x] Freeze one-to-one fact-key/value/scope matching, duplicate false positives, zero-denominator nulls and TP/FP/FN aggregation.
- [x] Score write changes relative to prepared state and check required prior facts against full final state.
- [x] Score storage, scope, unnecessary saves, duplicates and consent independently.
- [x] Separate current-value correction from historical-wording retirement.
- [x] Check forgetting across all active copies and negative controls across answers.
- [x] Keep write/read checkpoints independent and sequence prerequisites explicit.
- [x] Report policy conformance separately from common outcomes and retain denominators.
- [x] Verify empty-set, unchanged-prior, row-ID churn, wrong-key, scope-only and destructive-change fixtures through the dispatcher/scorer directly.
- [x] Run deterministic store/scorer fixtures without inference and record evidence.
