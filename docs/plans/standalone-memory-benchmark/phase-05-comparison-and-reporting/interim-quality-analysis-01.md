# Interim response quality analysis

Snapshot: 2026-10-04 11:15 IST. Attempt 03 was running. This is partial evidence, not final Phase 5 acceptance. Analysis made zero inference requests and used the frozen installed scorer. Unique finalized checkpoints from finished track runs were used; active tracks were excluded. The private manifest/checkpoint snapshot and its hashes are retained outside Git. Aggregates and scorer provenance are in [interim-quality-analysis-01.json](interim-quality-analysis-01.json).

The snapshot contains 186 finished track runs and 2,294 finalized checkpoints. Conservative baseline and rules conditions have full coverage of all 15 personas in both interfaces and each track. Examples has only two finished JSON personas; recurring has not been evaluated in this snapshot. Primary conclusions below use the fully covered baseline/rules conditions.

## Protocol reliability

Of 1,435 received JSON-interface responses, 294 passed the frozen adapter contract (20.5%): 235 operation batches and 59 nonempty final answers. All 1,921 received native-interface responses passed their adapter contract. Seven inference requests ended without a response (six JSON, one native). These response statistics have different current condition coverage and are descriptive. Adapter acceptance does not imply correct memory operations or answers.

Every finished conservative baseline/rules JSON track run failed at least one checkpoint. This does not mean every individual response failed. Prepared-memory JSON read had 4 correct answers among 4 scored answers for baseline, and 7 among 7 for rules, but only 4/90 and 7/90 read checkpoints completed. Conditional success on these small selected subsets cannot establish high overall reliability.

## Native task outcomes with complete persona coverage

| Frozen measure | Baseline | Rules |
|---|---:|---:|
| Prepared-memory read answer correctness | 69/90 (76.7%) | 64/90 (71.1%) |
| Prepared-memory read required answer format | 69/90 | 67/90 |
| Sequence probe answer correctness | 17/90 (18.9%) | 12/89 (13.5%); 1 probe unscored |
| Write storage precision | 45/160 (28.1%) | 47/179 (26.3%) |
| Write storage recall | 45/150 (30.0%) | 47/150 (31.3%) |
| Prepared-write current correction | 15/15 | 15/15 |
| Prepared-write historical wording retirement | 5/15 | 2/15 |
| Prepared-write forgetting | 30/30 | 29/30 |

Prepared-memory reading is stronger than combined saving and later recall under the frozen metrics. Rules has mixed effects: slightly greater write recall, lower precision, and lower read/sequence answer scores. One repetition provides no statistical superiority claim.

## Interpretation of storage scores

The frozen matcher requires recognized keys as well as value aliases and scope. A separately identified exploratory diagnostic found matching expected values in the correct scope under unrecognized keys for 90 of 105 baseline write false negatives, and 85 of 103 rules write false negatives. Those counts do not modify the frozen scores, enforce one-to-one rematching, or provide corrected recall. Low frozen storage scores therefore cannot all be described as lost facts or hallucinated memory.

There are also failures beyond key matching. One inspected H01 sequence response reported the preference reason as UNKNOWN despite a separate saved record describing selection by fold difficulty. The conservative policy's initial incidental preference was saved even though its annotations required no durable write. Historical-wording retirement and consent failures are separately recorded. General factual correctness of the explanatory chat answers was not evaluated.

## Limits

Collection is incomplete; recurring and examples comparisons remain pending. Answer correctness rates exclude missing completed probe answers and retain their unscored coverage. Sequence storage totals repeat state observations across checkpoints. Frozen lexical matching can miss paraphrases and alternative keys. One model and one repetition were selected. Current results describe this model, server, policy, prompt and interface combination; they do not establish general model capability or the cause of JSON-mode failures. The running collection and its frozen protocol were not modified.
