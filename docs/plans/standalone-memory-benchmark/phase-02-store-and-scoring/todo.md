# Phase 2 todo

- [ ] Implement independent SQLite state and user/workspace namespace selection.
- [ ] Implement the shared operation dispatcher and explicit success/error results.
- [ ] Verify persistent rows, not assistant claims, as save evidence.
- [ ] Implement fixed fact/answer scoring and separate format/reason metrics.
- [ ] Freeze one-to-one fact-key/value/scope matching, duplicate false positives, zero-denominator nulls and TP/FP/FN aggregation.
- [ ] Score write changes relative to prepared state and check required prior facts against full final state.
- [ ] Score storage, scope, unnecessary saves, duplicates and consent independently.
- [ ] Separate current-value correction from historical-wording retirement.
- [ ] Check forgetting across all active copies and negative controls across answers.
- [ ] Keep write/read checkpoints independent and sequence prerequisites explicit.
- [ ] Report policy conformance separately from common outcomes and retain denominators.
- [ ] Verify empty-set, unchanged-prior, row-ID churn, wrong-key, scope-only and destructive-change fixtures through the dispatcher/scorer directly.
- [ ] Run deterministic store/scorer fixtures without inference and record evidence.
