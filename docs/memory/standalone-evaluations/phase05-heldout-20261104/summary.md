# Phase 5 held-out memory benchmark

The full held-out collection ran from 4 November 2026 at 22:16 to 8 November 2026 at 21:50, India time, using `Ornith-1.5-35B-Uncensored-Q6_K`. It covered 15 held-out personas, the conservative and recurring policies, baseline, rules and examples instructions, JSON and native interfaces, and the write, prepared-memory read and sequence tracks. Each combination ran once, for 180 persona-condition repetitions and 540 track runs.

The requested settings were temperature 0, reasoning effort low, a 12,288-token output limit and non-streaming responses. The server did not report its effective settings. The collection used the frozen asset and scorer definitions recorded in the accompanying results. Offline replay used the same scorer and made zero inference requests.

## Coverage and execution

All 6,660 scheduled checkpoints were executed. Of these, 6,203 completed and 457 failed, comprising 261 deadlines, 193 format errors and three operation-round exhaustion failures. The 540 tracks comprised 310 complete and 230 failed tracks. Of 7,740 scheduled user turns, 7,698 were executed, including 7,241 completed and 457 failed turns. The remaining 42 follow-up turns were unexecuted.

The collection made 12,069 inference requests and one catalog request. It received usage for 11,808 inference requests, totaling 30,232,018 prompt tokens and 16,059,408 completion tokens. Usage was unavailable for 261 requests. Inference request latency had a median of 17.69 seconds and a nearest-rank 90th percentile of 68.50 seconds. Local cost was unpriced.

## Selected results

These examples keep the model, conservative policy and JSON interface fixed. Policy conformance counts use the policy's annotated requirements. Storage counts are true positives, false positives and false negatives.

| Track | Instruction | Policy conformance | Storage TP / FP / FN | Common answers correct |
|---|---|---:|---:|---:|
| Prepared-memory read | baseline | 76/90 | 0 / 0 / 0 | 76/88, with 2 unscored |
| Prepared-memory read | rules | 83/90 | 0 / 0 / 0 | 83/88, with 2 unscored |
| Write | baseline | 118/195 | 50 / 97 / 100 | 10/14, with 181 unscored |
| Write | examples | 133/195 | 72 / 80 / 78 | 14/15, with 180 unscored |
| Sequence | baseline | 21/270 | 225 / 982 / 1,080 | 17/83, with 187 unscored |
| Sequence | examples | 39/270 | 391 / 931 / 914 | 20/90, with 180 unscored |

Prepared-memory read tests recall using supplied records. Write scores measure changes from independently prepared starting states. Sequence scores measure the accumulated persisted state across conversations, with storage counts summing repeated state observations. A read condition has no storage denominator, so its storage precision and recall are null. Many write and sequence checkpoints have no applicable answer target, contributing to the unscored answer counts.

For example, held-out persona H01's C5 prepared-memory read under conservative baseline JSON reached the deadline, and H01's C6 read under the same condition had a format error. The accompanying report contains condition-level measures and representative failures for the complete matrix.

## Interpretation

The two policies have different conformance requirements. The conservative policy requires explicit durability or future-chat preferences, while the recurring policy also saves stable, non-sensitive personal and recurring context. Compare common behavioral outcomes when examining policy differences.

Results describe one model and one repetition per condition. Fixed lexical matching can miss paraphrases or match text without understanding negation. Missing answers and unexercised prerequisites remain visible in the detailed results. The prior October collection used a different model and its detailed capture was unavailable, so these measurements are a separate experiment.

See [the detailed report](report.md) and [machine-readable results](results.json) for all conditions, denominators, provenance, error categories and case evidence.
