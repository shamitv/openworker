# Response to Phase 1 implementation review

Response date: 2026-10-03 (Asia/Kolkata).

The [review](review.md) is preserved unchanged. Its demonstrated alias defects were
accepted, with targeted corrections applied to the working tree after Phase 2's
original acceptance. The corrections pass offline validation and **255 source
tests / 255 installed-wheel tests**, with zero inference requests. The new evidence
is in [review-acceptance.json](review-acceptance.json); both original phase acceptance
records remain unchanged.

## Disposition of R1–R7

### R1 — Accepted with a targeted scope

The P03 false positive reproduces under the original assets. The authoring tool now
requires summary wording together with sets for P03, ingredient wording together
with grams for P05, distance wording together with kilometres for P09, and complete
direction phrases for P12. P07 is addressed under R2. The generated development
corpus contains exactly these five alias-group changes. Distinctive short aliases,
including programming-language names and synthetic labels, are preserved. Matcher
semantics are unchanged: alternatives within a group are OR; groups are AND.
Adding a longer alternative alongside an ambiguous short alias would not fix it.

The review's 226/270 count is reproducible using raw whitespace-separated words,
but includes 210 deliberately distinctive synthetic control labels. It is not an
estimate of false-positive prevalence. The 38/60 development primary-fact count
also reproduces, but the presence of a short alternative in an AND-constrained
matcher does not itself establish a defect or a dominant failure mode.

Regressions reject the cited P03/P05 unrelated text and cover positive paraphrases
for all five formats. A P03 degraded prior value now enters write precision as an
FP rather than being treated as unchanged, and it is not classified as a duplicate
of the real format. Every annotated canonical value in both splits matches itself
and rejects all sibling canonical values. No claim is made that arbitrary model
text is semantically understood: aliases can still overmatch and miss paraphrases,
and the matcher does not interpret negation. These limits are now documented.

### R2 — Accepted; the demonstrated impact is stronger than stated

The original P07 reason, “I record settings first”, satisfied the format matcher.
This was already consequential in Phase 2: a reason-only answer earned both format
and reason recall credit, and that reason under the format key earned a storage TP.
Distinct canonical keys did not prevent those outcomes.

P07's format now requires commentary wording in addition to settings and ordering.
Reason-only recall passes the reason check and fails the format check; storing the
reason under the format key yields TP=0, FP=1, FN=1. A complete format-plus-reason
answer still passes. Validation now rejects canonical-value collisions between
every pair of sibling facts in both splits, including original/corrected pairs.
There is no exception for P07. The check concerns canonical sibling values; it
does not establish disjointness of every possible output string.

### R3 — Definition clarification accepted; the C4 rationale is rejected

`policy_difference` now explicitly means the primary policy divergence at C1,
from empty owner memory, and validation requires that tag on C1 only. Existing tags
and expectations are unchanged. Tests establish 15 tagged primary checkpoints
and 60 differing-expectation conversations per split, covering C1–C4.

C2/C3 carry forward C1's different states. C4 also inherits those different priors:
recurring already retains original/style/reason, while conservative must add them.
Both policies require the same explicitly requested facts and finish with the same
current state. Its different addition counts do not establish a separate policy
rule divergence. Documentation distinguishes tag coverage from counts of differing
expectation objects, without claiming downstream reports already undercounted.

### R4 — Documentation and explicit regression accepted

The existing Phase 2 implementation already selects owner records by `user_id`,
rather than requiring the fact annotation `subject: owner`. Documentation now
states this boundary and identifies authorized `third_party_project` facts as owner
saves. Added write and sequence regressions score a project fact alongside all
prescribed peer controls as TP=1, FP=0, FN=0. Peer-only records contribute neither
TP nor FP. No storage-selection behavior needed changing.

### R5 — Coverage clarification accepted; normalization retained

The frozen unit normalization is retained. Documentation and a code comment record
its current canonical corpus coverage: P02/P13 original/corrected development
values and no held-out canonical values. That observation does not establish when
or why the rules were authored, so the response does not assert an unverified
development-fitting history. Existing unit, decimal and phrase-boundary tests pass.

### R6 — Accepted in both affected tests

Both fixed eleven-asset assertions were replaced with required asset-name checks
that permit additions. Tests validate every returned SHA-256 and require scorer
provenance to contain the complete current asset map. A regression adds an instruction
asset to a temporary resource tree and verifies that the manifest includes it and
the scorer hash changes without changing source hashes.

### R7 — Accepted with diagnostic preservation and bounded cleanup

Failed verification now writes a report under `build/portability-reports` containing
the primary error and attempted commands, including captured stdout/stderr. It
then attempts to remove only the current invocation's disposable directory, after
checking its resolved parent is the package's build directory and its name uses
the owned verification prefix. Successful artifacts and older directories remain.

Regressions cover command failure, copying failure, a locked cleanup directory,
an outside target, and failure to write the diagnostic report. Cleanup errors are
reported without replacing the primary exception. If diagnostics cannot be saved,
the directory is retained; cleanup remains best effort under Windows locks. This
does not retroactively remove the review's earlier abandoned directories.

## Corrective acceptance

- Offline validation: `valid`; corpus sizes and the 25 scoring, 10 lifecycle and
  four native fixtures are unchanged.
- Source suite: **255 passed in 72.72 seconds**.
- Copied, built and installed wheel: **255 passed in 69.76 seconds**, with source
  overrides disabled, from an unrelated working directory, without OpenWorker.
- Regeneration is deterministic. Only the five agreed development alias groups
  changed; held-out content, gold expectations, snapshots and messages are unchanged.
  All 150 historical development conversations and 195 messages were preserved.
- Python 3.10 syntax parsing passed for 23 Python files; runtime testing used
  Python 3.14.2. Installation used the existing offline wheelhouse.

| Evidence | SHA-256 |
|---|---|
| Development corpus | `8cf19742ff549be73a6be7a8ae88e28b39a0da5129c916b1cfac4dcd5bcce199` |
| Bundle | `bfaff8d303291fea2152fb973e3e6b1231c3f7de472dec3bc114a0bde5457691` |
| Scorer | `ba79518e096b7ba1d43b3fc8a6347dc0aeb196fd9cf1e2c7debaf53b122dae9c` |
| Package tree | `da0e9b0dec882c66f1a8d98555635828ac1d85f4c23a7a0b3be2371a73430d33` |
| Installed wheel | `8cf9fe1896d162e38cde502fee627a7b4ca6f878f4733143ab9038138efd9448` |

The package tree manifest covers 37 files using raw file hashes; the acceptance
record specifies its hashing algorithm. Source and installed scorer provenance
agree. The successful detailed report remains at
`benchmarks/memory/build/portability-v6f3s6qd/report.json` (ignored).

These results amend the scoring/corpus acceptance of Phases 1 and 2; their original
records remain historical evidence. They establish neither model behavior nor a
second-machine portability result. No inference, commits or pushes were performed.

The review's post-smoke restriction needs qualification: the
[Phase 4 plan](../phase-04-experiments-and-smoke/plan.md) explicitly permits scorer
fixes and replay against saved evidence with recorded revisions. It forbids changing
gold expectations to manufacture a pass and keeps repeated live attempts separate.
Making the agreed corrections before inference avoids that complication.
