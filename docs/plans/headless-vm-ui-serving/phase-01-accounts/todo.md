# Phase 1 todo

- [x] Add SQLite account, home ownership, audit-event, login-failure, and browser-session storage.
- [x] Add transactional schema versioning and compatible unversioned-database upgrades, with concurrent initialization and rollback coverage.
- [x] Add Argon2id password hashing, account/IP login throttling, and generic login failures.
- [x] Add create/list/disable/reset-password commands with hidden password prompts.
- [x] Add login, session, logout, and password-change endpoints with secure cookies, origin checks, and CSRF validation.
- [x] Add account tests for first-login password change, password-change revocation, and disable revocation.
- [x] Add and run tests for expiry, lockout thresholds, concurrent login/password changes, CLI behavior, and cookie-to-home ownership across independent clients.

Completion evidence and verification boundaries are recorded in [`status.md`](status.md).
