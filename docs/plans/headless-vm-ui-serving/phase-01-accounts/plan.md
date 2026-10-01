# Phase 1 — Accounts and browser sessions

## Implementation

Add a central SQLite account database with stable user IDs, normalized unique usernames, password hashes, enabled state, forced-change state, user-to-home ownership, login failure counters, auditable account events, and revocable browser sessions. Use Argon2id for passwords. The `openworker-web user` CLI provisions, lists, disables, and resets accounts with interactive password input. New and reset accounts must change passwords on first login.

Version the database using SQLite `PRAGMA user_version`. Schema version 1 initializes a fresh store or adopts the compatible unversioned hosted schema without losing users, homes, sessions, failures, or audit events. Apply migrations and version changes atomically under an immediate transaction; reject incompatible schemas and versions newer than the application.

The gateway issues an opaque random cookie (`Secure`, `HttpOnly`, `SameSite=Strict`, host-only). Store only a hash of its value. Use a 12-hour idle and 7-day absolute expiry; logout, disable, and reset revoke sessions. Require an exact Origin and a per-session CSRF header on unsafe requests. Apply per-account and per-IP throttling with generic login failures and an audit trail. No public registration route exists.

## Acceptance

Provisioned users can log in and change passwords. Unknown, disabled, locked-out, expired, and revoked sessions fail. One user's cookie cannot select another home. Cookies never expose engine tokens.


Phase 1 verifies the database-to-session-to-home ownership boundary using independent gateway test clients. Complete product isolation and real browser/VM/sandbox verification belong to phases 2?5.
