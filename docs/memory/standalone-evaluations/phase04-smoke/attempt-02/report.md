# Standalone memory benchmark report

Collection status: **complete**. Infrastructure gate: **passed**.

Model misses, false recall, consent questions and format/tool failures are measured outcomes; they do not become infrastructure successes or disappear when a later response finishes.

Coverage: 12 track runs; 78 completed, 70 failed and 0 unexecuted checkpoints.

## Conditions and separate tracks

| Model | Policy | Prompt | Interface | Track | Policy conformance | Storage TP/FP/FN | Precision | Recall | Common fact recall | Common answers |
|---|---|---|---|---|---|---|---|---|---|---|
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | json | read | 4/6 | 0/0/0 | null | null | null | 4/4 |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | json | sequence | 1/18 | 19/0/68 | 1.000 | 0.218 | 0.125 | 1/3 |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | json | write | 3/13 | 2/0/8 | 1.000 | 0.200 | 0.250 | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | json | read | 4/6 | 0/0/0 | null | null | null | 4/4 |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | json | sequence | 0/18 | 15/64/81 | 0.190 | 0.156 | 0.125 | 1/4 |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | json | write | 5/13 | 4/0/6 | 1.000 | 0.400 | 0.625 | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | native | read | 3/6 | 0/0/0 | null | null | null | 3/4 |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | native | sequence | 1/18 | 22/0/65 | 1.000 | 0.253 | 0.188 | 1/6 |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | native | write | 6/13 | 2/1/8 | 0.667 | 0.200 | 0.250 | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | native | read | 3/6 | 0/0/0 | null | null | null | 3/4 |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | native | sequence | 0/18 | 18/44/78 | 0.290 | 0.188 | 0.188 | 1/4 |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | native | write | 5/13 | 2/2/8 | 0.500 | 0.200 | 0.500 | 0/1 |

## Requests, provenance and cleanup

Inference requests: 198; failed HTTP requests: 0; missing usage: 0.
Reported tokens: input=414580, output=248903; local cost=null.
Submitted settings: `{"max_tokens": 2048, "reasoning_effort": "low", "stream": false, "temperature": 0}`. Server-effective settings: `None` (unavailable unless reported).
Collection hash: `e100e6ebc2ea0b92516a64f8ba5e9d5968ed6119fe2e6afb1853667081da1d65`. Scoring hash: `f5cfb1e2a52df159790ee589f2a977a255f66f19607856a8787f24b7994a323e`.
Cleanup: **complete**. Offline replay/report inference requests: 0.

## Case outcomes

