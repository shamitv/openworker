# Phase 5 status

Status: In progress — documentation present; deployment and regression verification pending

Implementation evidence: [`docs/headless-vm-ui.md`](../../../headless-vm-ui.md) documents Python and GUI setup, account commands, loopback gateway startup, Nginx TLS/WebSocket proxying, sandbox requirements, callback configuration, backups, logs, health, capacity planning, recovery, and limitations. The gateway exposes `/web/health`. The implementation and deployment guide were added in [bb6ed21](https://github.com/shamitv/openworker/commit/bb6ed21).

Existing automated coverage: The backend cases in [`test_hosted_web.py`](../../../../tests/test_hosted_web.py) cover mocked account, supervisor, callback, and gateway behavior as described in the earlier phase statuses. No test execution, fresh-VM installation, public-browser integration, or desktop/Tauri regression result is recorded in this plan.

Remaining acceptance checks: Follow the guide on a fresh VM; run two-browser, two-account security and product scenarios; verify a real sandbox, crash recovery, OAuth, and unattended scheduled work; and run desktop authentication/Tauri regressions. Record the commands, outcomes, and environment in this file after execution. See [`todo.md`](todo.md).

Known limitations: Capacity depends on the selected sandbox, models, and workload; no fixed VM sizing has been validated. Engines share the service OS identity. Hosted Codex subscription sign-in is unavailable, and OAuth providers need deployment-specific HTTPS callback configuration.
