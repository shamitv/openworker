# Standalone memory benchmark

Phase 1 ships versioned contracts, policies, expanded synthetic corpora, expected
scoring fixtures and offline validation. Store, scoring execution, model adapters,
live commands and instruction variants belong to later phases. No inference is
performed by this package version.

Copy this entire directory anywhere, then install and validate it independently:

```sh
python -m venv .venv
# Activate .venv using the command appropriate for your shell.
python -m pip install '.[test]'
python -m memory_bench validate
python -m pytest -c pyproject.toml --confcutdir=tests
```

Python 3.10+ is supported. `httpx` is the sole runtime dependency; the Phase 1
validator uses only the standard library. Tests require `pytest`. Validation and
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
permission scripts and scoring labels. The runner will return the scripted consent
reply only when a permission operation occurs. Denied/default replies grant nothing.
All data is synthetic; no credentials, hosted accounts or filesystem workspaces are used.
`render_state` freezes the shared context/memory heading and canonical JSON rendering
for both future adapters. A conversation's message indices are a schedule: the runner
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
outcomes; the future runner/scorer must use actual state and mark absent correction
or deletion prerequisites unexercised, never seed or manufacture them.
Current-state annotations describe the owner's progression; peer-only checkpoints
have `storage_scored=false` and report namespace/recall controls separately. Peer
fixtures never earn storage TP/FP credit. Every scoring fixture identifies its track.

Scoring fixtures contain declarations of expected results, not a working scorer.
Lifecycle fixtures validate declarative traces, not a store or HTTP adapter. Native
fixtures freeze envelope/argument examples; execution parity is a Phase 3 gate.

## Matching and provenance

Private key aliases and value groups are frozen before inference. Matching uses
case/Unicode/punctuation normalization and whole phrases, preserving decimal and
unit distinctions. Format and reason are scored independently. Development reason
aliases were tightened from historical single-word matches so a generic probe's
topic cannot satisfy a reason. Unknown keys or unlisted paraphrases remain unmatched;
the future reports must show that limitation and retain raw unmatched records.

`validate` prints counts, individual SHA-256 asset hashes and a bundle hash. JSON
hashes use sorted-key compact UTF-8 JSON; Markdown hashes use LF-normalized UTF-8.
Collection and scorer revisions must remain separately identifiable in later phases.

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
Reports and owned verification environments remain in the ignored `build` directory.
