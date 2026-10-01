# Phase 2 todo

- [x] Add a per-account engine supervisor with private homes, ephemeral loopback ports, and process-only launch tokens.
- [x] Start enabled engines at gateway startup; reconcile account changes, stop disabled engines, and restart crashes with backoff.
- [x] Resolve account-to-home mappings from the account store and reject homes outside the managed homes directory.
- [x] Require a supported enforcing sandbox provider and fail closed when provider preflight fails.
- [x] Add mocked supervisor tests for the 20-account limit, restart, disable, and sandbox-unavailable behavior.
- [ ] Verify real sandbox enforcement and non-loopback isolation on a target host.
- [ ] Verify scheduled work continues without a browser and resumes after a real engine crash/restart.
