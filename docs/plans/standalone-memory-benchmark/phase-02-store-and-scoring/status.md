# Phase 2 status

Status: Complete

Implementation and acceptance date: 2026-10-03 (Asia/Kolkata). Dependency: Phase 1.

## Delivered

The independent [package](../../../../benchmarks/memory/README.md) now provides SQLite storage, persistent IDs, validated snapshot seeding, selected-memory projection and all five operations through one ordered dispatcher. Successful mutations commit independently; contract failures return explicit errors, while infrastructure failures are recorded and raised. Reads and mutations by ID can cross workspaces for the same abstract user and never return or mutate another user's records. Permission replies are exposed only by permission operations; policy violations remain observable.

Checkpoint helpers initialize independent prepared write/read stores and sequence stores with empty owner memory plus prescribed peer controls. Sequence reopening preserves actual accumulated state. Versioned JSON evidence retains context, before/after snapshots, per-message final answers, ordered operations/results and failures. C5's first-turn blind recall is scored separately from its later save.

The deterministic scorer implements frozen matching and one-to-one write deltas, duplicate false positives, prior-fact preservation, complete forgetting across keys/scopes/history, independent correction/current retirement/history retirement, strict labelled answers and whole-answer exclusions. Consent is checked chronologically against exact proposals. Forbidden saves remain visible even when later deleted. Recoverable tool errors remain reported, and infrastructure failures cannot produce successful no-op conformance. Common target presence, policy conformance, answer format/reason and control outcomes have separate counts and denominators.

Aggregation sums TP/FP/FN within condition/policy/track before division and retains case-level evidence, zero-denominator nulls, failed/unexecuted coverage and unexercised controls. Prepared/peer records earn no save credit. Missing snapshots remain unscorable.

The committed Phase 2 snapshot leaves all Phase 1 schema, corpus, policy, protocol and fixture assets unchanged. Their bundle hash remains `ada6e044e3c63177d82123d78f2092cc9b1f2a47269328f5b0a571f9927ccc0b`.

## Executed acceptance checks

From `benchmarks/memory`, with source pytest plugin autoload disabled:

```text
C:\work\openworker\.venv\Scripts\python.exe -m pytest -c pyproject.toml --confcutdir=tests --basetemp build/phase2-acceptance-tests-3ca134145b4a4026b9467c10d64f2f86 -q
C:\work\openworker\.venv\Scripts\python.exe tools/verify_portability.py --wheelhouse build/wheelhouse
```

- Source suite: **227 passed in 63.75s**.
- Copied, built and installed wheel: **227 passed in 60.59s**, with source-path overrides disabled and tests run from an unrelated working directory.
- All **25 frozen scoring fixtures** execute the scorer; the frozen aggregate fixture verifies numerators and denominators.
- Scripted decisions execute **2,220 corpus checkpoints** across 30 personas, both policies and write/read/sequence tracks, including sequence restarts. These are deterministic infrastructure checks without model inference or prompt selection.
- Additional cases cover mixed successful/failed batches, foreign/missing/very large IDs, persistence, row-ID churn, wrong keys/scopes, destructive changes, history-only/reverted mutations, multiple-copy forgetting, misplaced/late consent and failed/unexecuted evidence.
- Clean installation confirms OpenWorker is absent. Tests guard against OpenWorker imports and network access. Installation uses the local wheelhouse with `--no-index`; inference requests: **0**.
- Python 3.10 syntax parsing passes for **22** Python files. `git diff --check` passes.

The [acceptance record](acceptance.json) retains environment metadata, commands, all source/asset hashes and wheel evidence. The ignored detailed portability report is `benchmarks/memory/build/portability-3pkwhxx0/report.json`.

## Revisions and hashes

Implementation is committed in focused batches based on `3fd4de5c55b4e22bb856be78fad8e43947817547`:

- Shared matching: `778c489d798a05d7c688162a1aa5404697e5d045`.
- SQLite store and checkpoint evidence: `596311e56b6408874672ab183d1368699512522a`.
- Scorer, execution tests and portability evidence: `0e6ad24863f29312e758a8aefbf8a40ab35d5311`.

