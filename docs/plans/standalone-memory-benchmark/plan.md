# Standalone memory benchmark

## Goal

Measure how local models and instructions select, store, correct, forget and recall memory through a self-contained benchmark. Compare model behavior with instructions fixed, instruction wording within one policy, and the effects of different memory policies.

Build the future package under `benchmarks/memory`. It must work after copying that directory to another machine and installing its own dependencies. Runtime dependencies are Python 3.10+ and `httpx`; deterministic tests use `pytest`. The package calls the model endpoint directly and owns its memory store, operation loop and scorer.

## Planning delivery and current progress

Planning date: 2026-10-03 (Asia/Kolkata). Branch: `codex/standalone-memory-benchmark`, created from `feat/headless-vm-ui-serving` at `01f7ec8d89578ef98f6afec24033d78b600377a5`.

This delivery consists of planning documents. Every implementation phase starts **Not started**, with unchecked tasks. Creating and publishing these documents completes the planning deliverable; implementation, deterministic checks and live evidence are required to complete the phases.

The existing [hosted corpus](../../../tests/fixtures/memory/personas_v1.json) and [local-model findings](../../memory/persona-evaluations/v1/summary.md) are development references. The earlier benchmark scripts import OpenWorker components and do not establish standalone acceptance. Their results remain historical evidence under different protocols.

The approved local catalog was checked during planning on 2026-10-03 and advertised only `Ornith-1.5-35B-Uncensored-Q6_K`. This catalog check made no inference request. Recheck availability before any future live action.

## Architecture and evaluation tracks

Versioned corpus + policy/instruction assets + explicit model/interface selection → direct local HTTP runner → independent SQLite state → deterministic scorer → sanitized JSON and Markdown reports.

| Track | Starting information | Measurement |
|---|---|---|
| `write` | Exact conversation and a correctly prepared prior state for each scored checkpoint | Fact selection, operations, consent, scope, correction and forgetting |
| `read` | Identical manually prepared memories and fresh blind questions | Recall and use of available memory, independent of writing misses |
| `sequence` | Fresh owner memory followed by the scripted conversations and actual persisted state | Combined saving and fresh-chat recall, including accumulated failures |

Writing checkpoints receive their required prior state independently. Prepared-memory reading uses the same supplied records across model/prompt conditions. Sequence tests retain earlier misses; an absent correction or deletion prerequisite makes that control unexercised. Persona expected facts must never be seeded into sequence state to manufacture success. Prescribed peer controls are explicit fixture data and reported separately.

Every condition/track gets independent user/workspace namespaces and a fresh store. Write and read checkpoints each restore their own annotated starting state; only sequence conversations retain earlier writes. New conversations receive instructions, selected memory and the new question. Follow-up turns retain only their current conversation's messages. User/workspace IDs are abstract labels rather than hosted accounts or filesystem paths.

## Policies, instructions and interfaces

Compare two policies:

- **`conservative`:** based on the current guidance's explicit durability requirements. Explicit remember requests and clearly stated preferences for future chats are durable; ambiguous incidental context applies to the current chat.
- **`recurring`:** also saves stable, non-sensitive personal and recurring context expressed naturally, without requiring words such as “always” or “from now on.”

Both policies reject temporary details, preserve preference reasons, respect user/workspace scope, support correction and forgetting, and require the annotated consent conditions for consent-sensitive cases. Phase 1 freezes the exact policy text and expectations, including third-person and quoted information.

Each policy has three instruction variants: `baseline`, `rules` with clearer decision rules, and `examples` with rules and development examples. Variants within a policy must express the same requirements. Examples use development data only. Different policies have separate conformance labels; common outcomes such as storage and recall are also reported. A correctly conservative decision to avoid saving must not be presented as an instruction-following failure solely because the recurring policy would save it.

Both interfaces use the same memory records and operation implementation:

- **`json`:** the model returns a structured answer and operation list.
- **`native`:** the model invokes the operations as native tools and returns an answer.

Freeze operation semantics, argument schemas, state rendering and error handling before comparisons. Record interface effects separately from model, policy and wording effects. Gold answers, operation expectations, scoring aliases and conformance labels stay outside model-visible inputs.

Both interfaces follow one response lifecycle: execute an operation batch in listed order, return its results/errors, then request the next response. Answers accompanying operations are provisional. Only a valid response without operations supplies the scored final answer. The limit is six operation batches plus at most one final-answer request, all within the whole-turn deadline. Phase 1 freezes this protocol; Phase 3 implements and verifies adapter parity.

Storage precision/recall uses fixed, one-to-one fact/scope matching against each policy's annotations. In write checkpoints, unchanged prepared facts earn no new-write credit; full final state still determines correction, forgetting and preservation of required prior facts. Zero denominators produce `null`, and reports retain TP/FP/FN counts, denominators and coverage. Common behavioral targets remain the same across policies; valid conservative no-save decisions are scored through policy conformance.

## Review decisions — 2026-10-03

