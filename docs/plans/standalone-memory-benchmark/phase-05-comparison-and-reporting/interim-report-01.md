# Interim held-out report

Snapshot: [progress-snapshot-07](progress-snapshot-07.json) at 2026-10-04 15:51 IST, 18.99h into attempt 03. This is interim, partial-coverage evidence for a collection that is still running. It is not Phase 5 acceptance, it does not close any checklist item, and it must not be combined with the historical hosted/model benchmarks.

## Authorization and provenance

Attempt 03 runs the full held-out matrix on the one model the endpoint advertised, `Ornith-1.5-35B-A3B-Q4_K_M`, after the user explicitly selected it on 2026-10-03. Fifteen held-out personas, both policies, three prompt variants, both interfaces and all three tracks, once each: 180 persona-condition repetitions, 540 track runs, 6,660 checkpoints, 7,740 scheduled user turns. Effective settings `max_tokens=12288`, `temperature=0`, `reasoning_effort=low`, `stream=false`; schedule hash `368722b0f71611dd51c61918ea08ad6335ebd91da18fb42e42d9052e0e58c310` was recorded before inference.

The frozen scorer and the frozen asset bundle are unchanged. The only source difference from the previously accepted package is one line in `client.py` raising `max_tokens` from 2048 to 12288; the collection hash for this attempt is `8a142dbd402db5c759bfc6f49b6f2236f7d387d252aa046584a986feed949e1c` against `4f417fd9…` before. Both identities were recomputed and matched during this snapshot, and 383 source tests pass. Full detail, including what could **not** be re-verified from the recording context, is in [offline-acceptance.json](offline-acceptance.json) under `attempt_03`.

No prompt, gold, lifecycle or scorer input was changed after held-out observations began. The running collection and its frozen protocol were not modified.

## Coverage so far

| Measure | Value |
|---|---|
| Checkpoints finalized | 3,392 of 6,660 (50.9%) |
| Track runs started | 276 of 540 |
| Conditions complete | 6 of 12 — all six `conservative`; `recurring` has just begun |
| Inference requests | 4,940 started, 4,939 finished |
| Requests with errors | 13, all `deadline` |
| Turn-deadline events | 13, at the 180s whole-turn cap |
| Collection errors | none |
| Expected finish | roughly 2026-10-05 10:00–11:00 IST, extrapolating 18.99h for the six completed conditions |

Per condition, at finalized checkpoints:

| Condition | complete | format_error | deadline |
|---|---:|---:|---:|
| `json/conservative/baseline` | 24 | 530 | 1 |
| `json/conservative/rules` | 20 | 532 | 3 |
| `json/conservative/examples` | 22 | 525 | 8 |
| `native/conservative/baseline` | 555 | 0 | 0 |
| `native/conservative/rules` | 554 | 0 | 1 |
| `native/conservative/examples` | 555 | 0 | 0 |
| `json/recurring/baseline` | 4 | 58 | 0 |

## Two different JSON pass rates, both correct

These measure different things and must never be quoted without their denominator:

- **20.5% of received JSON responses** passed the frozen adapter contract — 294 of 1,435, as of 11:15 IST ([interim-quality-analysis-01](interim-quality-analysis-01.md)). A turn may issue up to seven requests, and a response that parses can be an operation batch inside a turn that later fails on its final answer.
- **4.1% of finalized JSON checkpoints completed** — 70 of 1,727 at this snapshot. A checkpoint completes only when every scheduled turn returns a nonempty final answer inside the envelope.

By contrast, native finished 1,664 of 1,665 finalized checkpoints with a single deadline. The interface gap is total and one-directional.

## What the JSON failures actually contain

[Sampled JSON-interface response shapes](json-interface-response-shapes-01.md) answers this with a deterministic stratified sample of 150 failing turns, drawn without inspecting content, from the durable request journal.

A methodological finding came first: **a failing response is not in the turn transcript at all.** The adapter raises before the assistant message is appended, so `turn_finished` records hold only provisional messages from a turn that already parsed. Failing responses survive only in `request_finished` records. Any deliverable that quotes a representative JSON failure must read the request journal, not `checkpoints.jsonl`.

Of the 150 sampled failing responses:

| Shape | Count |
|---|---:|
| Parsed as a JSON object | 0 |
| Fenced JSON | 0 |
| Started with an envelope, then prose | 0 |
| Envelope embedded in prose | 13 |
| Prose using memory-operation vocabulary | 49 |
| Prose with no memory vocabulary | 88 |

None of the 150 sampled failures parsed as JSON or used a code fence. Thirteen contained a brace in prose; the shape heuristic does not establish whether those contained a usable embedded envelope.

The decisive check applies the frozen `score_answer` to the answer text those rejected turns actually delivered:

| Measure | Rejected `format_error` turns | Controls without a format error |
|---|---:|---:|
| Responses with an answer probe | 56 | 34 |
| Would have had valid probe format | 56 | 34 |
| Would have been fully correct | 50 | 23 |
| Would satisfy fields requiring `UNKNOWN` | 53 | 28 |
| Would have leaked an excluded fact | 3 | 1 |

The exploratory scorer marked 50 of 56 rejected answers and 23 of 34 control answers fully correct. These are unmatched samples with different case mixtures, so the counts do not establish superiority. The overall control sample also contains 11 timeouts without responses; those are excluded from scored-answer counts. The `UNKNOWN` measure checks fields expected to be unknown, rather than requiring the whole answer to be unknown. On the read track, 195 of 195 expected answer values were present in the sampled failing responses. One inspected failure was already in the required `field: value` probe format with correct values and no excluded fact, and failed because the adapter requires the entire response to be one JSON object.

The harness requests `response_format: json_object`. The capture does not establish whether the server applied a grammar or why prose was returned. JSON outcomes include envelope adherence and subsequent memory behavior. Format failures limit what the frozen scores reveal about memory behavior; the separately labelled text analysis provides additional descriptive evidence.

## Scoring caveats that survive completion

- Frozen lexical matching misses paraphrases and alternative keys. A separately identified exploratory diagnostic found matching expected values in the correct scope under unrecognized keys for 90 of 105 baseline and 85 of 103 rules write false negatives. That does not modify any frozen score.
- Presence of a value in prose is an upper bound, not correctness: a long answer can satisfy a fact incidentally, and the frozen answer measure additionally requires one `field: value` line per probe field with no excluded fact.
- Sequence storage totals repeat state observations across checkpoints.
- One model, one repetition, one server. This describes that combination and establishes no general capability, and no model-to-model comparison is possible with one advertised model.
- `reasoning_effort=low` was submitted but the server reports no effective settings, so it stays null rather than being described as applied. The responses do carry separate reasoning content.

## Remaining acceptance work

At this historical snapshot, remaining work was collection of the `recurring` conditions; final coverage accounting; offline replay; reviewed reports; cleanup; and a separate sanitized results commit. Review on 2026-10-05 located the exact rebuilt wheel and its existing clean-environment acceptance report, resolving the portability uncertainty recorded by the other context. See [review decisions](parallel-agent-review-01.md) for current collection and replay evidence.

Open checklist items in [todo.md](todo.md): 7, 8, 10, 11, 12, 14, 15.
