# Phase 2 — Private engines and tool isolation

## Implementation

Supervise one loopback-only engine process per enabled user. Give each engine an app-owned home containing its own state and workspace root, an ephemeral port, and an in-memory launch token. Pass `COWORKER_STATE_DIR`, `OPENWORKER_BASE_DIR`, strict state locking, parent liveness, and an explicit enforcing sandbox provider. Start all enabled engines when the gateway starts; detect crashes and restart with bounded backoff. Stop engines and revoke sessions when accounts are disabled.

The gateway resolves the authenticated user's home from the account database and never accepts a home ID from the browser. Audit path-taking API operations for traversal and symlink escapes. Require every agent shell, file, git, and search tool to go through the sandbox provider. Refuse sessions when the provider is absent or unusable; never fall back to `direct` or `runner-local`.

## Acceptance

User A's API path, session ID, or WebSocket path cannot select user B's engine or files. No engine port accepts non-loopback traffic. A crashed engine recovers and its scheduled work resumes; an unavailable sandbox prevents agent tool work.
