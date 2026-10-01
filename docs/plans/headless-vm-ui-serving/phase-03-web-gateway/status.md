# Phase 3 status

Status: In progress — implementation present; verification pending

Implementation evidence: [`hosted/app.py`](../../../../coworker/hosted/app.py) serves the login page and authenticated SPA, reports gateway health, checks browser origin/CSRF, and proxies account-scoped HTTP and WebSocket requests while stripping client credentials and injecting engine credentials. [`hosted/run.py`](../../../../coworker/hosted/run.py) restricts the listener to loopback. [`hostedWeb.ts`](../../../../surfaces/gui/src/hostedWeb.ts) and [`api.ts`](../../../../surfaces/gui/src/api.ts) initialize browser sessions, attach CSRF tokens, and redirect on expiry. The engine advertises `{"mode":"desktop","headless_web":true}`. Backend and GUI support were added in [bb6ed21](https://github.com/shamitv/openworker/commit/bb6ed21) and [3b002b9](https://github.com/shamitv/openworker/commit/3b002b9).

Existing automated coverage: The gateway case in [`test_hosted_web.py`](../../../../tests/test_hosted_web.py) uses fake upstream engines to cover unauthenticated access, account routing, token/actor header handling, CSRF and origin rejection, WebSocket routing, and absence of the engine token from the served page. It is one-process test coverage, not a two-browser deployment test. The test is present; execution results are not recorded here.

Remaining acceptance checks: Run the existing test, verify expired WebSocket sessions and remaining proxy edge cases, and exercise the gateway through a real HTTPS reverse proxy from two independent browsers. See [`todo.md`](todo.md).

Known limitations: TLS terminates at the configured reverse proxy; no public HTTPS deployment has been verified. The same OS-identity limitation described in the [overview](../plan.md) applies.
