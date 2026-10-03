# Standalone memory benchmark report

Collection status: **failed**. Infrastructure gate: **failed**.

Model misses, false recall, consent questions and format/tool failures are measured outcomes; they do not become infrastructure successes or disappear when a later response finishes.

Coverage: 12 track runs; 0 completed, 1 failed and 147 unexecuted checkpoints.

## Conditions and separate tracks

| Model | Policy | Prompt | Interface | Track | Policy conformance | Storage TP/FP/FN | Precision | Recall | Common fact recall | Common answers |
|---|---|---|---|---|---|---|---|---|---|---|
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | json | read | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | json | sequence | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | json | write | 0/1 | 0/0/0 | null | null | 0.000 | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | json | read | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | json | sequence | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | json | write | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | native | read | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | native | sequence | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | conservative | baseline | native | write | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | native | read | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | native | sequence | null (0/0) | 0/0/0 | null | null | null | null (0/0) |
| Ornith-1.5-35B-Uncensored-Q6_K | recurring | baseline | native | write | null (0/0) | 0/0/0 | null | null | null | null (0/0) |

## Requests, provenance and cleanup

Inference requests: 1; failed HTTP requests: 1; missing usage: 1.
Reported tokens: input=None, output=None; local cost=null.
Submitted settings: `{"max_tokens": 2048, "reasoning_effort": "low", "stream": false, "temperature": 0}`. Server-effective settings: `None` (unavailable unless reported).
Collection hash: `7115578ae74737065e0000d4ee9db0ae3c99268543e7e55bcad92a1506421869`. Scoring hash: `f5cfb1e2a52df159790ee589f2a977a255f66f19607856a8787f24b7994a323e`.
Cleanup: **complete**. Offline replay/report inference requests: 0.

## Case outcomes

| Policy | Prompt | Interface | Track | Persona | Case | Execution | Conformance | Tool errors | Format errors |
|---|---|---|---|---|---|---|---|---|---|
| conservative | baseline | json | read | P01 | C3 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | read | P01 | C5 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | read | P01 | C6 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | read | P01 | C7 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | read | P01 | C9 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | read | P01 | C10 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C1 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C2 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C3 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C4 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C5 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C6 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C7 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C8 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C9 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C10 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C11 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C12 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C13 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C14 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C15 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C16 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C17 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | sequence | P01 | C18 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C1 | api_error | False | 0 | 0 |
| conservative | baseline | json | write | P01 | C2 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C4 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C5 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C8 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C11 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C12 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C13 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C14 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C15 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C16 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C17 | unexecuted | None | 0 | 0 |
| conservative | baseline | json | write | P01 | C18 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | read | P01 | C3 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | read | P01 | C5 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | read | P01 | C6 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | read | P01 | C7 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | read | P01 | C9 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | read | P01 | C10 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C1 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C2 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C3 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C4 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C5 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C6 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C7 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C8 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C9 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C10 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C11 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C12 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C13 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C14 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C15 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C16 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C17 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | sequence | P01 | C18 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C1 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C2 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C4 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C5 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C8 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C11 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C12 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C13 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C14 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C15 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C16 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C17 | unexecuted | None | 0 | 0 |
| recurring | baseline | json | write | P01 | C18 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | read | P01 | C3 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | read | P01 | C5 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | read | P01 | C6 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | read | P01 | C7 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | read | P01 | C9 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | read | P01 | C10 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C1 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C2 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C3 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C4 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C5 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C6 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C7 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C8 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C9 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C10 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C11 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C12 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C13 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C14 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C15 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C16 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C17 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | sequence | P01 | C18 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C1 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C2 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C4 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C5 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C8 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C11 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C12 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C13 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C14 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C15 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C16 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C17 | unexecuted | None | 0 | 0 |
| conservative | baseline | native | write | P01 | C18 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | read | P01 | C3 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | read | P01 | C5 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | read | P01 | C6 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | read | P01 | C7 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | read | P01 | C9 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | read | P01 | C10 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C1 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C2 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C3 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C4 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C5 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C6 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C7 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C8 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C9 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C10 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C11 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C12 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C13 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C14 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C15 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C16 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C17 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | sequence | P01 | C18 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C1 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C2 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C4 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C5 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C8 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C11 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C12 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C13 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C14 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C15 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C16 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C17 | unexecuted | None | 0 | 0 |
| recurring | baseline | native | write | P01 | C18 | unexecuted | None | 0 | 0 |

This collection does not establish model or policy superiority. Phase 5 remains a separate explicit evaluation gate.