| Policy | Prompt | Interface | Track | Persona | Case | Execution | Conformance | Tool errors | Format errors |
|---|---|---|---|---|---|---|---|---|---|
| conservative | baseline | json | read | P01 | C3 | complete | True | 0 | 0 |
| conservative | baseline | json | read | P01 | C5 | format_error | False | 0 | 2 |
| conservative | baseline | json | read | P01 | C6 | complete | True | 0 | 0 |
| conservative | baseline | json | read | P01 | C7 | complete | True | 0 | 0 |
| conservative | baseline | json | read | P01 | C9 | format_error | False | 0 | 2 |
| conservative | baseline | json | read | P01 | C10 | complete | True | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C1 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C2 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C3 | complete | True | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C4 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C5 | complete | False | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C6 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C7 | complete | False | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C8 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C9 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C10 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C11 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C12 | complete | False | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C13 | complete | False | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C14 | complete | False | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C15 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C16 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C17 | format_error | False | 0 | 2 |
| conservative | baseline | json | sequence | P01 | C18 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C1 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C2 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C4 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C5 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C8 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C11 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C12 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C13 | complete | True | 0 | 0 |
| conservative | baseline | json | write | P01 | C14 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C15 | format_error | False | 0 | 2 |
| conservative | baseline | json | write | P01 | C16 | complete | True | 1 | 0 |
| conservative | baseline | json | write | P01 | C17 | complete | True | 0 | 0 |
| conservative | baseline | json | write | P01 | C18 | format_error | False | 0 | 2 |
| recurring | baseline | json | read | P01 | C3 | complete | True | 0 | 0 |
| recurring | baseline | json | read | P01 | C5 | complete | True | 0 | 0 |
| recurring | baseline | json | read | P01 | C6 | complete | True | 0 | 0 |
| recurring | baseline | json | read | P01 | C7 | complete | True | 0 | 0 |
| recurring | baseline | json | read | P01 | C9 | format_error | False | 0 | 2 |
| recurring | baseline | json | read | P01 | C10 | format_error | False | 0 | 2 |
| recurring | baseline | json | sequence | P01 | C1 | format_error | False | 0 | 2 |
| recurring | baseline | json | sequence | P01 | C2 | format_error | False | 0 | 2 |
| recurring | baseline | json | sequence | P01 | C3 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C4 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C5 | format_error | False | 0 | 2 |
| recurring | baseline | json | sequence | P01 | C6 | format_error | False | 0 | 2 |
| recurring | baseline | json | sequence | P01 | C7 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C8 | format_error | False | 0 | 2 |
| recurring | baseline | json | sequence | P01 | C9 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C10 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C11 | format_error | False | 0 | 2 |
| recurring | baseline | json | sequence | P01 | C12 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C13 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C14 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C15 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C16 | complete | False | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C17 | format_error | False | 0 | 2 |
| recurring | baseline | json | sequence | P01 | C18 | format_error | False | 0 | 2 |
| recurring | baseline | json | write | P01 | C1 | format_error | False | 0 | 2 |
| recurring | baseline | json | write | P01 | C2 | format_error | False | 0 | 2 |
| recurring | baseline | json | write | P01 | C4 | format_error | False | 0 | 2 |
| recurring | baseline | json | write | P01 | C5 | format_error | False | 0 | 2 |
| recurring | baseline | json | write | P01 | C8 | complete | True | 0 | 0 |
| recurring | baseline | json | write | P01 | C11 | complete | False | 0 | 0 |
| recurring | baseline | json | write | P01 | C12 | format_error | False | 0 | 2 |
| recurring | baseline | json | write | P01 | C13 | complete | True | 0 | 0 |
| recurring | baseline | json | write | P01 | C14 | complete | True | 0 | 0 |
| recurring | baseline | json | write | P01 | C15 | complete | True | 0 | 0 |
| recurring | baseline | json | write | P01 | C16 | complete | True | 0 | 0 |
| recurring | baseline | json | write | P01 | C17 | format_error | False | 0 | 2 |
| recurring | baseline | json | write | P01 | C18 | format_error | False | 0 | 2 |
| conservative | baseline | native | read | P01 | C3 | complete | True | 0 | 0 |
| conservative | baseline | native | read | P01 | C5 | complete | False | 0 | 0 |
| conservative | baseline | native | read | P01 | C6 | complete | True | 0 | 0 |
| conservative | baseline | native | read | P01 | C7 | complete | True | 0 | 0 |
| conservative | baseline | native | read | P01 | C9 | format_error | False | 0 | 2 |
| conservative | baseline | native | read | P01 | C10 | format_error | False | 0 | 2 |
| conservative | baseline | native | sequence | P01 | C1 | complete | True | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C2 | format_error | False | 0 | 2 |
| conservative | baseline | native | sequence | P01 | C3 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C4 | format_error | False | 0 | 2 |
| conservative | baseline | native | sequence | P01 | C5 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C6 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C7 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C8 | format_error | False | 0 | 2 |
| conservative | baseline | native | sequence | P01 | C9 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C10 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C11 | format_error | False | 0 | 2 |
| conservative | baseline | native | sequence | P01 | C12 | format_error | False | 0 | 2 |
| conservative | baseline | native | sequence | P01 | C13 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C14 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C15 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C16 | complete | False | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C17 | format_error | False | 0 | 2 |
| conservative | baseline | native | sequence | P01 | C18 | format_error | False | 0 | 2 |
| conservative | baseline | native | write | P01 | C1 | complete | True | 0 | 0 |
| conservative | baseline | native | write | P01 | C2 | format_error | False | 0 | 2 |
| conservative | baseline | native | write | P01 | C4 | format_error | False | 0 | 2 |
| conservative | baseline | native | write | P01 | C5 | format_error | False | 0 | 2 |
| conservative | baseline | native | write | P01 | C8 | complete | True | 0 | 0 |
| conservative | baseline | native | write | P01 | C11 | format_error | False | 0 | 2 |
| conservative | baseline | native | write | P01 | C12 | format_error | False | 0 | 2 |
| conservative | baseline | native | write | P01 | C13 | complete | True | 0 | 0 |
| conservative | baseline | native | write | P01 | C14 | complete | True | 0 | 0 |
| conservative | baseline | native | write | P01 | C15 | complete | True | 0 | 0 |
| conservative | baseline | native | write | P01 | C16 | complete | False | 0 | 0 |
| conservative | baseline | native | write | P01 | C17 | complete | True | 0 | 0 |
| conservative | baseline | native | write | P01 | C18 | format_error | False | 0 | 2 |
| recurring | baseline | native | read | P01 | C3 | complete | True | 0 | 0 |
| recurring | baseline | native | read | P01 | C5 | format_error | False | 0 | 2 |
| recurring | baseline | native | read | P01 | C6 | complete | True | 0 | 0 |
| recurring | baseline | native | read | P01 | C7 | complete | True | 0 | 0 |
| recurring | baseline | native | read | P01 | C9 | format_error | False | 0 | 2 |
| recurring | baseline | native | read | P01 | C10 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C1 | format_error | False | 0 | 2 |
| recurring | baseline | native | sequence | P01 | C2 | format_error | False | 0 | 2 |
| recurring | baseline | native | sequence | P01 | C3 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C4 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C5 | format_error | False | 0 | 2 |
| recurring | baseline | native | sequence | P01 | C6 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C7 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C8 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C9 | format_error | False | 0 | 2 |
| recurring | baseline | native | sequence | P01 | C10 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C11 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C12 | format_error | False | 0 | 2 |
| recurring | baseline | native | sequence | P01 | C13 | format_error | False | 0 | 2 |
| recurring | baseline | native | sequence | P01 | C14 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C15 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C16 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C17 | complete | False | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C18 | complete | False | 0 | 0 |
| recurring | baseline | native | write | P01 | C1 | format_error | False | 0 | 2 |
| recurring | baseline | native | write | P01 | C2 | format_error | False | 0 | 2 |
| recurring | baseline | native | write | P01 | C4 | format_error | False | 0 | 2 |
| recurring | baseline | native | write | P01 | C5 | complete | False | 0 | 0 |
| recurring | baseline | native | write | P01 | C8 | format_error | False | 0 | 2 |
| recurring | baseline | native | write | P01 | C11 | complete | False | 0 | 0 |
| recurring | baseline | native | write | P01 | C12 | format_error | False | 0 | 2 |
| recurring | baseline | native | write | P01 | C13 | complete | True | 0 | 0 |
| recurring | baseline | native | write | P01 | C14 | complete | True | 0 | 0 |
| recurring | baseline | native | write | P01 | C15 | complete | True | 0 | 0 |
| recurring | baseline | native | write | P01 | C16 | complete | True | 0 | 0 |
| recurring | baseline | native | write | P01 | C17 | complete | True | 0 | 0 |
| recurring | baseline | native | write | P01 | C18 | format_error | False | 0 | 2 |

This collection does not establish model or policy superiority. Phase 5 remains a separate explicit evaluation gate.
