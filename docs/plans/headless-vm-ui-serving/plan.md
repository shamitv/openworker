# Headless VM browser UI

## Goal

Serve the full OpenWorker UI from a headless VM to up to 20 admin-provisioned users over HTTPS. Each account owns a private engine, state, keys, sessions, and workspace root. Authentication and home ownership live in an application database; no per-user OS accounts are required. Agent shell and file tools must run through an enforcing sandbox.

## Architecture

Browser → HTTPS reverse proxy → authenticated web gateway → user's loopback-only `openworker-server` → sandboxed tools. The gateway serves the built React SPA, owns account sessions, checks the user-to-home mapping, and proxies HTTP and WebSockets to the correct engine. The browser never receives an engine launch token. Engines stay running after logout so automations continue.

The gateway binds to loopback, accepts only the configured public origin, and trusts forwarded headers only from the local reverse proxy. The public API is cookie-authenticated with CSRF protection. Engine processes use separate state and workspace roots. Disable `direct` tool execution in this deployment and fail closed if the configured sandbox cannot start.

## Phase order

1. [Accounts and browser sessions](phase-01-accounts/plan.md)
2. [Private engines and tool isolation](phase-02-private-engines/plan.md)
3. [Web gateway and SPA](phase-03-web-gateway/plan.md)
4. [Headless product flows](phase-04-headless-flows/plan.md)
5. [Deployment and verification](phase-05-deployment-and-verification/plan.md)

Each phase has `plan.md`, `todo.md`, and `status.md`. A phase is complete only after its acceptance criteria and tests pass; its status file records the evidence.

## Public interfaces

- `openworker-web serve --spa DIR --data-dir DIR --public-origin https://HOST --sandbox-provider NAME` starts the gateway on loopback; `--host` and `--port` configure its local listener.
- `openworker-web user create|list|disable|reset-password USERNAME` administers accounts without putting passwords in command-line arguments.
- `/web/auth/login`, `/web/auth/session`, `/web/auth/logout`, and `/web/auth/password` manage cookie sessions. The gateway proxies `/v1/*` and `/ws/*` to the account's engine.
- The full-engine `/v1/capabilities` response gains a hosted-headless flag. Artifact downloads use an authenticated endpoint scoped to the account's workspace.

## Acceptance

Two users can run concurrent sessions from different browsers without reading or controlling each other's sessions, inbox, secrets, artifacts, or paths. Invalid/expired sessions and cross-origin or CSRF requests fail. A missing sandbox prevents tool execution. Engines recover after failure and keep scheduled tasks running without an open browser. Desktop behavior continues to work.

## Decisions and limits

- Public HTTPS, built-in password-only accounts, admin provisioning, and no self-registration.
- Private homes with a separate engine process per user; account and authorization state is in the gateway database.
- One VM supports up to 20 enabled accounts in the first release. Engines remain resident for unattended work.
- No migration of existing desktop state in this feature.
- A backend code-execution compromise could cross homes because engine processes share an OS identity. Supported API paths and agent tools are constrained in code and by the required sandbox; this is not process-level isolation.
