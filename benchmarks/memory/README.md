# Standalone memory benchmark

The package ships versioned contracts, policies, expanded synthetic corpora,
offline validation, an independent SQLite store, deterministic scoring, direct
local HTTP collection through JSON/native interfaces, and six instruction variants.
Only explicit `smoke` and `run` commands perform inference. Phase 5 evaluation is
a separate gate and is not run as part of installation or validation.

Copy this entire directory anywhere, then install and validate it independently:

```sh
python -m venv .venv
# Activate .venv using the command appropriate for your shell.
python -m pip install '.[test]'
python -m memory_bench validate
python -m pytest -c pyproject.toml --confcutdir=tests
```

Python 3.10+ is supported. `httpx` is the sole runtime dependency; validation,
storage and scoring use only the standard library. Tests require `pytest`. Validation and
tests use no network or OpenWorker installation. Package installation may require
an available package index or a local wheelhouse. `memory-bench validate` is also
available after installation. All runtime resources are read with
`importlib.resources`, independent of the current working directory.

## Frozen assets and inputs

`contract.json` describes current-fact records, five operation argument/result
schemas, JSON/native response envelopes and the common lifecycle. The separate
corpus schema and validator check shapes plus relational constraints. Schema
validation deliberately supports only the JSON Schema keywords used by these assets;
introducing another keyword requires extending and testing the validator.

Each record has a stable integer ID, abstract user/workspace namespaces, a global
or workspace scope, a free-form key, a current value and separate historical text.
Changing a key or scope requires forget plus remember. Same-user reads and mutations
by ID can address another workspace; that never changes the record's workspace.
Injection selects the current user's global and current-workspace facts only.

Policy baselines share scope, correction, forgetting and consent rules. Conservative
requires explicit durability; recurring also saves stable non-sensitive incidental
context. Explicit requests to remember sensitive facts grant consent. Incidental
sensitive facts require a permission question and an affirmative scripted answer.
Quoted/third-person information does not become a fact about the user. This consent
rule is a deliberate clarification of the historical guidance.

`build_model_input` explicitly projects instructions, abstract context, selected
memory and exact messages. It excludes gold facts, accepted aliases, expected state,
permission scripts and scoring labels. The runner returns the scripted consent
reply only when a permission operation occurs. Denied/default replies grant nothing.
All data is synthetic; no credentials, hosted accounts or filesystem workspaces are used.
`render_state` freezes the shared context/memory heading and canonical JSON rendering
for both adapters. A conversation's message indices are a schedule: the runner
must submit user turns individually, recording actual assistant/tool history before
each follow-up. The projection is not a preassembled HTTP request containing future turns.

## Corpus and track boundaries

Each split contains 15 personas, 270 fresh conversations and 315 scripted user turns.
Development P01–P15 retain all original 150 conversations and 195 user turns, with
eight additional cases per persona. Held-out H01–H15 use distinct activities, facts,
wording and control values. Held-out content is authored offline and is not used for
prompt selection or examples. The original hosted corpus is an authoring reference,
not a runtime resource or acceptance result.

- C1–C10 cover incidental learning, temporary details, explicit saving, scope,
  peer isolation, correction, forgetting and blind recall.
- C11–C13 cover sensitive consent granted, denied and explicitly granted.
- C14–C16 cover quoted statements, third-person facts and authorized project facts.
- C17 prepares duplicate copies for forgetting; C18 repeats an unchanged durable
  preference to distinguish preservation from new-write credit.

Each persona has 13 write checkpoints, six prepared-read checkpoints and 18 sequence
conversations. Write checkpoints run the full indicated conversation from their own
policy-specific starting snapshot. Prepared reads execute only the blind first
message (including C5, whose later message requests a write) from a common manually
prepared snapshot; they expect no mutations. Sequence runs execute all messages,
starting with empty owner memory and explicit peer-only fixture controls. Follow-ups
retain only their current conversation's messages. No sequence checkpoint is seeded
with expected owner facts. Annotated sequence states describe policy-conforming
outcomes; the scorer uses actual state and marks absent correction
or deletion prerequisites unexercised, never seed or manufacture them.
Current-state annotations describe the owner's progression; peer-only checkpoints
have `storage_scored=false` and report namespace/recall controls separately. Peer
fixtures never earn storage TP/FP credit. Every scoring fixture identifies its track.

All 25 scoring fixtures now execute the scorer. Additional deterministic tests run
the corpus's annotated decisions through SQLite and the dispatcher for both policies
and all three tracks in both splits. These synthetic scripted tests verify the
infrastructure; they do not measure a model. Lifecycle fixtures still validate
declarative traces. Native adapter execution parity is a Phase 3 gate.

## Store, dispatcher and scoring APIs

