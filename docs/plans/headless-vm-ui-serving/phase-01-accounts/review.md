# Phase 1 acceptance review

Review date: 2026-10-02 (Asia/Calcutta)

Reviewed commit: `bec9c0adc306af039c6666e68940e3da079153f8` (`bec9c0a`)

Verdict: **Changes requested**

The existing Phase 1 suite passes all 63 tests. Additional isolated checks reproduce a forced-password-change bypass and two defects in browser authentication. R1 prevents acceptance of the requirement that provisioned and reset passwords must be replaced. R2 and R3 need input-handling and request-responsiveness corrections, respectively.

This review assesses the account/session requirements in [the Phase 1 plan](plan.md). The corrections below are review requests; this document does not implement them.

## Acceptance checklist

| Requirement | Result | Evidence and qualification |
|---|---|---|
| SQLite account storage, normalized usernames, stable IDs, unique homes | Pass | Account-store tests cover normalization, repeat initialization, persisted ownership, and enabled-account capacity. Schema constraints enforce unique usernames and homes. |
| Transactional schema initialization, legacy upgrades, rejection and rollback | Pass | Fresh, legacy, and versioned initialization, concurrent opens, preservation of legacy rows/home files, incompatible/newer schemas, and migration rollback are covered. |
| Argon2id passwords and hidden-password administration CLI | Pass | Password storage uses Argon2id. CLI tests cover create/list/disable/reset, hidden confirmation prompts, controlled errors, and rejection of password arguments. |
| New and reset accounts must replace their password | **Fail — R1** | Forced-change gating works, but submitting the same password as the replacement clears the requirement after both provisioning and reset. |
| Opaque hashed sessions and secure, host-only cookie attributes | Pass in backend tests | Session rows contain token hashes. Cookie assertions cover the `__Host-` name, `Secure`, `HttpOnly`, `SameSite=Strict`, root path, absent domain, and matching deletion attributes. Browser enforcement remains unverified. |
| Idle/absolute expiry and logout, reset, disable revocation | Pass | Tests cover exact 12-hour idle and seven-day absolute boundaries, session touching, revocation scope, and login/password-change races with administrative changes. |
| Exact Origin and per-session CSRF enforcement | Pass for covered requests | Login requires the configured Origin; authenticated unsafe requests require Origin and the session's CSRF token. Missing, wrong, and cross-account values are rejected in covered cases. |
| Account/IP throttling, generic login failures, audit events | **Partial — R2** | Thresholds, recovery, ordinary unknown/disabled/locked accounts, and audit events pass. Lone-surrogate credentials escape normal failure handling and return HTTP 500. |
| Cookie-to-home ownership and engine-token non-disclosure | Pass with independent clients and test engines | Gateway tests reject forged identity/home inputs and cross-account session/artifact IDs, and confirm database-owned routing and absence of engine tokens/password hashes from tested browser responses. |
| No public registration | Pass | No registration route is implemented; the gateway test confirms registration is unavailable. |

## Review comments

### R1 [P1] Reject an unchanged replacement password

