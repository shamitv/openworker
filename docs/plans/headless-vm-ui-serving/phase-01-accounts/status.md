# Phase 1 status

Status: In progress — implementation present; verification pending

Implementation evidence: [`accounts.py`](../../../../coworker/hosted/accounts.py) provides the SQLite account, home, audit, login-failure, and session tables; Argon2id password handling; throttling; password changes; and session revocation/expiry. [`run.py`](../../../../coworker/hosted/run.py) exposes account administration with hidden password prompts. [`app.py`](../../../../coworker/hosted/app.py) provides the browser auth routes, secure cookie, origin and CSRF checks, and session endpoint. Implemented in [bb6ed21](https://github.com/shamitv/openworker/commit/bb6ed21).

Existing automated coverage: [`test_hosted_web.py`](../../../../tests/test_hosted_web.py) contains account and gateway cases. The account case covers first-login password change state, password-change revocation, disabling an account, and a rejected bad-password attempt. The gateway case covers password change, logout revocation, and representative origin/CSRF enforcement. These tests are present; execution results are not recorded here.

Remaining acceptance checks: Run the existing tests and add coverage for actual lockout thresholds, idle/absolute expiry, concurrent changes, CLI behavior, and full two-account separation across user data. Explicit schema versioning and upgrade migrations are not implemented. See [`todo.md`](todo.md).

Known limitations: Account engines share the gateway operator's OS identity, so this application-level home separation does not contain a backend compromise. The feature currently supports no state migration from desktop installations.
