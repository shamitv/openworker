# Frozen scoring specification v1

The Phase 2 scorer matches current values only: normalized key under a frozen key
alias, accepted value groups, user, scope and workspace must all match. Each expected
fact and actual record earns at most one TP. Match deterministically in expected
fact order and ascending record ID. Extra copies and all unmatched actual facts are
FP; unmatched expected facts are FN. Aliases are private annotations; neither an LLM
judge nor a runtime semantic repair may add aliases after inference.

Normalization uses Unicode NFKC, case folding, underscores/punctuation as spaces,
whitespace collapse, retained decimal points and normalized gsm/Hz/kHz spacing.
A value matches when every alias group has at least one whole normalized phrase
present. Alternatives within a group are OR; groups are AND. Adding a longer
alternative alongside an ambiguous short alias does not constrain that short alias.
Exclusions use the same matcher. Fixed aliases can both overmatch unrelated text
and miss valid paraphrases; retain raw state and unmatched records for inspection
and report both limitations. Matching is lexical and does not interpret negation.
Unit normalization covers development P02/P13 original/corrected values and no
held-out canonical values; this coverage does not establish its authoring origin.

Write scores compare changes relative to the supplied prior snapshot. Match unchanged
prior facts first, ignoring ID churn; they earn no new-write credit. Additional copies
and key/value/scope changes enter the scored changes. Check deletions and retained prior
facts against the full final state. Sequence storage scores accumulated actual state.
Read tracks get identical prepared records across policies and measure recall and
unintended mutations; prepared records never earn save credit.
Storage scores select records whose user_id is the owner's namespace, independently
of the annotated subject. Authorized third_party_project facts are owner saves;
subject: third_party does not imply another storage owner. Prescribed peer controls earn no storage
credit and are reported separately; peer-only checkpoints have storage_scored=false.
Each scoring fixture explicitly identifies its write, read or sequence track.

Precision = TP/(TP+FP), recall = TP/(TP+FN); zero denominators are null. Aggregate counts
within each condition and track before division, preserving coverage and null cases.
Policy conformance and fixed common outcomes remain separate. A conservative empty
decision can conform while missing common automatic-storage targets.

The corpus coverage tag policy_difference identifies the primary divergence at
C1, from empty owner memory. C2/C3 inherit its different prior and current states.
C4 has different required-addition counts because of those priors, but both policies
require the same explicitly requested facts and finish with identical current state.
Tag counts are not counts of every differing policy-expectation object: each split
has 15 tagged primary checkpoints and 60 differing-expectation conversations (C1-C4).

Current correction uses value only. Strict old-value retirement checks value and history
separately; historical wording never makes a correct current value incorrect. Forgetting
checks every active copy, including historical copies and other keys/scopes. UNKNOWN is
valid only as the entire requested field, with no excluded control elsewhere in the answer.
Duplicate or missing labelled fields fail format checks. Correct positive fields cannot
conceal excluded workspace or forgotten values in other text.

Sequence correction/forgetting prerequisites inspect actual state before the control.
Absent prerequisites yield null/unexercised with a reason, never a pass. A failed or
unexecuted checkpoint cannot become a successful empty/no-op decision. Capture collection
and scorer hashes separately when replay rescoring is implemented.
