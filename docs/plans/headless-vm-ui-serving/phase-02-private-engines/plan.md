# Phase 2 — Private engines and tool isolation

## Implementation

Supervise one loopback-only engine process per enabled user. Give each engine an app-owned home containing its own state and workspace root, an ephemeral port, and an in-memory launch token. Pass `COWORKER_STATE_DIR`, `OPENWORKER_BASE_DIR`, strict state locking, parent liveness, and an explicit enforcing sandbox provider. Start all enabled engines when the gateway starts; detect crashes and restart with bounded backoff. Stop engines and revoke sessions when accounts are disabled.

The gateway resolves the authenticated user's home from the account database and never accepts a home ID from the browser. Audit path-taking API operations for traversal and symlink escapes. Require every agent shell, file, git, and search tool to go through the sandbox provider. Refuse sessions when the provider is absent or unusable; never fall back to `direct` or `runner-local`.

## Acceptance

User A's API path, session ID, or WebSocket path cannot select user B's engine or files. No engine port accepts non-loopback traffic. A crashed engine recovers and its scheduled work resumes; an unavailable sandbox prevents agent tool work.

## Native Windows completion work

The selected target is native Windows. Keep the existing two sandbox OS accounts for network profiles, and give every hosted sandbox its own restricted logon token and private runtime directories. Grants must not accumulate on the shared account SID. Protect managed homes, process/thread/token/desktop/pipe DACLs, and file ownership; keep credentials and temp/cache/home separate. Failures must refuse tool work.

Use automated lifecycle/path/controller tests for implementation coverage, then run the opt-in native acceptance gate with real engines, real providers, and a local deterministic model. Mark the phase complete only after the live gate passes. If machine setup or host permissions block the gate, finish the code and record the blockers and unverified checks in `status.md`.