Source: [accounts.py:569](../../../../coworker/hosted/accounts.py#L569) hashes the replacement; [accounts.py:598](../../../../coworker/hosted/accounts.py#L598) updates the password and clears `must_change`.

**Reproduction:** Provision an account with a valid initial password and log in. Submit `/web/auth/password` with the correct Origin and session CSRF token, setting both `current` and `new` to that initial password. The endpoint returns HTTP 200. Log in again with the same password: `/web/auth/session` reports `must_change=false`. The same sequence succeeds after an administrator resets the password.

**Impact:** The administrator-supplied credential remains usable for full application access. Rehashing it with a new salt does not replace the password, so the forced-change requirement can be bypassed.

**Requested correction:** Reject a replacement that matches the current password before changing stored credentials or clearing `must_change`. Keep the password, valid sessions, and forced-change state intact on rejection; preserve the existing transactional checks against concurrent reset, disable, logout, and password changes.

**Regression expectation:** For both a newly provisioned account and a reset account, an identical replacement returns the existing password-change failure response (HTTP 400). The account remains gated with `must_change=true`, its valid session remains usable for a retry, and the stored password is unchanged. A different valid replacement succeeds, revokes existing sessions, and permits login with `must_change=false`.

### R2 [P2] Return generic failures for malformed Unicode credentials

Source: [app.py:155](../../../../coworker/hosted/app.py#L155) calls authentication outside the input-error handler. [accounts.py:380](../../../../coworker/hosted/accounts.py#L380) and [accounts.py:407](../../../../coworker/hosted/accounts.py#L407) encode username/password values as UTF-8.

**Reproduction:** POST raw JSON to `/web/auth/login` with the correct Origin and an escaped lone surrogate (`\ud800`) in either the username or password field. For example:

```json
{"username":"\ud800","password":"initial secure password long enough"}
```

JSON decoding succeeds, but UTF-8 encoding raises `UnicodeEncodeError`. Both field variants returned HTTP 500 with `Internal Server Error` in the isolated gateway check.

**Impact:** An unauthenticated request can trigger an uncaught authentication exception and bypass the generic invalid-credentials response. These paths also fail before the usual login-failure accounting and audit handling completes.

**Requested correction:** Validate UTF-8 encodability or handle the encoding failure explicitly at the authentication boundary. Return the existing HTTP 401 `{"error":"invalid credentials"}` response without issuing a cookie. Keep expected input errors distinct from database or operational failures, and ensure malformed input does not crash failure/audit handling.

**Regression expectation:** Raw JSON containing a lone surrogate in either field returns the same generic HTTP 401 response as other invalid credentials, has no `Set-Cookie` header, creates no browser session, and raises no uncaught exception. Ordinary valid credentials continue to work.

### R3 [P2] Move blocking account work off the gateway event loop

Source: [app.py:155](../../../../coworker/hosted/app.py#L155) and [app.py:191](../../../../coworker/hosted/app.py#L191) invoke synchronous account operations from asynchronous handlers. [app.py:88](../../../../coworker/hosted/app.py#L88) also performs synchronous session lookup. The store performs Argon2 work and SQLite operations with a [10-second lock timeout](../../../../coworker/hosted/accounts.py#L186).

**Reproduction:** An isolated ASGI probe inserted a deliberate 300 ms delay into password verification while running a heartbeat scheduled every 10 ms on the same event loop. Login succeeded, but the maximum heartbeat gap was approximately 402 ms. This probe demonstrates blocking; it is not a production latency benchmark.

**Impact:** Password verification and database lock waits prevent the gateway loop from serving other accounts, health requests, and WebSocket activity. Login throttling does not make an individual unthrottled verification or database wait non-blocking.

**Requested correction:** Run blocking account operations from asynchronous request paths in bounded workers, including authentication, password changes, and session lookups. Bound expensive password work to avoid uncontrolled concurrent Argon2 memory use, and preserve the store's transactional rechecks and revocation semantics.

**Regression expectation:** With an account operation deliberately paused in a worker, a health request and an unrelated session request complete before it is released. Retain passing coverage for concurrent logins, competing password changes, reset/disable races, expiry, and revocation.

## Executed verification

Date: 2026-10-02 (Asia/Calcutta). Environment: Linux x86_64, Python 3.12.3, SQLite 3.45.1, using the existing `/tmp/openworker-test-venv` environment.

```sh
/tmp/openworker-test-venv/bin/python -m pytest tests/test_hosted_accounts.py tests/test_hosted_web.py -q
```

Result: **63 passed in 17.76 seconds**.

The successful run allowed the test engines to bind to loopback. An earlier restricted-sandbox attempt could not bind those sockets and was stopped; it is not a completed verification result.

The suite contains 57 account-store/CLI cases in [test_hosted_accounts.py](../../../../tests/test_hosted_accounts.py) and six backend cases in [test_hosted_web.py](../../../../tests/test_hosted_web.py). The targeted checks for R1–R3 used temporary account stores and an isolated gateway with engine startup replaced by a stub. Their reproduction cases are not yet permanent regression tests.

The missing regression scenarios are:

- Reject identical replacement passwords after provisioning and reset; accept a different valid password and complete forced change.
- Return generic HTTP 401 responses for lone-surrogate credentials without cookies, sessions, or uncaught exceptions.
- Keep health and unrelated session requests responsive while blocking account work is paused.

## Verification boundaries

Passing results establish the locally tested Phase 1 database/session/home-ownership boundary. Gateway ownership tests use independent clients and loopback test engines, rather than real browsers and deployed private engines.

Real-browser cookie enforcement, target-VM HTTPS, real sandbox enforcement, and complete product-data isolation remain acceptance work for later phases. R3 is an additional implementation concern; the Phase 1 plan does not specify a throughput or latency target.

The current passing suite does not resolve R1–R3. Phase 1 sign-off should wait for the requested corrections and their regression coverage.
