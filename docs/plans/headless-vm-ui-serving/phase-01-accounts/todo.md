# Phase 1 todo

- [x] Add SQLite account, home ownership, audit-event, login-failure, and browser-session storage.
- [ ] Add explicit schema versioning and upgrade migrations.
- [x] Add Argon2id password hashing, account/IP login throttling, and generic login failures.
- [x] Add create/list/disable/reset-password commands with hidden password prompts.
- [x] Add login, session, logout, and password-change endpoints with secure cookies, origin checks, and CSRF validation.
- [x] Add account tests for first-login password change, password-change revocation, and disable revocation.
- [ ] Add and run tests for expiry, lockout thresholds, concurrent login/password changes, CLI behavior, and broader cross-user ownership.
