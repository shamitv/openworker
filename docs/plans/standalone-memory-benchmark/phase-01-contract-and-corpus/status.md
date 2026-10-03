# Phase 1 status

Status: Complete

Implementation and acceptance date: 2026-10-03 (Asia/Kolkata).

## Delivered

The independently installable [package](../../../../benchmarks/memory/README.md), version `0.1.0`, provides `python -m memory_bench validate`, bundled resources, frozen record/operation/result schemas, common state rendering and JSON/native response contracts. Runtime metadata declares Python 3.10+ and only `httpx`; tests use `pytest`.

Both baseline policies and the scoring specification are frozen. User-selected decisions: free-form keys with private fixed aliases; an explicit request to remember a sensitive fact grants consent. Incidental sensitive facts require an affirmative scripted permission response. Scope, correction, complete forgetting, quoted and third-person behavior are annotated independently.

| Split | Personas | Conversations | User turns | Write checkpoints | Read checkpoints | Sequence conversations |
|---|---:|---:|---:|---:|---:|---:|
| Development | 15 (P01–P15) | 270 | 315 | 195 | 90 | 270 |
| Held-out | 15 (H01–H15) | 270 | 315 | 195 | 90 | 270 |

There are 210 unique control values per split. All original 150 development conversations and 195 user messages were compared with the historical fixture and preserved exactly. Eight additional cases per persona cover sensitive consent, quoted/third-person information, authorized project facts, duplicate forgetting and unchanged preferences. Historical reason aliases were tightened during offline authoring because some generic probe topics matched the old single-word aliases.

Write checkpoints have independent policy-specific starting snapshots; prepared reads have one common snapshot and execute only the blind first message; sequences have empty owner state and explicit peer-only controls. Peer controls never earn storage credit. Gold annotations and permission scripts are excluded by the model-input projection. Message-index lists describe a schedule, not a request containing future user turns.

## Executed acceptance checks

From `benchmarks/memory`:

```text
python tools/build_assets.py --development-source ../../tests/fixtures/memory/personas_v1.json
python -m memory_bench validate
C:\work\openworker\.venv\Scripts\python.exe -m pytest -c pyproject.toml --confcutdir=tests --basetemp=build/test-temp-phase1-02 -q
python tools/verify_portability.py --wheelhouse build/wheelhouse
```

Source validation ran with the package's `src` directory on `PYTHONPATH`. Source tests passed, then the final portability check built and installed the wheel from a copied directory into a fresh virtual environment. Its tests used `-o pythonpath=` to disable the copied source fallback, and confirmed imports came from installed `site-packages`. The final installed-wheel suite passed **110 tests in 14.46 seconds**. OpenWorker was absent. Guarded validation and module-CLI validation both passed from an unrelated working directory with identical hashes. Tests block network connections and OpenWorker imports.

Offline checks validated both policies and all three track annotations, canonical alias matches, unique controls, namespace/scope boundaries, blind-question leakage, prepared prerequisites, preserved prior facts, empty sequence state, 25 declared scoring fixtures, 10 declarative lifecycle fixtures and four native schema fixtures. Python 3.10 syntax parsing passed for all 13 Python source/test/authoring files. Historical-message preservation passed separately. `git diff --check` passed.

Environment: Windows AMD64, Python **3.14.2**, `httpx` **0.28.1**, `pytest` **9.1.1**, setuptools **84.0.0**, wheel **0.48.0**, pip **25.3**. Declared dependency wheels were acquired separately; final build/install used a local wheelhouse and `--no-index`. Validation/tests made no network requests; **inference requests: 0**.

The final reproducible check is recorded in [acceptance.json](acceptance.json). The detailed local command report is retained at `benchmarks/memory/build/portability-wi87e653/report.json` (ignored). Earlier verification attempts are retained in their separately owned build directories; generic temporary/cache directory permission failures were resolved by using package-owned build paths.

## Revisions and hashes

Implementation commit: `73ab572c9697f76fb5d0ea3b5af2cc164f4af92e`, based on `fbb1a6bc67ba068c614079173edbea42f15139da`. The 27-file package source tree is identified by SHA-256 `528f44c733ad9c0d55e23fd779f6d339757fe2db35ee2f2bf7e116e0183f7b4b`. Its manifest excludes ignored build/cache/environment files and hashes LF-normalized UTF-8 file content in sorted relative-path order.

Bundle SHA-256: `ada6e044e3c63177d82123d78f2092cc9b1f2a47269328f5b0a571f9927ccc0b`.

Verified wheel SHA-256: `bc03c4ff2a41eb4f7af9700ea82e96a62849012b1974b050c729e01b86a607b9`.

| Asset | SHA-256 |
|---|---|
| Record/operation/response contract | `d991db4b1a3e6222fa0f1dbf9e70b53c18b305cb497ccb25c9cc5371e81227b5` |
| Corpus schema | `299acac7a3e5f3ab4654ed699408423a48dc36d9341d95d851d6ff87f4b860b9` |
| Development corpus | `f6e9e95d3a33fe0bcccb0fb573c06b788af381d63dbd52326646313556f96ac5` |
| Held-out corpus | `aa56e6ec4578af3b5d725c127938054cdc1b7cac7e38063c863d49d4c25e60f8` |
| Conservative baseline | `c84c13d62cf8cc8fdbdc95e16d9f4572d65423e2ace9daa76d2779e89db277dc` |
| Recurring baseline | `a1ebba539d5be75af87b9eca2a95338c8de85717e85245af640c389caf0632ff` |
| Operations/lifecycle/rendering specification | `dc96d63bb0f872d88f662b6d782d6df1f9ee345ec43690c9c88644d9eb314153` |
| Scoring specification | `67d41ae7e4b70b6cf2237f25f28d342c36daedaaaee6ab40b3aec57cc6d4890e` |
| Lifecycle examples | `a18989b8cd9d4d9226635f50fd742c7f997ee31fca7b9883cb4caf86990d4d1d` |
| Native schema examples | `c95e5c7798c7ac58287ada110169010be17058b6651bddea99bac6dd20d7e77f` |
| Scoring fixtures | `c1805b27d42b32cfb589901fa7083f5886684ca589b3d647449aa73401aa55e6` |

JSON asset hashes use canonical sorted-key compact UTF-8 JSON; Markdown asset hashes use LF-normalized UTF-8. The bundle hash hashes the canonical asset-hash map.

## Limits and subsequent phases

These are corpus/contract checks and declared expected-result fixtures. They do not establish store execution, a working scorer, HTTP routing or JSON/native execution parity. Those are Phase 2/3 gates. No held-out inference, prompt tuning or model comparison occurred. Fixed aliases can miss valid free-form keys/paraphrases; unmatched evidence must remain inspectable in later reports. Runtime acceptance used Python 3.14.2; Python 3.10 received a syntax check, not a runtime test. Phases 2–5 remain **Not started**.