- **Interface lifecycle:** retain the shared dispatcher and results already required; add operation ordering, provisional answers, termination and round accounting so both interfaces answer after the same available results.
- **Scoring:** retain separate policy conformance and common outcomes; specify matching, changes versus prepared state, zero denominators and aggregation before collecting evidence.
- **Phase dependency:** test the dispatcher directly in Phase 2 and move JSON/native adapter parity acceptance to Phase 3, where adapters are implemented.

## Phase order

| Phase | Plan | Checklist | Status |
|---|---|---|---|
| 1. Contract, policies and corpus | [Plan](phase-01-contract-and-corpus/plan.md) | [Todo](phase-01-contract-and-corpus/todo.md) | [Status](phase-01-contract-and-corpus/status.md) |
| 2. Independent store and scorer | [Plan](phase-02-store-and-scoring/plan.md) | [Todo](phase-02-store-and-scoring/todo.md) | [Status](phase-02-store-and-scoring/status.md) |
| 3. Direct model runner | [Plan](phase-03-model-runner/plan.md) | [Todo](phase-03-model-runner/todo.md) | [Status](phase-03-model-runner/status.md) |
| 4. Experiment controls and limited smoke | [Plan](phase-04-experiments-and-smoke/plan.md) | [Todo](phase-04-experiments-and-smoke/todo.md) | [Status](phase-04-experiments-and-smoke/status.md) |
| 5. Held-out comparison and reporting | [Plan](phase-05-comparison-and-reporting/plan.md) | [Todo](phase-05-comparison-and-reporting/todo.md) | [Status](phase-05-comparison-and-reporting/status.md) |

Phases depend on their predecessors. A phase is complete only after its acceptance checks pass and its status records commands, results, environment, revisions/hashes and limitations. Model misses are results; missing infrastructure or evidence cannot be described as a passed gate.

## Planned CLI and experiment matrix

The future package provides `validate`, `smoke`, `run`, `replay` and `report`. These commands are planned interfaces, not implemented by this documentation delivery.

Live commands require `--base-url`, `--models` and a new `--output` directory. Full runs support dataset, policy, prompt, interface and track selection plus `--runs`. Use names `development`/`heldout`, `conservative`/`recurring`, `baseline`/`rules`/`examples`, `json`/`native` and `write`/`read`/`sequence` consistently in CLI arguments and reports.

The matrix is `model × policy × prompt variant × interface × persona × repetition`; report each evaluation track separately. Scheduling is sequential, reproducible and recorded. Compare models with all other factors fixed; compare wording within a model and policy; compare policy outcomes explicitly. A result describes a model/instruction combination and does not establish a prompt-independent model ranking.

The initial live gate uses **P01 only**, one model, one repetition, each policy's baseline instruction, both interfaces and all three tracks: **twelve track runs**. Smoke may use P01's prescribed synthetic peer controls; it must not schedule the other personas or held-out data. Any repeated smoke attempt requires fresh state and an explicit attempt record.

Phase 5 requires a later explicit request for the full sweep. Its default is all 15 held-out personas, both policies, three variants, both interfaces and all three tracks, once each. With one model this is 180 persona-condition repetitions and 540 track runs. `--runs` increases repetitions. One model supports policy/prompt comparisons and measured behavior; actual comparisons between models require at least two advertised IDs.

## Defaults, routing and evidence

| Setting | Default |
|---|---|
| Local endpoint | `http://10.42.0.202:8090/v1` |
| Initial model | `Ornith-1.5-35B-Uncensored-Q6_K`, subject to a fresh catalog check |
| Temperature / reasoning effort | `0` / `low` |
| Output limit | 2,048 tokens per request |
| Operation rounds | Six operation batches per turn, then at most one final-answer request |
| Whole-turn deadline | 180 seconds, shared across all requests/operations in that turn |
| Requests | Sequential, with no automatic retries or model fallback |
| Local cost | Unpriced; `null` |

Accept only explicit loopback/private-network endpoints and exact advertised model IDs. Reject public/OpenRouter routes, inference redirects and environment-derived proxy routing. Do not load `.env` or cloud credentials. Unsupported requested settings must produce a clear recorded failure rather than being silently removed or changed.

No hosted VM deployment, account provisioning, browser fixture, gateway or OpenShell is required. The standalone runner must not import OpenWorker providers, tools, memory code or prompt rendering. It generates no automatic titles or other auxiliary model calls.

Record actual model ID, available server metadata, effective settings, corpus/policy/instruction/schema/response-protocol/scorer hashes, request counts, available usage and latency. Missing usage and unavailable metadata remain explicit `null`; failed cases remain visible. Preserve raw diagnostics outside Git and publish reviewed synthetic evidence without credentials or authentication headers.

Replay rescoring uses captured evidence without inference and records its own revision/hash. Keep write, prepared-memory read and sequence scores separate. Report correction of current values separately from retirement of historical wording, and do not combine these results with earlier protocols.

## Delivery and completion

Commit the overview and five phase document sets in a small documentation commit, then normally push `codex/standalone-memory-benchmark` to `origin`. Never force-push. Subsequent implementation work should use small phase-oriented commits and update the phase's status only with actual evidence.

The planning delivery creates no benchmark implementation and authorizes no full live sweep. The initial implementation acceptance ends with the bounded Phase 4 smoke. Phase 5 remains pending until the full sweep is explicitly requested.