The hashes below identify the verified Phase 2 package snapshot. Newer review edits in the working tree were excluded from these commits; this acceptance evidence applies to the committed snapshot.

| Evidence | Value |
|---|---|
| Scorer revision | `standalone-memory-scorer-v1` |
| Scorer SHA-256 | `ed16d03f71bcc20ea1f9a773c2c6c4f6f7aed59fbb9dd9561149be335c9aa408` |
| Package source tree SHA-256 | `d467204c6b7ce6b76bed9a712ae249334d4bfc03961557bdd4aa659209abf9f3` |
| Installed wheel SHA-256 | `dd79eb65bb557bedc18724bb9576c1f816073f63ea7af48828cfaca9c51949e8` |

The scorer hash covers the LF-normalized implementation source hash map, frozen asset hashes and scorer revision using canonical JSON. It matches the installed wheel's scorer provenance. The package source tree hashes the canonical map of raw file-byte hashes for 36 package/license/source/test/tool/asset files, excluding build/cache artifacts. Full maps are in the acceptance record.

## Limits and subsequent phases

Runtime acceptance used Python 3.14.2 on Windows; Python 3.10 received a syntax check rather than runtime execution. Fixed aliases can miss valid free-form keys/paraphrases; unmatched records and raw snapshots remain inspectable. No model adapters, HTTP execution, live inference, model comparison or hosted deployment occurred. JSON/native execution parity belongs to Phase 3. Phases 3–5 remain pending.


## Corrective review acceptance — 2026-10-03

The preceding acceptance remains the historical record of the original implementation.
Accepted Phase 1 review feedback was subsequently applied to the working tree after
Phase 2 acceptance. The [review response](../phase-01-contract-and-corpus/review-response.md) documents each disposition;
[review-acceptance.json](../phase-01-contract-and-corpus/review-acceptance.json) records the new commands, environment and full hashes.
Both original acceptance.json files are preserved unchanged.

Targeted development format aliases were tightened for P03/P05/P07/P09/P12. Validation
now rejects canonical sibling-value collisions in either split and enforces C1 as
policy_difference's primary checkpoint. Scoring documentation clarifies storage
ownership, propagated policy expectations, unit coverage and lexical limitations.
Extensible asset checks and bounded failure cleanup with preserved diagnostics were added.
Only corpus/development.json and protocol/scoring.md changed among bundled assets;
held-out data, messages, snapshots, policy requirements and expected outcomes are unchanged.

Offline validation reports valid. The source suite passed **255 tests in 72.72s**;
the copied, built and installed wheel passed **255 tests in 69.76s** without OpenWorker,
source fallback or network access. Regeneration is deterministic; all 150 historical
conversations and 195 messages are preserved. Python 3.10 syntax parsing passed for
23 Python files. Inference requests: **0**. No commits or pushes were performed.

| Corrective evidence | SHA-256 |
|---|---|
| Development corpus | `8cf19742ff549be73a6be7a8ae88e28b39a0da5129c916b1cfac4dcd5bcce199` |
| Bundle | `bfaff8d303291fea2152fb973e3e6b1231c3f7de472dec3bc114a0bde5457691` |
| Scorer | `ba79518e096b7ba1d43b3fc8a6347dc0aeb196fd9cf1e2c7debaf53b122dae9c` |
| Package tree (37 raw-file hashes) | `da0e9b0dec882c66f1a8d98555635828ac1d85f4c23a7a0b3be2371a73430d33` |
| Installed wheel | `8cf9fe1896d162e38cde502fee627a7b4ca6f878f4733143ab9038138efd9448` |

The detailed ignored report is benchmarks/memory/build/portability-v6f3s6qd/report.json.
The new hashes identify the corrected working tree; earlier hash tables identify
historical revisions. Fixed aliases can still overmatch or miss paraphrases, sibling
checks cover canonical values only, and failure cleanup is best effort under locks.
Phases 1 and 2 have corrective acceptance; Phases 3–5 remain pending.
