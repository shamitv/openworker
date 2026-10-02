# Phase 2 todo

- [x] Add a per-account engine supervisor with private homes, ephemeral loopback ports, and process-only launch tokens.
- [x] Start enabled engines at gateway startup; reconcile account changes, stop disabled engines, and restart crashes with backoff.
- [x] Resolve account-to-home mappings from the account store and reject homes outside the managed homes directory.
- [x] Require a supported enforcing sandbox provider and fail closed when provider preflight fails.
- [x] Add mocked supervisor tests for the 20-account limit, restart, disable, and sandbox-unavailable behavior.
- [x] Sanitize engine/runner environments and protect Windows managed homes with explicit ACLs.
- [x] Implement hosted Windows restricted-token launches with unique logon grants and private credential/home/cache/temp directories.
- [x] Protect bootstrap process/thread/token/desktop and pipe ownership; serialize ACL mutations and lease active runtime folders.
- [x] Revalidate persisted workspace/extra roots, artifacts, skills, credential descendants, and scheduled/manual workspace paths.
- [x] Record scheduled sandbox/construction failures as errors on the original run.
- [x] Add lifecycle, path-boundary, controller/API-ordering, and model-fixture automated coverage.
- [x] Add an opt-in live Windows gate using real engines/providers and a local fake model.
- [x] Document canceled setup, window-station denial, test boundaries, and the remaining live gate.
- [ ] Verify real sandbox enforcement and non-loopback isolation on a target host.
- [ ] Verify scheduled work continues without a browser and resumes after a real engine crash/restart.
- [ ] Verify real simultaneous account isolation, peer pipe/process denial, private credentials, read-only roots, logout, disable, and cleanup on Windows.