`MemoryStore(path)` supports `seed(records)`, `snapshot()`, `selected(user_id,
workspace_id)` and context-manager/close/reopen use. Seeding initializes an empty
store once, preserves supplied IDs and validates the entire snapshot before writing.
New IDs are monotonic, including after deletion and reopening. `selected` returns
the same projected records used by `build_model_input`.

`OperationDispatcher(store, OperationContext(user_id, workspace_id,
conversation_id), permission_reply=None)` supplies `dispatch(operation)` and
`dispatch_batch(operations)`. Its `events` property returns detached, ordered
operation/context/result evidence. A contract error returns the frozen error
envelope. SQLite/I/O failures are recorded as infrastructure errors and raised.
Permission calls expose the scripted reply only when invoked, default to denial,
and do not mutate memory. The dispatcher executes policy violations so they remain
measurable. Each successful mutation commits independently.

`create_checkpoint_store(path, persona, conversation, policy, track)` requires a
new path and chooses the annotated write/read snapshot or sequence peer controls.
Create a sequence store once; subsequent conversations share it. At a restart,
close it and use `reopen_sequence_store(path)`. The helpers never seed expected owner
facts into sequence state. The caller owns condition/persona/repetition file paths
and must use separate files for independent runs.

`checkpoint_evidence(...)` validates and copies a version-1 JSON-serializable
capture. It requires `condition`, `track`, `starting_records`, `final_records`,
`turns`, `status` and optional `errors`. Missing snapshots are `None`. Each turn is:

```python
{
    "message_index": 0,
    "answer": "the final answer for this user turn",  # None when unavailable
    "status": "complete",  # otherwise the recorded failure reason
    "operations": dispatcher.events,
}
```

Only final answers belong in `answer`; provisional text stays in the
runner's raw diagnostics. Each turn's operations contain only that turn's events.
Indices must be unique and ordered. A completed checkpoint must have a nonempty
completed final answer for every scheduled user turn. `status="unexecuted"` keeps
coverage visible without earning storage credit. C5's message 0 answer is scored
for recall while message 1 changes final storage.

`score_checkpoint(persona, conversation, policy, track, evidence)` returns detached
JSON data containing policy storage counts, full-state/preservation checks, scope,
duplicates, unnecessary/temporary saves, consent, correction/forgetting controls,
per-field answer matches, common outcomes, errors and the raw snapshots.
`aggregate_scores(case_scores)` groups by condition, policy and track, combining
personas/repetitions and summing counts before division. It retains every case,
null denominator, failed/unexecuted checkpoint and unexercised control. Aggregate
answer matches, common targets, consent and correction/forgetting have independent
denominators. No percentage averaging or cross-track pooling occurs.

Common `fact_presence` measures whether fixed behavioral targets are present in
full current state; it is a target-recall diagnostic, not new-save credit. Read
seeds receive no save credit. Write scores first remove unchanged prior facts
one-to-one, including accepted aliases and row-ID churn. History-only changes are
excluded from new-write scoring but included in read-mutation and retirement checks.
`unnecessary_saves` lists unmatched scored records, including duplicates and facts
under an incorrect key/scope; raw records explain these false positives.

Correction reports correct-current-value presence, obsolete-current retirement,
historical retirement and combined strict retirement separately. Policy conformance
permits historical explanations during correction, while requiring obsolete active
current copies to be corrected. Forgetting searches all owner keys/workspaces and
history. Absent pre-control prerequisites produce null/unexercised controls.
Forbidden saves and sensitive writes are inspected in the operation trace even if
later deleted. Consent must precede a successful write and match its exact
key/value/scope in the current user/workspace/conversation. An explicit sensitive
remember request needs no permission call; re-asking fails conformance. Unnecessary
questions in `not_required` cases are reported separately.

Committed snapshots remain scorable after execution failure, but failed cases
cannot pass policy conformance. Missing state evidence remains unscorable. Answers
require the requested labels exactly once, one per line, with literal `UNKNOWN`
for unavailable fields. Exclusions scan the entire answer, and preference format
and reason have separate matches.

## Matching and provenance

Private key aliases and value groups are frozen before inference. Matching uses
case/Unicode/punctuation normalization and whole phrases, preserving decimal and
unit distinctions. Format and reason are scored independently. Development reason
aliases were tightened from historical single-word matches so a generic probe's
topic cannot satisfy a reason. Unknown keys or unlisted paraphrases remain unmatched;
reports show that limitation and retain raw unmatched records.
Aliases can also overmatch unrelated text; the lexical matcher does not interpret
negation. Targeted development format aliases require summaries with sets,
ingredients with grams, commentary after settings, distances with kilometres,
and complete direction phrases. Canonical sibling values must remain separable.
Storage ownership means the owner's user namespace, rather than `subject: owner`;
authorized third-party project facts count as owner saves and peer controls do not.

