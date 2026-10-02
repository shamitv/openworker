# Phase 5 todo

- [x] Document package/SPA build, password account administration, loopback gateway startup, supervised Quick Tunnel exposure/restart, sandbox setup, backup, logs, health, capacity, and troubleshooting guidance; retain local Nginx fixture instructions.
- [x] Record current implementation evidence and outstanding verification/limitations in the phase status files.
- [x] Remove external OAuth acceptance from this multi-phase plan, superseding its earlier Phase 5 deferral while preserving existing implementation and historical evidence.
- [x] Add the supervised Linux launcher for tunnel URL discovery, loopback gateway startup, private logs and coupled child shutdown using existing account data; live verification remains part of the pending public gate.
- [ ] Verify launcher URL capture/readiness, startup failure/timeout, duplicate launch refusal, Ctrl+C/hangup cleanup and child exit handling while preserving existing account data.
- [ ] Follow the guide on a fresh Linux VM and verify temporary internet deployment through Cloudflare Quick Tunnel with the generated URL as the exact gateway public origin.
- [ ] Add and run a public-tunnel variant of the existing hosted browser gate with Chromium/Alice, Firefox/Bob and an external workstation joiner; require ordinary browser/CLI certificate verification, no fixture CA, no skipped scenarios and no automatic retries.
- [ ] Run two-browser, two-account scenarios for sessions, secrets, inbox, approvals, artifacts, files, WebSockets, and account revocation.
- [ ] Verify approved work, confined typed/recent workspaces, previews, exact browser downloads, persistence, account isolation and external machine join/reconnect through the public tunnel.
- [ ] Exercise real CSRF/origin rejection, login throttling/forwarded client identity, sandbox failure, crash recovery and scheduled-task behavior.
- [ ] Restart the tunnel, update the gateway origin with the same account data, sign in at the new hostname, and reconnect the external machine using a fresh URL and existing state; verify preserved data and machine ID, then reconnect with `openworker up`.
- [ ] Verify backup/restore, health and private logs; record idle/active resource measurements for the 20-engine target without claiming validated capacity from the two-account gate.
- [ ] Run existing desktop authentication and Tauri regression checks.
- [ ] Record versions, public hostname, commands, results and private evidence; stop and remove disposable deployment, tunnel and joiner state after verification.
