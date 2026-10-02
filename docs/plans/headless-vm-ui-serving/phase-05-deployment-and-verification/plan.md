# Phase 5 — Deployment and verification

## Implementation

Document building the SPA, installing the Python package, setting the required sandbox provider, provisioning users, launching the gateway, and configuring a reference HTTPS reverse proxy with WebSocket forwarding. Document backup and restore of the gateway database and per-user homes, process logs, health checks, and resource sizing for 20 resident engines. The gateway and every engine listen only on loopback.

Run end-to-end tests with two browsers and two accounts for sessions, secrets, inbox, approvals, artifacts, files, WebSockets, and account revocation. Exercise CSRF, origin, login-throttling, sandbox-down, crash-restart, OAuth callback, and scheduled-task paths. Verify existing desktop authentication and Tauri behavior.

Phase 4 uses password-based app authentication. Its live external OAuth consent and callback acceptance was explicitly deferred here on 2026-10-02. Configure deployment-specific HTTPS callbacks and verify a real external provider consent/token exchange, routing to the owning account, and rejection of wrong-account, replayed, or expired flow state. Backend URL/routing tests alone do not establish this gate; record the provider and callback flow actually exercised.

## Acceptance

A fresh VM deployment can be followed from documentation without guessing configuration values beyond its domain, certificates, and sandbox setup. The multi-user security and desktop regression checks pass, with evidence recorded in `status.md`.