`policy_difference` marks C1's primary policy divergence from empty owner state.
C2/C3 inherit different state; C4's different additions reflect those priors and
both policies reach the same explicit final state. Each split has 15 tagged
checkpoints and 60 conversations with differing policy-expectation objects.
Frozen unit normalization currently covers P02/P13's development context values
and no held-out canonical values; its authoring origin is not inferred from this.

`validate` prints counts, individual SHA-256 asset hashes and a bundle hash. JSON
hashes use sorted-key compact UTF-8 JSON; Markdown hashes use LF-normalized UTF-8.
`memory_bench.provenance.scorer_provenance()` returns the independent scorer revision,
SHA-256, implementation source hashes and frozen asset hashes. Source/text hashes
normalize line endings; JSON uses canonical encoding. Collection provenance remains
separate from each replay's scoring provenance.

To maintain the checked-in, fully expanded assets, the optional authoring tool accepts
an explicit historical source path:

```sh
python tools/build_assets.py --development-source /path/to/personas_v1.json
```

It has no default repository lookup and is never imported by the installed package.
Regeneration must preserve development conversations and pass validation/tests.

For a repeatable portability check, prepare an offline wheelhouse containing httpx,
pytest, setuptools, wheel and their dependencies, then run:

```sh
python tools/verify_portability.py --wheelhouse /path/to/wheelhouse
```

The helper copies this directory, creates a clean environment, builds and installs
the wheel with `--no-index`, runs guarded validation from an unrelated working
directory, and tests the installed wheel with the source-path override disabled.
Reports include the installed scorer hash. Owned verification environments remain
in the ignored `build` directory.
On failure, command diagnostics are saved under `build/portability-reports` before
the current invocation's disposable directory is removed. Cleanup failures are
reported alongside the original error; previous verification directories are retained.


## Collection, replay and reports

Live actions require an explicit local `--base-url`, exact advertised `--models`,
and a new `--output` directory. Use a loopback/private IP or localhost, with an
empty root path or `/v1`. Public endpoints, provider routes, redirects, inherited
credentials, environment proxies and automatic retries are refused. No `.env` is
loaded. Requests are sequential and have no auxiliary inference calls.

```sh
python -m memory_bench smoke --base-url http://10.42.0.202:8090/v1 --models Ornith-1.5-35B-Uncensored-Q6_K --output /tmp/memory-bench-smoke-attempt-01
python -m memory_bench run --base-url http://127.0.0.1:8000/v1 --models exact-advertised-id --output /tmp/memory-bench-development-01 --dataset development --policies conservative recurring --prompts baseline rules examples --interfaces json native --tracks write read sequence --runs 1
python -m memory_bench replay --input /tmp/memory-bench-smoke-attempt-01 --output /tmp/memory-bench-rescore-01
python -m memory_bench report --input /tmp/memory-bench-smoke-attempt-01 --output /tmp/memory-bench-report-01
```

`smoke` fixes development P01, both policies' baseline instructions, both interfaces,
all three tracks and one repetition: twelve track runs, 148 checkpoints and 172 user
turns. It accepts one advertised model and rejects coverage overrides. `run` requires
every factor selection explicitly; only `--runs` defaults to one. Both dataset
splits and all named policies/prompts/interfaces/tracks are supported. No full
held-out run is implied by implementing or completing a smoke.

Both adapters use the same ordered operation lifecycle: text accompanying operations
is provisional, operation errors are returned without repair, and only a nonempty
answer without operations is final. A turn permits six operation batches plus one
final-answer request and at most seven requests, with a 180-second total deadline.
Submitted wire settings are temperature=0, reasoning_effort=low, max_tokens=2048,
stream=false. Unsupported settings fail visibly; server-effective settings remain
null when the server does not report them. Successfully committed writes survive
later errors. Fresh conversations receive only current context, selected memory
and the new user message; only current-conversation follow-ups retain history.

Outputs contain manifest.json, append-only diagnostics.jsonl and checkpoints.jsonl,
results.json, and report.md. The manifest freezes source/asset hashes, requested and
actual schedules, settings, request usage/timings, coverage and cleanup. Interrupted
or failed runs retain partial evidence and explicit unexecuted checkpoints. Disposable
SQLite files are removed after snapshots are captured. Keep raw output outside Git.
Only reviewed results.json and report.md belong in published synthetic findings.

Reports keep policy conformance, common outcomes and the three tracks separate,
retain case evidence and denominators, and show null for unavailable usage/empty
ratios. Model/format/tool failures remain measured outcomes; unresolved routing,
configuration, API, store or cleanup failures produce a failed infrastructure gate.
A complete collection does not imply correct model answers or memory decisions.

`replay` and `report` perform zero inference. Replay preserves collection provenance
and appends scoring provenance, refusing a different corpus, contract or lifecycle.
Reports remove headers, raw requests/responses, private paths and raw error messages;
full diagnostics remain in the original private output. The six instruction variants
are bundled and hashed. Rules/examples retain their complete baseline policy;
examples have explicit development P02 sources and contain no held-out examples.
