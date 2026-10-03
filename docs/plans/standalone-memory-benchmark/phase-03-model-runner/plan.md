# Phase 3 — Direct model runner and both interfaces

## Implementation

Implement a direct OpenAI-compatible HTTP client using `httpx`. Use the explicitly supplied local endpoint; verify exact requested model IDs through `/models` before inference. Do not use an SDK/provider router with implicit retries or fallback. Disable environment-derived proxy behavior and redirects. Reject public/OpenRouter routes and model-route aliases. Do not read `.env` or cloud credentials.

Supply the same policy/instruction assets, abstract user/workspace context and selected memory records to both interfaces. JSON mode requests a structured answer and operation list. Native mode exposes the same operations as tools. Both adapters invoke the Phase 2 dispatcher and use its results. Keep interface-specific envelopes separate from the policy text so interface effects can be reported.

Run a bounded loop with temperature 0, low reasoning effort, 2,048 output tokens and six operation rounds. Apply a 180-second deadline to the whole turn, including all requests and operations. Record effective settings; unsupported settings produce explicit failures. Do not silently repair responses, remove requested parameters, change model IDs or retry failed requests.

Every selected model/policy/prompt/interface/persona/repetition gets fresh state. Within a write track, each checkpoint uses its annotated prior state; a read track uses prepared records; a sequence track uses actual earlier writes. Fresh chats receive no preceding conversational messages. Follow-ups retain their own conversation history. Capture injected memory before the first user turn, request/response metadata, operations, results, answers and store snapshots.

Provide these independent CLI actions:

| Action | Behavior |
|---|---|
| `validate` | Validate bundled corpus, policy, prompt and operation assets offline |
| `smoke` | Execute the fixed Phase 4 development smoke with explicit endpoint/model/output |
| `run` | Execute explicitly selected matrix conditions, including configurable repetition count |
| `replay` | Rescore captured evidence without inference; preserve collection and new scoring provenance |
| `report` | Produce readable Markdown and sanitized JSON from captured/scored evidence without inference |

Live actions require explicit `--base-url`, `--models` and a new `--output` directory. Full runs support `--dataset`, `--policies`, `--prompts`, `--interfaces`, `--tracks` and `--runs`. Use the names in the [overview](../plan.md) consistently. Smoke has fixed persona/policy/variant/interface/track selections and one repetition; reject attempts to broaden its coverage or select multiple models.

Requests are sequential. Record all attempted requests, status/errors, model ID, available usage and timings, plus completed/failed/unexecuted coverage. A model or tool failure must remain visible even if a turn later finishes. Configuration, routing and prerequisite failures cannot produce a successful run report. Preserve partial evidence on interruption or failure, release owned resources, and never replace unavailable usage with zero.

## Acceptance

Mocked HTTP tests cover exact routing, catalog validation, redirect/public-route refusal, absence of credential/proxy inheritance, JSON and native operation handling, malformed responses, tool errors, failed requests, unsupported settings and whole-turn deadlines. Verify no automatic retry or fallback request occurs.

Test fresh stores and conversation boundaries, current-conversation follow-ups, injected-memory capture, operation persistence, consent fixtures, partial evidence, missing usage and inference-free replay/report actions. Tests must pass with no OpenWorker installed. A cloud key in the environment must not trigger a cloud request. No live inference is required for this phase.
