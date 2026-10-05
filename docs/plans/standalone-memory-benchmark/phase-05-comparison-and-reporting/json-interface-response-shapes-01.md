# Sampled JSON-interface response shapes

Snapshot: 1791108973 unix. The capture was still running. This analysis made 0 inference requests. Aggregate counts, the sample definition and per-response rows are in [json-interface-response-shapes-01.json](json-interface-response-shapes-01.json).

This is interim, exploratory, partial-coverage evidence. It is not Phase 5 acceptance and it changes no frozen score.

## Where the failing response comes from

A failing response is not present in the turn transcript. The adapter raises before the assistant message is appended, so turn_finished holds only provisional messages of a turn that already parsed. Responses here are the last finished inference request of each sampled turn, read from the durable request journal. A representative failing JSON response therefore cannot be quoted from checkpoints.jsonl.

## Population

- 1735 finalized `json` turns, of which 1636 are `format_error` and 99 are not.
- 3383 of 6660 scheduled checkpoints are finalized.

## Sample

- 150 failing turns sampled from the 1636 `format_error` turns, plus 71 control turns without a format error.
- Stratification: prompt x track, round-robin personas inside each stratum, sorted deterministic order.
- Turns without a readable finished response: 0.

## Response shapes

| Shape | Sampled `format_error` | Control |
|---|---:|---:|
| `parses_as_json` | 0 | 60 |
| `fenced_json` | 0 | 0 |
| `json_prefix_then_prose` | 0 | 0 |
| `json_embedded_in_prose` | 13 | 0 |
| `prose_with_operation_vocabulary` | 49 | 0 |
| `prose_other` | 88 | 0 |
| `no_content_field` | 0 | 0 |
| `no_response_returned` | 0 | 11 |

## Exploratory value presence

Exploratory only. The frozen matcher is applied to raw assistant prose to count whether an expected value appears anywhere in the response. There is no one-to-one assignment between facts and spans, so these counts are an upper bound: a long answer can satisfy a fact incidentally, and paraphrase or an alternative wording is invisible to lexical matching. No rematching, no corrected recall and no frozen score is derived or changed.

| Measure | Sampled `format_error` | Control |
|---|---:|---:|
| Responses | 150 | 71 |
| Answer-probe values present | 206/219 | 85/111 |
| Responses with an answer expectation | 56/150 | 28/71 |
| Responses containing at least one answer value | 56/150 | 27/71 |
| Save-expectation values present | 199/273 | 91/250 |
| Responses with a save expectation | 62/150 | 47/71 |
| Present values with workspace evidence | 0 | 1 |
| Responses mentioning an excluded answer value | 4 | 2 |
| Responses explicitly declining to persist | 1 | 4 |
| Responses carrying separate reasoning content | 150 | 60 |

Answer-probe and save expectations are reported separately because most held-out checkpoints were never asked to save anything; a combined denominator would be dominated by turns with no expectation at all.

## What the rejected text would have scored

Exploratory only. The frozen score_answer function is applied to the answer text each turn actually delivered: the inner `answer` field for a JSON envelope, or the raw response for a rejected one. It is applied to turns the harness already rejected, to show what that text would have scored had it been delivered as an answer. The checkpoint's frozen score is unchanged, no response is re-executed and no memory operation is replayed. A rejected response that would have scored is evidence about delivery, not a corrected benchmark result.

| Measure | Sampled `format_error` | Control |
|---|---:|---:|
| Responses with an answer probe | 56 | 34 |
| Would have been fully correct | 50 | 23 |
| Would have had valid probe format | 56 | 34 |
| Would satisfy fields requiring UNKNOWN | 53 | 28 |
| Would have leaked an excluded fact | 3 | 1 |

A rejected response that is already in the required `field: value` probe format, with correct values and no excluded fact, failed only because the JSON adapter requires the whole response to be one JSON object. That is the clearest separation this sample offers between memory behaviour and envelope adherence.

| Track | Sampled responses | Answer values | Save values | Control responses | Answer values | Save values |
|---|---:|---:|---:|---:|---:|---:|
| `read` | 50 | 195/195 | 180/226 | 16 | 60/60 | 50/72 |
| `sequence` | 50 | 11/24 | 12/33 | 33 | 17/43 | 25/153 |
| `write` | 50 | 0/0 | 7/14 | 22 | 8/8 | 16/25 |

## Limits

- The failing population and the covered conditions are still growing: only 3383 of 6660 checkpoints are finalized and only the policies executed so far appear.
- Presence is not correctness. The frozen answer measure also requires one `field: value` line per probe field, exactly one value per field and no excluded fact, so a response can contain every expected value and still score zero. High presence counts, such as the read track above, bound what the response said, not what the frozen scorer awards.
- Write-track presence is naturally low because the turn asks a question rather than a restatement; a low count there is not evidence of a lost fact.
- Control turns are not all successful answers: 11 of 71 are `deadline` turns whose request returned nothing, reported as `no_response_returned` rather than as an answer shape.
- Presence counts are an unassigned upper bound, not a score, and are not comparable to frozen storage precision or recall.
- Controls use the same quota procedure but are not matched to failing turns. Empty or small strata can leave quotas unfilled. Differences between these samples do not establish superiority.
- Shapes describe this model, server, policy, prompt and interface combination at one repetition. They do not establish the cause of JSON-mode failure. The harness requests response_format: json_object; the capture does not establish whether the server applied a grammar.
