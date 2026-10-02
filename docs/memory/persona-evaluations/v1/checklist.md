# Execution checklist

## Before push

- [x] Complete corpus validates: 15 personas, 150 conversations, 195 turns.
- [x] Offline harness and affected regression suites pass.
- [x] P01/sentinel smoke executes ten conversations and thirteen turns.
- [x] Smoke routing, fresh-session, prompt-scope, account isolation, restart, and cleanup checks pass.
- [x] Model outcomes and any explicitly repeated smoke attempts recorded.
- [x] Dataset/runbook and harness/tests committed in small batches.
- [x] Normal push succeeds; remote revision matches tested source.

## After push

- [x] Committed source deployed and hashes verified.
- [x] Full sweep uses new accounts/stores independent of smoke.
- [x] All 15 personas, 150 conversations, and 195 turns execute without skips or automatic reruns.
- [x] Injection scope, account isolation, and eight restart checks pass; model scope/recall misses remain results.
- [x] Metrics, environment, limitations, and representative synthetic evidence recorded.
- [x] Sanitized output reviewed; private logs retained outside Git.
- [x] Disposable roots, processes, and owned sandboxes removed; ports released.
- [x] Results/report committed and pushed.

## Executed commands and evidence

```bash
python scripts/eval_memory_personas.py validate
python -m pytest tests/test_memory_persona_eval.py tests/test_memory.py \
  tests/test_memory_api.py tests/test_hosted_acceptance_helpers.py \
  tests/test_hosted_supervisor.py -q
```

Final affected-suite result: **120 passed in 6.53s**. The initial pre-push gate had 117 tests; later deterministic scoring checks raised the total to 120. No test uses external inference.

Live smoke and full commands used the VM interpreter `/home/ubuntu/openworker-phase2-20261002/.venv/bin/python`:

```bash
python scripts/eval_memory_personas.py smoke \
  --base-url http://10.42.0.202:8090/v1 \
  --models Ornith-1.5-35B-Uncensored-Q6_K \
  --root /home/ubuntu/.cache/openworker-persona-smoke-20261002-03 \
  --output /home/ubuntu/.cache/openworker-persona-smoke-results-20261002-03 \
  --spa surfaces/gui/dist

# After the collection source was committed and normally pushed:
python scripts/eval_memory_personas.py run \
  --base-url http://10.42.0.202:8090/v1 \
  --models Ornith-1.5-35B-Uncensored-Q6_K --runs 1 \
  --root /home/ubuntu/.cache/openworker-persona-full-20261002-01 \
  --output /home/ubuntu/.cache/openworker-persona-full-results-20261002-01 \
  --spa surfaces/gui/dist
```

The full run collected from pushed revision `9d01ebb7965253331fe7ae1cbb2864e30663ff1b` during 2026-10-02 16:47–18:14 UTC. Scorer-only improvements were tested and pushed separately, then replayed on saved evidence. Both revisions and hashes are preserved in [results.json](results.json).

| Gate | Evidence |
|---|---|
| Limited live smoke | [Three explicit attempts and findings](smoke.md); successful attempt: P01 only, ten conversations / thirteen turns, sentinel control |
| Full coverage | 150 unique session UUIDs / 195 turns; 15 profiles, one run each; 16 fresh accounts including sentinel |
| Infrastructure | All 150 routing/fresh-session/injection checks; all 15 peer exclusion and workspace-denial checks; eight restart batches |
| Model result | Automatic context save + recall 5/15; primary Grade 8 CBSE miss; explicit context saves 15/15; full details in [report](report.md) |
| Errors | Two tool failures, zero turn/API errors/timeouts; 13 non-memory calls; three visible consent questions |
| Cleanup | Ports 18453/18866/18867 released; owned stores/processes/sandboxes and temporary source/archive copies removed |
| Preserved resources | Existing OpenShell gateway on 17670 reachable; unrelated deployments untouched |
| Private evidence | VM smoke output directories and `/home/ubuntu/.cache/openworker-persona-full-results-20261002-01/private`; console logs retained outside Git |
| Publication | Small commits; ordinary pushes to `origin/feat/headless-vm-ui-serving`; no force-push |

The harness gate passed. Model misses, unsupported saved details, non-memory calls, and strict correction/forgetting failures are documented outcomes; memory guidance was unchanged. No OpenRouter requests were made.
