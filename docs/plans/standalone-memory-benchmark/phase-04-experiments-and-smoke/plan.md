# Phase 4 — Experiment controls and limited live smoke

## Implementation

Implement the experiment matrix and reproducible sequential scheduling. Assign stable condition identifiers for model, policy, prompt variant, interface, persona and repetition. Record the requested and actual schedule. Each condition has an independent store and explicitly identified conversations/checkpoints.

Prepare and freeze six instruction assets: baseline, clearer rules and rules with development examples for each of the conservative and recurring policies. Within-policy variants must retain the same policy requirements. Freeze the corpus, contracts, rendering and scorer before held-out evaluation; record their hashes. Held-out cases must not be used to tune prompts or choose their examples.

Report writing, prepared-memory reading and sequence outcomes separately. Compare wording within a model/policy/interface condition. Compare policies explicitly, with policy-specific conformance and common outcome columns. Preserve model/interface interactions and case-level results rather than collapsing all conditions into one percentage.

After the offline suites pass, run one bounded live smoke using the explicitly supplied local endpoint and currently advertised `Ornith-1.5-35B-Uncensored-Q6_K`. Recheck `/models` before execution. The fixed schedule is:

| Factor | Smoke selection |
|---|---|
| Persona / split | P01 only / development |
| Policies | conservative and recurring |
| Prompt variant | baseline within each policy |
| Interfaces | json and native |
| Tracks | write, read and sequence |
| Repetitions | one |
| Total | twelve track runs |

P01's prescribed synthetic peer controls may be used for its namespace checks. Do not schedule other personas or held-out cases. The smoke validates routing, both interfaces, real operation/store evidence, injected state, fresh-chat boundaries, policy-specific scoring, error capture and cleanup. It does not establish superiority of a model, prompt or policy.

Treat missed automatic saves, false recall, consent questions and tool/format failures as measured model outcomes. Fix infrastructure or scorer defects without changing the gold expectations to manufacture a pass. Replay scorer-only fixes on saved evidence without inference and record both revisions. If another live smoke is needed, use fresh state, label it as a separate explicit attempt and retain the earlier findings.

Export reviewed synthetic JSON and a Markdown smoke report. Keep raw diagnostic logs outside Git, remove disposable stores/resources and record cleanup. Commit implementation/tests/sanitized smoke findings in small batches and push normally before any later held-out sweep. Completing Phase 4 does not authorize Phase 5 execution.

## Planned execution

From an independently installed package, with a new output directory:

```bash
python -m memory_bench validate
python -m pytest
python -m memory_bench smoke \
  --base-url http://10.42.0.202:8090/v1 \
  --models Ornith-1.5-35B-Uncensored-Q6_K \
  --output /tmp/memory-bench-smoke-attempt-01
```

These commands are future interfaces. Run tests from the standalone package's test root. Raw diagnostic/output directories stay outside the checkout unless reviewed evidence is deliberately exported.

## Acceptance

All deterministic suites pass, including scheduling/filtering and gold-leakage checks. The smoke accounts for all twelve selected track runs, with complete capture or explicit failure records. Routing, state/conversation isolation, actual operation execution, scoring and cleanup are verified. An explicit failure record satisfies coverage accounting, but unresolved infrastructure failures prevent the smoke gate from passing.

Record actual commands, package/environment versions, model/settings, collection/scoring revisions, hashes, model outcomes, repeated attempts and cleanup in status.md. Leave Phase 5 pending.
