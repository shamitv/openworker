# Phase 1 implementation review

Review date: 2026-10-03 (Asia/Kolkata)

Reviewed revision: `73ab572c9697f76fb5d0ea3b5af2cc164f4af92e` (`73ab572`,
`feat(memory-bench): add standalone Phase 1 package`), the Phase 1 implementation commit on
`codex/standalone-memory-benchmark`, based on `fbb1a6b`.

Re-checked after `3fd4de5` and against the working tree during Phase 2 development. Findings R1–R7
were raised against `73ab572` and all remain open: no asset file, corpus annotation or fixture changed
afterwards, and the matching logic was relocated unchanged. Phase 1 has since been recorded as
complete in [status.md](status.md) by `3fd4de5`; this review disputes that sign-off on R1.

Verdict: **Changes requested**

The package is well built. The contract and lifecycle invariants are enforced rather than asserted, the
test suite is adversarial rather than decorative, and the standalone guarantee is real rather than
asserted. Offline validation reports `valid`, and every test passes with `coworker` never imported.

The blocking problem is measurement precision, not correctness. The frozen matcher will award true
positives to model output that merely contains a common noun, and the corpus does not currently detect
that. R1 must be resolved before the Phase 4 smoke, because the plan forbids revising scoring after
inspecting held-out results. Phase 2 has already begun building the scorer on this matcher, so the
correction is cheaper now than after the smoke.

This review assesses the implementation of [the Phase 1 plan](plan.md). The corrections below are review
requests; this document does not implement them.

## Acceptance checklist

| Requirement | Result | Evidence and qualification |
|---|---|---|
| Self-contained package skeleton with independent dependency metadata | Pass | `standalone-memory-bench` 0.1.0, `requires-python >=3.10`, sole runtime dependency `httpx>=0.27,<1`, `src/` layout, console script. Resource reads go through `importlib.resources`, not the checkout or cwd. |
| Versioned record, scope and shared operation schemas | Pass | `contract.json` freezes five operations, result and error envelopes, and both response envelopes. Invariants are asserted: identity never appears in operation arguments, `memory_update` cannot change key or scope, `remember` requires scope, keys stay free-form. |
| Shared response lifecycle: ordered batches, provisional answers, six-round limit | Pass | Declarative traces cover final answer, ordered mixed batch, read-before-final, six batches then final, seventh batch refused, malformed envelope, deadline, empty final answer, unknown-operation feedback and invalid-argument feedback. Successful mutations survive sibling failures. |
| Independent conservative and recurring policies | Pass | Both reject temporary details, keep format and reason separate, require scope and consent conditions, and treat quoted and third-person statements as non-facts. The explicit-request consent rule is an explicit, documented clarification of historical guidance. |
| 15 development and 15 held-out personas with full annotations | Pass | Validation confirms 15 + 15, 270 conversations and 315 turns per split, 195 write / 90 read / 270 sequence checkpoints, 210 unique controls. Gold answers, aliases and expected state are absent from model-visible inputs. |
| Blind probes free of answers and aliases | Pass | Every enabled blind probe is checked against all 18 annotated facts per persona. Poisoning every `contract.gold_fields` entry leaves the projection byte-identical. No gold value appears in any prepared snapshot's `record.history`. |
| One-to-one matching, zero denominators, prior-state and duplicate handling | **Fail — R1, R2** | The documented rules are correct and the fixtures declare them, but the alias groups admit large numbers of unintended matches and no check detects sibling-fact alias overlap. |
| Corpus, policy, schema and protocol hashes recorded | Pass | `validate` emits 11 individual SHA-256 asset hashes plus a bundle hash (`ada6e044…ccc0b25`), using canonical JSON and LF-normalized UTF-8. |
| Validation requires neither OpenWorker nor network | Pass | Clean-venv run asserts `importlib.util.find_spec('coworker') is None`, guards `socket` in-process, and allow-lists installed distributions. Test root blocks `coworker` imports and socket use. |

## Review comments

### R1 [P1] Tighten value alias groups so unrelated model text cannot earn a true positive

