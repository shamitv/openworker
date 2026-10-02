# Execution checklist

## Before push

- [x] Complete corpus validates: 15 personas, 150 conversations, 195 turns.
- [x] Offline harness and affected regression suites pass.
- [x] P01/sentinel smoke executes ten conversations and thirteen turns.
- [x] Smoke routing, fresh-session, prompt-scope, account isolation, restart, and cleanup checks pass.
- [x] Model outcomes and any explicitly repeated smoke attempts recorded.
- [ ] Dataset/runbook and harness/tests committed in small batches.
- [ ] Normal push succeeds; remote revision matches tested source.

## After push

- [ ] Committed source deployed and hashes verified.
- [ ] Full sweep uses new accounts/stores independent of smoke.
- [ ] All 15 personas, 150 conversations, and 195 turns execute without skips or automatic reruns.
- [ ] Scope/isolation and restart checks pass.
- [ ] Metrics, environment, limitations, and representative synthetic evidence recorded.
- [ ] Sanitized output reviewed; private logs retained outside Git.
- [ ] Disposable roots, processes, and owned sandboxes removed; ports released.
- [ ] Results/report committed and pushed.
