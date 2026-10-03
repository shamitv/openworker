# Smoke attempt 01 — retained infrastructure failure

Date: 2026-10-03 (Asia/Kolkata). Collection source: commit 2649a7d.

The advertised exact model was verified. The first inference request returned HTTP
500 before producing a model response because the server template rejects a second
system message. Collection stopped without retry or fallback: one failed checkpoint,
147 unexecuted checkpoints, one inference request, and no reported usage.

No operations ran. The owned SQLite store was removed; cleanup completed. Raw
request/response diagnostics remain outside Git in the explicitly labelled attempt
01 output. The JSON and Markdown here were reviewed as synthetic, sanitized evidence.

This failed attempt remains preserved. The request-assembly correction places the
unchanged shared policy/state and a separately headed interface envelope in one
initial system message. Any subsequent collection uses fresh state and a new attempt
label, after offline tests and installed-wheel acceptance pass again. No gold labels,
policy requirements, settings or model IDs were changed.