Source: `matches_value` as AND across alias groups, now in
[matching.py:17](../../../../benchmarks/memory/src/memory_bench/matching.py#L17) (at `73ab572` it was
[validation.py:45](../../../../benchmarks/memory/src/memory_bench/validation.py#L45), relocated
unchanged during Phase 2 work);
[scoring.md:10](../../../../benchmarks/memory/src/memory_bench/assets/protocol/scoring.md) documents
the intended semantics. The alias data itself is
[generated in build_assets.py:149](../../../../benchmarks/memory/tools/build_assets.py#L149) from
historical `groups` values.

**Reproduction:** Several annotated facts reduce to a single group containing a single common noun:

```text
P03/style  value_alias_groups = [['set', 'sets']]      value = 'summaries by set'
  matches_value('I will set out the score')  -> True
P05/style  value_alias_groups = [['grams', 'gram']]    value = '…'
  matches_value('I will use grams')          -> True
```

Across the development split, 226 of 270 annotated facts (84%) are single-group with at least one
single-word alias. Restricted to `original`, `corrected`, `style` and `reason`, 38 of 60 have a one-word
alias somewhere.

**Impact:** The stated limitation in `scoring.md` is that the fixed matcher can miss valid paraphrases.
The dominant observed risk is the opposite. A model that writes "I will set out the score" is credited
with correctly storing `P03/style`, because "set" appears as a whole normalized phrase. Once Phase 5
reports precision and recall as headline numbers, an unknown share of true positives reflects the alias
sets rather than model behavior, and any policy, prompt or interface comparison is partly measuring the
corpus. The `write` track also seeds prepared snapshots with these values, so the same looseness
propagates into unchanged-prior and duplicate detection. Two further items make this harder to notice
later: 47 facts across both splits carry a one-word alias, and the loosest classes are concentrated in
exactly the preference facts the benchmark is designed to measure.

**Requested correction:** Tighten any alias group whose members are single common nouns so that a group
requires the fact's distinguishing phrase rather than one ambiguous word. Where a legitimate paraphrase
needs a short form, retain it as an additional group member rather than as the group's sole content, so
the AND across groups still constrains the match. Preserve the existing `original` versus `corrected`
separation, which is already correct and covered.

**Regression expectation:** For every annotated fact, the loosened probes above no longer match. Each
fact retains at least one negative probe drawn from its own persona that must not match, and at least
one positive probe that does. The ten existing lifecycle fixtures, four native fixtures and 25 scoring
fixtures continue to validate unchanged, and `validate` still reports `valid` with updated asset and
bundle hashes.

### R2 [P2] Check alias disjointness across all sibling facts, not only original versus corrected

Source: [validation.py:141](../../../../benchmarks/memory/src/memory_bench/validation.py#L141)
enforces alias separation for `original` and `corrected` only. No equivalent check exists for any other
fact pair. Still present and unchanged in the current tree.

**Reproduction:** In the development split,
`matches_value(P07.reason.value, P07.style)` returns `True`. `P07/reason` is "I record settings first",
which satisfies `P07/style` groups `[['settings', 'setting'], ['before', 'first']]` via "settings" and
"first". This is the only such collision in either split.

**Impact:** Not currently exploitable, because `matches_record` also requires the record key to match, and
the two facts use distinct keys. It becomes exploitable as soon as an alias set is edited, and the
scoring specification already treats a correct value under the wrong fact key as a false positive. A
scorer implementing [scoring.md:3](../../../../benchmarks/memory/src/memory_bench/assets/protocol/scoring.md)
to spec would therefore have no corpus-level guarantee that sibling facts are separable.

**Requested correction:** Generalize the existing `original`/`corrected` overlap check so that no
annotated fact's canonical value matches any other fact's alias groups within the same persona, subject
to the deliberate `original`/`corrected` correction pairing. Either resolve the `P07` collision in the
alias data or record it as an accepted, documented exception.

**Regression expectation:** Validation fails when a sibling fact's value is made to match another fact's
groups, and passes on the current corpus once `P07` is resolved or excepted. The 22 corpus-rejection
cases in `test_corpus.py` continue to pass.

### R3 [P2] Correct or define the `policy_difference` coverage tag

Source: [validation.py:19](../../../../benchmarks/memory/src/memory_bench/validation.py#L19) requires
`policy_difference` per persona; the tag is authored in
[build_assets.py](../../../../benchmarks/memory/tools/build_assets.py) and validated for presence only.

**Reproduction:** Per split, 60 conversations have different `conservative` and `recurring`
expectations, but only 15 carry the `policy_difference` tag. All 15 tagged cases are `C1`. The untagged
differences are `C2` and `C3`, which differ only in `retained_prior_facts` and
`expected_current_facts`, and `C4`, where conservative requires five additions where recurring requires
two:

```text
C4  required_additions  conservative=['original','style','reason','notebook','A']
                     recurring=['notebook','A']
```

**Impact:** `C4` is a genuine behavioral divergence, not propagation from `C1`, and it is the case where
the two policies are most distinguishable on a single explicit request. Because coverage is reported
per persona, downstream reports will understate policy-divergence coverage by roughly three times and
will not surface `C4`.

**Requested correction:** Either extend the tag to `C4`, or state in the corpus documentation that the
tag denotes the primary policy-divergence checkpoint only, and report differing-expectation counts
separately from tag counts.

**Regression expectation:** Every conversation whose policy expectations differ is either tagged or
covered by a documented rule, and validation enforces whichever definition is adopted. Reported coverage
counts remain reproducible for both splits.

Re-checked against the current tree: both splits still carry 15 tagged conversations, so this is
unchanged.

### R4 [P3] Distinguish owner-namespace records from `subject: owner` facts

Source: [validation.py:51](../../../../benchmarks/memory/src/memory_bench/validation.py#L51) maps every
non-peer subject to the owner namespace when matching.

**Reproduction:** Of 9,810 write snapshot records across both splits and policies, 5,490 are owned by the
owner namespace. Of those, 120 match no `subject: owner` fact; all 120 are `team_report_label`, the
`third_party_project` fact annotated `subject: third_party`.

**Impact:** The behavior is correct and intentional: `third_party_project` is durable project context
that the owner legitimately stores in their own workspace. The risk is that "owner records" in the
scorer and `subject == "owner"` are not the same set, and Phase 2 will filter on one of them.

**Requested correction:** Document the distinction at the scoring boundary so storage scoring selects
owner-namespace records while excluding `subject: peer` controls, and state explicitly that
`third_party_project` is scored as an owner save.

**Regression expectation:** The Phase 2 scorer fixture set covers a `third_party_project` save as a true
positive and a peer control as neither true positive nor false positive.

### R5 [P3] Note that `normalize` is fitted to development values

Source: [validation.py:39](../../../../benchmarks/memory/src/memory_bench/validation.py#L39) rewrites
`g/m` to `gsm` and splits `kHz` and `Hz` after digits. Now at
[matching.py:9](../../../../benchmarks/memory/src/memory_bench/matching.py#L9), relocated unchanged.

**Reproduction:** The special cases fire on exactly four development facts, `P02` and `P13` `original`
and `corrected`, and on zero held-out facts.

**Impact:** Harmless in effect, since the rules are inert on held-out data. Worth recording because the
split exists to keep held-out material out of tuning decisions, and a reader cannot currently tell
whether these rules were derived from development data or written for a general case.

**Requested correction:** Add a comment stating the origin and inertness, or drop the rules if no
held-out value requires them.

### R6 [P3] Relax the fixed asset-count assertion before Phase 4

Source: [test_fixtures_and_cli.py:90](../../../../benchmarks/memory/tests/test_fixtures_and_cli.py#L90)
asserts `len(asset_hashes()) == 11`.

**Impact:** Phase 4 adds six instruction variants. The assertion fails on arrival for a reason unrelated
to correctness. Confirmed still present in the current tree.

**Requested correction:** Assert the specific expected asset names rather than a count, or assert a
minimum count.

### R7 [P3] Clean up owned verification directories when portability checking fails

Source: [verify_portability.py:31](../../../../benchmarks/memory/tools/verify_portability.py#L31)
creates a temporary directory under `build/` with no cleanup on failure.

**Impact:** `build/` currently holds six abandoned verification directories, five of which cannot be read
back because a partially created environment denies access. They are correctly ignored by the repository
`.gitignore`, so they do not affect the commit, but they accumulate on every failed attempt.

**Requested correction:** Remove the owned directory in a `finally` block, or clean up previous
verification directories at startup.

Re-checked against the current tree: the Phase 2 edit to this script adds scorer provenance to the
report but still creates the temporary directory without cleanup.

## Executed verification

Date: 2026-10-03 (Asia/Kolkata). Environment: Windows, Python 3.14.2, using the repository `.venv`
(httpx 0.28.1, pytest 9.1.1). All runs executed from `benchmarks/memory` with `PYTHONPATH` set to the
package `src` directory. No inference request was made; the endpoint catalog was not contacted during
this review.

Run against the Phase 1 tree as committed in `73ab572`:

```sh
python -m memory_bench validate     # status "valid", inference_requests: 0
python -m pytest -q                 # 110 passed in 11.85s
```

Validation reported 15 personas, 270 conversations, 315 scripted turns and 210 controls per split, with
195 write, 90 read and 270 sequence checkpoints, 25 scoring fixtures, 10 lifecycle fixtures and 4 native
schema fixtures.

Re-run against the current working tree during Phase 2 development, which adds the store, dispatcher,
scorer, checkpoint execution and provenance modules:

```sh
python -m memory_bench validate     # status "valid", bundle_hash ada6e044…ccc0b25 (unchanged)
python -m pytest -q                 # 225 passed in 63.04s
```

The unchanged bundle hash confirms no asset, corpus, policy or fixture was modified after `73ab572`,
which is why R1–R3 and R6 still reproduce. The Phase 2 additions are outside this review's scope.

Additional read-only analysis over the validated corpus established: zero topic, fact-value and
namespace overlap between splits, with one shared message, the `C17` scripted deletion control; zero gold
values pre-revealed in any prepared `record.history`; `expected_current_facts` fully derivable from
additions, updates and deletions minus retained priors for every persona and policy; and every write
starting state equal to the preceding checkpoint's expected state.

The adversarial probes behind R1, R2 and R3 were run against the shipped assets and are reported as
observed behavior. They are not yet permanent regression tests. The missing scenarios are:

- No fact matches a negative probe derived from its own persona, and the `P03`, `P05` and `P07` cases
  above specifically.
- Validation rejects a corpus where a sibling fact's value matches another fact's alias groups.
- Coverage reporting accounts for every conversation whose policy expectations differ.

## Verification boundaries

These results establish the offline contract, corpus and fixture boundary only. They say nothing about
model behavior, and no live smoke has been run.

Portability was verified by `tools/verify_portability.py` using a local copy, a clean virtual environment
and an offline wheelhouse. That demonstrates the package builds, installs and validates independently of
the OpenWorker source tree, and that no OpenWorker distribution is required. It does not demonstrate the
plan's "copy that directory to another machine" requirement. The six verification directories under
`build/` were unreadable at review time, so the passing result of the most recent run could not be
independently confirmed from its report; the script's assertions and exit behavior were reviewed
instead. The acceptance evidence recorded in [status.md](status.md) and
[acceptance.json](acceptance.json) by `3fd4de5` was not independently re-derived here.

## Sign-off position

[status.md](status.md) records Phase 1 as **Complete** as of `3fd4de5`, with the bundle hash, per-asset
hashes, executed commands and environment. That record is accurate as far as it goes: the commands did
run, the hashes are correct, and the limitations paragraph is honest about fixed aliases missing
paraphrases.

Two qualifications apply. First, that status document's own limitations note — "Fixed aliases can miss
valid free-form keys/paraphrases" — describes the opposite failure mode from R1, and understates it. The
observed risk is over-matching, which corrupts reported precision rather than merely reducing recall.
Second, R1 is now load-bearing for Phase 2, which is being built directly on this matcher; `scoring.py`
and `matching.py` exist in the current tree and consume `matches_value` unchanged. Tightening the alias
groups now changes only the corpus and its hash, before any inference exists. After the Phase 4 smoke it
becomes a scoring revision that the plan requires to be reported as a separate experiment.

Phase 1 sign-off should be revisited for R1 and R2. R3–R7 can be dispositioned individually without
blocking later phases, though R6 should land before Phase 4 adds its instruction assets.