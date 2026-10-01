# Phase 4 status

Status: In progress — implementation present; verification pending

Implementation evidence: [`hosted/app.py`](../../../../coworker/hosted/app.py) supplies the authenticated artifact-download route and allowlisted account-scoped callback and machine WebSocket routes. [`api.ts`](../../../../surfaces/gui/src/api.ts) adapts artifact downloads and disables native reveal actions in hosted mode; [`hostedWeb.ts`](../../../../surfaces/gui/src/hostedWeb.ts) exposes the account workspace path. [`cloud.py`](../../../../coworker/cloud.py), [`mcp/oauth.py`](../../../../coworker/mcp/oauth.py), and [`remote/acceptor.py`](../../../../coworker/remote/acceptor.py) generate hosted callbacks and public join routes. Implemented across [bb6ed21](https://github.com/shamitv/openworker/commit/bb6ed21) and [3b002b9](https://github.com/shamitv/openworker/commit/3b002b9).

Existing automated coverage: [`test_hosted_web.py`](../../../../tests/test_hosted_web.py) checks artifact account scoping, account-specific callback routing, generated OAuth redirect URLs, and account-scoped join URL parsing/WebSocket URL construction. These are backend tests; they do not complete a real provider consent or external machine join. The tests are present; execution results are not recorded here.

Remaining acceptance checks: Exercise workspace selection, artifact download, provider consent and callback, and machine joining from a hosted browser and external machine. Add and run end-to-end hosted GUI and expired-flow coverage. See [`todo.md`](todo.md).

Known limitations: OpenAI Codex subscription sign-in is unavailable in hosted mode because it requires a fixed localhost callback. Cloud Auth0 and OAuth providers require public HTTPS callback allow-list configuration; see the [deployment guide](../../../headless-vm-ui.md).
