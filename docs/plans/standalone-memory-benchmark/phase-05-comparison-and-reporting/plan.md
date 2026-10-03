# Phase 5 — Held-out comparison and reporting

## Execution gate

This phase remains pending until the full sweep is explicitly requested. Completion of the planning delivery or Phase 4 smoke does not authorize it. Before executing, verify Phase 4 acceptance and normal push, deploy/copy the committed standalone package, and verify its resource hashes and independent dependencies.

Recheck the approved endpoint's `/models` and use only explicitly selected advertised IDs. The planning catalog advertised one model. One available model supports policy/prompt comparisons and measured behavior; reporting a comparison between models requires at least two available model IDs. Do not invent, substitute or automatically obtain another model.

## Implementation and procedure

Default full coverage is 15 held-out personas, both policies, three variants per policy, both interfaces and all three tracks, once each. For one model this yields 180 persona-condition repetitions and 540 track runs. `--runs` increases repetitions and multiple selected model IDs multiply the same matrix. Record selected coverage before inference and retain every completed, failed or unexecuted item.

Use fresh stores independent of development and smoke runs. Preserve the frozen prompts/scoring rules; do not revise them after inspecting held-out results and then present the revised run as the same experiment. Any later revision creates a separately identified experiment with its own hashes and evidence.

Generate sanitized JSON and Markdown reports with case and condition results. Show write, prepared-memory read and sequence outcomes separately, including policy conformance, storage precision/recall, preference format/reason, scope, temporary saves, duplicates, correction, forgetting, consent and tool/format/API errors. Identify whether storage scores measure write changes or accumulated sequence state. Publish TP/FP/FN, denominators, zero-denominator nulls and coverage alongside fixed common behavioral outcomes. Missing sequence prerequisites are unexercised, not passes.

Present model comparisons with instructions/interface fixed; wording comparisons within a policy and model; and policy comparisons with their differing requirements stated. Do not combine interface effects into a prompt result or pool percentages with the historical hosted/model benchmarks. Include representative failures and distinguish current-value correction from historical-wording retirement.

Record model ID, available server/environment metadata, effective inference settings, request counts, available usage and latency. Missing usage or unknown metadata remains null; local cost is unpriced. Preserve collection, policy/prompt/corpus/schema/response-protocol and scorer provenance. Replay-based rescoring preserves the original collection revision and adds the replay's scorer revision/hash without inference.

Retain raw diagnostics privately, review published evidence for credentials/authentication headers, remove owned temporary stores/resources and verify cleanup. Test portability in a separate environment containing only the copied package and its dependencies; require validation and deterministic tests there, plus live endpoint access only when live execution is requested. Preserve unrelated files and services.

## Planned full command

After the execution gate is satisfied, from the independently installed package with a new output directory:

```bash
python -m memory_bench run \
  --base-url http://10.42.0.202:8090/v1 \
  --models Ornith-1.5-35B-Uncensored-Q6_K \
  --dataset heldout \
  --policies conservative recurring \
  --prompts baseline rules examples \
  --interfaces json native \
  --tracks write read sequence \
  --runs 1 \
  --output /tmp/memory-bench-heldout-attempt-01
```

This is a future interface and procedure; it is not a command to execute as part of the initial planning/smoke delivery.

## Acceptance

Every selected condition is accounted for, with no silent reruns or fallback. Unresolved infrastructure failures remain explicit and prevent a successful full gate; model misses and invalid outputs remain measured outcomes. Reports retain denominators, prerequisites, missing usage and limitations, including one-repetition uncertainty when applicable.

Portability verification passes without OpenWorker installed. Sanitized reports/results and the completed execution checklist are committed and normally pushed in a separate small batch. Record actual authorization, commands, versions, IDs/settings, revisions/hashes, coverage, findings, private-evidence location and cleanup in status.md before marking the phase complete.
