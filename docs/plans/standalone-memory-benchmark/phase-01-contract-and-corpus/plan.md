# Phase 1 — Contract, policies and corpus

## Implementation

Create the standalone package skeleton with its own installation metadata, runtime/test dependencies and portable resource layout. Define a versioned record and operation contract before implementing the store or provider loop. User and workspace identities are abstract namespaces selected by the runner.

Records represent distinct current facts with stable IDs, fact keys, values and explicit global/workspace scope. Preserve preference format and its reason as independently scorable facts. Keep historical explanations separate from the current value so “updated from” wording does not automatically count as a current-value correction failure. The same record representation, operation names and argument semantics apply to JSON decisions and native tools.

Define remember, read, update, forget and permission-decision operations, including their successful and failed results. Freeze consent prerequisites, scope rules, missing-ID behavior and invalid-argument behavior. Model-visible contracts describe how to operate memory; they must not enumerate a case's expected answers or expose its gold annotations.

Write the `conservative` and `recurring` policy documents. The conservative policy retains the current guidance's explicit durability requirements. The recurring policy additionally saves stable, non-sensitive personal and recurring context expressed naturally. Both reject temporary details, preserve reasons, distinguish personal from workspace facts, support correction/forgetting, and follow the case's explicit consent conditions. Record policy conformance separately from common storage/recall outcomes.

Adapt the existing 15 synthetic personas into fully expanded development cases. The adapted data must ship inside the standalone package; runtime code must not read the repository's hosted fixture. Author 15 new held-out personas with different facts, wording and controls. Assign all conversations and related paraphrases from one persona to one split.

Each case contains exact messages, conversation boundaries, actor/workspace IDs, starting records, policy-specific expected changes, blind probes, aliases, exclusions, correction/deletion prerequisites and expected current state. Provide independently prepared prior states for write checkpoints and prepared records for read tests. Sequence cases start with empty owner memory and preserve actual model writes; explicitly identify any prescribed peer controls.

Cover implicit recurring context, explicit remembering, format preferences and reasons, temporary details, repetition, correction, forgetting, workspace switches, consent granted/denied, and third-person/quoted information. Define allowed outcomes where the policy genuinely allows more than one operation sequence. Expected state may be achieved by different valid operations; compare conformance and final state independently.

## Acceptance

Offline validation confirms 15 development and 15 held-out personas; complete annotations for both policies and three tracks; unique controls; valid namespaces/scopes; satisfiable write/read prerequisites; and no expected answers in blind probes or model-visible metadata.

Canonical facts match their own aliases. Positive, negative and malformed-output scoring fixtures are prepared before inference. Corpus, policy and operation-schema hashes are recorded. Validation requires neither OpenWorker nor network access.

No held-out prompt tuning or live inference is required to complete this phase.
