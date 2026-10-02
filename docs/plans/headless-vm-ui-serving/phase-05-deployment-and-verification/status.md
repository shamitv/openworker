# Phase 5 status

Status: In progress — documentation present; deployment and regression verification pending

Implementation evidence: [`docs/headless-vm-ui.md`](../../../headless-vm-ui.md) documents Python and GUI setup, account commands, loopback gateway startup, Nginx TLS/WebSocket proxying, sandbox requirements, callback configuration, backups, logs, health, capacity planning, recovery, and limitations. The gateway exposes `/web/health`. The implementation and deployment guide were added in [bb6ed21](https://github.com/shamitv/openworker/commit/bb6ed21).

Existing automated coverage: The backend cases in [`test_hosted_web.py`](../../../../tests/test_hosted_web.py) cover mocked account, supervisor, callback, and gateway behavior as described in the earlier phase statuses. Linux phases 2–4 now record real OpenShell/engine, HTTPS browser and password-based product gates in their status files. Phase 4 also records a clean full GUI regression run and authentication compatibility suites. These results can be reused as supporting evidence; a fresh installation, public-domain certificate integration and desktop/Tauri gate remain pending.

Remaining acceptance checks: Follow the guide on a fresh VM and public deployment; extend the verified two-browser, two-account scenarios to the full deployment checklist, including secrets/inbox/revocation and operational recovery; complete external OAuth consent/callback acceptance and desktop/Tauri regressions. Linux sandbox, crash recovery and unattended-work evidence is already recorded in Phase 2; password-based product acceptance is recorded in Phase 4. Record the commands, outcomes, and environment in this file after execution. See [`todo.md`](todo.md).

External OAuth consent and callback/token exchange acceptance was moved from Phase 4 to this phase by the agreed password-based scope on 2026-10-02. Public callback allow-list configuration and a real provider sign-in are still pending. Existing backend routing tests and Phase 4 password-session acceptance do not satisfy this gate.

Known limitations: Capacity depends on the selected sandbox, models, and workload; no fixed VM sizing has been validated. Engines share the service OS identity. Hosted Codex subscription sign-in is unavailable, and OAuth providers need deployment-specific HTTPS callback configuration.
