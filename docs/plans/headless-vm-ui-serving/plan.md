# Headless VM browser UI

## Goal

Serve the full OpenWorker UI from a headless VM to up to 20 admin-provisioned users over HTTPS. Each account owns a private engine, state, keys, sessions, and workspace root. Authentication and home ownership live in an application database; no per-user OS accounts are required. Agent shell and file tools must run through an enforcing sandbox.

## Architecture

Browser → HTTPS reverse proxy → authenticated web gateway → user's loopback-only `openworker-server` → sandboxed tools. The gateway serves the built React SPA, owns account sessions, checks the user-to-home mapping, and proxies HTTP and WebSockets to the correct engine. The browser never receives an engine launch token. Engines stay running after logout so automations continue.

The gateway binds to loopback, checks the configured public origin on state-changing browser requests and browser WebSockets, and reads forwarded client addresses only from its loopback peer. The public API is cookie-authenticated with CSRF protection. Engine processes use separate state and workspace roots. Disable `direct` tool execution in this deployment and fail closed if the configured sandbox cannot start.

## Phase order

1. [Accounts and browser sessions](phase-01-accounts/plan.md)
2. [Private engines and tool isolation](phase-02-private-engines/plan.md)
3. [Web gateway and SPA](phase-03-web-gateway/plan.md)
4. [Headless product flows](phase-04-headless-flows/plan.md)
5. [Deployment and verification](phase-05-deployment-and-verification/plan.md)

Each phase has `plan.md`, `todo.md`, and `status.md`. A phase is complete only after its acceptance criteria and tests pass; its status file records the evidence.

## Current progress

[Phase 1 is complete](phase-01-accounts/status.md): transactional schema upgrades, browser account/session behavior, CLI administration, and cookie-to-home ownership are verified locally. On 2026-10-01, `tests/test_hosted_accounts.py` and `tests/test_hosted_web.py` passed together: **63 tests passed** on Windows 11 with Python 3.14.2 and SQLite 3.50.4. The account session cookie uses `SameSite=Strict`.

Implementation for phases 2–4 and phase 5 guidance in [`docs/headless-vm-ui.md`](../../headless-vm-ui.md) are present. Linux phases 2, 3 and password-based Phase 4 have passed their live gates; Phase 5 deployment/OAuth acceptance and the separate Windows sandbox live gate remain pending. See each phase's `status.md` for evidence and remaining checks.

Phase 2 code and automated coverage now include native Windows restricted-logon tool runners, protected homes, sanitized environments, persisted-path validation, and scheduled-failure reporting. Live acceptance remains blocked by canceled sandbox setup and window-station permissions on the selected PC; see [Phase 2 status](phase-02-private-engines/status.md) for the explicit gate and remaining checks.

Linux/OpenShell Phase 2 acceptance is complete on the supplied Ubuntu 26.04.1/Python 3.14.4 VM. With Docker 29.1.3 and OpenShell 0.0.116 installed, its real-sandbox/engine gate passed **2 tests in 43.50s** on 2026-10-02, proving concurrent tool isolation, loopback authentication, unattended scheduling, crash recovery, and disable/cleanup. Changes add private temporary/runtime directories, create read-only output mount sources before startup, and reject hosted artifact requests for unknown sessions. Linux uses the supported default `allowlist` network profile; unrestricted OpenShell networking remains unsupported. See [Phase 2 status](phase-02-private-engines/status.md) for evidence and the separate remaining Windows gate.

The final related VM regression suite passed **359 tests with 40 platform/opt-in skips in 45.97s**.

[Phase 3 is complete on Linux](phase-03-web-gateway/status.md): the hardened gateway and built SPA passed concurrent Chromium/Firefox HTTPS acceptance with two private OpenShell engines and the supplied real local LLM. UI-approved file writes, exact authenticated artifacts and VM contents, reload persistence, cross-account isolation, expiry redirects, continued peer work and browser token non-disclosure passed on 2026-10-02. Backend regressions passed (126 hosted and 129 compatibility tests), GUI units passed (489), the production build passed, and all 327 hermetic browser cases passed across runs. Temporary test deployment cleanup completed; public-domain certificate trust remains separate.

[Phase 4 is complete for password-based hosting on Linux](phase-04-headless-flows/status.md): Hosted VM controls, typed/recent workspaces, exact UI downloads, external workstation machine enrollment/reconnect, account isolation and independent password-session expiry passed the fresh Chromium/Alice and Firefox/Bob HTTPS gate in **approximately 1.2 minutes**, with no skips or automatic retries. Affected backend suites passed **302 tests**, GUI units **489**, the production build passed, and the clean full hermetic browser run passed **335 cases**. Private evidence is retained and disposable deployment/joiner cleanup completed. External OAuth consent and callback acceptance explicitly moves to [Phase 5](phase-05-deployment-and-verification/todo.md); public certificate trust remains pending.

## Public interfaces

- `openworker-web serve --spa DIR --data-dir DIR --public-origin https://HOST --sandbox-provider NAME` starts the gateway on loopback; `--host` and `--port` configure its local listener. Supported providers are `openshell`, `seatbelt`, and `windows`.
- `openworker-web user create|list|disable|reset-password USERNAME` administers accounts without putting passwords in command-line arguments.
- `/web/auth/login`, `/web/auth/session`, `/web/auth/logout`, and `/web/auth/password` manage cookie sessions. The gateway proxies `/v1/*` and `/ws/*` to the signed-in account's engine; the engine reports `{"mode":"desktop","headless_web":true}` from `/v1/capabilities`.
- `GET /web/artifacts/download?session=ID&path=PATH` streams an authenticated account-scoped artifact. Public account routes under `/h/{account-id}/` allow the engine's OAuth callbacks and `/j/{token}` join links; joined machines use `/h/{account-id}/ws/machine`.

## Acceptance

Two users can run concurrent sessions from different browsers without reading or controlling each other's sessions, inbox, secrets, artifacts, or paths. Invalid/expired sessions and cross-origin or CSRF requests fail. A missing sandbox prevents tool execution. Engines recover after failure and keep scheduled tasks running without an open browser. Desktop behavior continues to work.

## Decisions and limits

- Public HTTPS, built-in password-only accounts, admin provisioning, and no self-registration.
- Private homes with a separate engine process per user; account and authorization state is in the gateway database.
- One VM supports up to 20 enabled accounts in the first release. Engines remain resident for unattended work.
- No migration of existing desktop state in this feature.
- Hosted OpenAI Codex subscription sign-in is unavailable because its fixed localhost callback is not supported. Cloud Auth0 and third-party OAuth providers need to allow the deployment's public HTTPS callback URLs.
- A backend code-execution compromise could cross homes because engine processes share an OS identity. Supported API paths and agent tools are constrained in code and by the required sandbox; this is not process-level isolation.
