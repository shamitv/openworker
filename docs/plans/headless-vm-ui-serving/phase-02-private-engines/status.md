# Phase 2 status

Status: In progress — implementation present; verification pending

Implementation evidence: [`supervisor.py`](../../../../coworker/hosted/supervisor.py) starts one child engine per enabled account on loopback with a private home, ephemeral port, and process-environment token; reconciles disables and crashes; enforces the 20-account cap; validates home paths; and requires a supported enforcing sandbox provider to pass preflight. [`server/app.py`](../../../../coworker/server/app.py) and [`server/manager.py`](../../../../coworker/server/manager.py) apply hosted sandbox behavior in the engine. Implemented in [bb6ed21](https://github.com/shamitv/openworker/commit/bb6ed21).

Existing automated coverage: [`test_hosted_web.py`](../../../../tests/test_hosted_web.py) has a mocked supervisor test covering 20 engines, simulated crash and restart, account disable, and sandbox-unavailable behavior. It does not launch a real engine or provider. The test is present; execution results are not recorded here.

Remaining acceptance checks: Verify actual tool execution is contained by each supported sandbox, engine listeners are inaccessible off-host, and scheduled work continues without a browser and resumes after a real engine restart. See [`todo.md`](todo.md).

Known limitations: All child engines run under the gateway's OS identity. Linux deployment guidance recommends OpenShell; provider installation and enforcement have not been verified on a target VM.
