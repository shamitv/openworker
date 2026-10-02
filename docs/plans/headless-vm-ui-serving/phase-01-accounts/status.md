# Phase 1 status

Status: Complete ? account/session acceptance verified locally on 2026-10-01 (Asia/Calcutta)

## Implementation evidence

- [`accounts.py`](../../../../coworker/hosted/accounts.py) implements account/home ownership, Argon2id passwords, audit events, account/IP throttling, forced password changes, and revocable sessions with 12-hour idle and seven-day absolute expiry. Already-throttled attempts are audited without extending the throttle window.
- SQLite schema version 1 uses `PRAGMA user_version` and ordered migrations in a single immediate transaction. Fresh databases initialize, compatible unversioned databases retain all account data, and incompatible/newer schemas fail. Concurrent WAL initialization retries transient SQLite locking within a bounded timeout; migration failure rolls back both schema and version.
- [`run.py`](../../../../coworker/hosted/run.py) administers accounts using hidden password prompts and reports duplicate accounts, invalid input, and database failures as controlled CLI errors.
- [`app.py`](../../../../coworker/hosted/app.py) uses opaque `__Host-` cookies with `Secure`, `HttpOnly`, `SameSite=Strict`, and matching deletion attributes. Auth routes enforce exact Origin and per-session CSRF checks; session ownership comes from the database rather than client-selected identities or homes.

## Executed verification

Environment: Windows 11 (10.0.26200), repository `.venv`, Python 3.14.2, SQLite 3.50.4. Date: 2026-10-01 (Asia/Calcutta).

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hosted_accounts.py tests/test_hosted_web.py -q
```

Result: **63 passed in 12.50s**, with no failures.

[`test_hosted_accounts.py`](../../../../tests/test_hosted_accounts.py) provides 57 focused cases for fresh/legacy/versioned initialization, preserved legacy data and home files, rejected schemas, transactional rollback, concurrent startup, exact expiry and throttle boundaries, session touching/token hashing, revocation scope, synchronized login/password races, CLI lifecycle/errors, validation, and enabled-account capacity.

[`test_hosted_web.py`](../../../../tests/test_hosted_web.py) provides six backend cases, including two independent gateway clients sharing the account database. Phase 1 assertions cover forced-change gating, session cookie creation/deletion, generic login failures, missing/wrong Origin and CSRF, forged identity/home inputs, cross-account session/artifact IDs, logout/reset revocation, and absence of password hashes or engine tokens in browser responses. Existing mocked supervisor, callback/join, and HTTP/WebSocket tests also pass.

Acceptance: Provisioned users log in and change passwords; unknown, disabled, throttled, expired, and revoked authentication fails; database-owned home selection resists forged client identity; browser session cookies contain opaque tokens rather than engine credentials. All Phase 1 checklist items are complete.

## Verification boundaries and limitations

Gateway ownership tests use loopback test engines and independent test clients. Phase 1 alone did not establish real browser cookie enforcement, complete product-data isolation, target-VM HTTPS, real sandbox enforcement, unattended work or desktop regressions. Subsequent Linux evidence is recorded in phases 2–4. The revised Phase 5 covers temporary public Quick Tunnel deployment and remaining operational/desktop checks; external OAuth acceptance is outside this multi-phase plan. The separate Windows sandbox gate remains pending.

Engines share the gateway operator's OS identity, so application-level home separation does not contain a backend compromise. Existing unversioned hosted account databases upgrade automatically; desktop-state migration remains outside this feature.
