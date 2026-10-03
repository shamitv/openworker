# Hosted memory personas, version 1

This evaluation uses **synthetic data** and existing password-based hosted accounts. It does not read real account histories, alter memory guidance, or use OpenRouter. The expanded corpus at `tests/fixtures/memory/personas_v1.json` contains all 15 profiles, exact prompts, aliases, scope expectations, and control prerequisites; this runbook and that file are sufficient context without earlier conversations.

## Execution order

1. Validate the corpus and run deterministic tests.
2. Run `smoke`: only P01 (Grade 8 CBSE), one repetition, with a sentinel account.
3. Fix harness defects, keeping model failures as measured outcomes. Any new smoke attempt uses fresh roots and is explicitly recorded.
4. Commit the dataset/runbook and harness/tests in small batches; push the normal branch without force.
5. Run `run`: all 15 personas once, with fresh state independent of smoke.
6. Commit and push sanitized results and the report.

Never start the full sweep before the harness push succeeds. `smoke` cannot select the other profiles. Extra requested local models must be advertised by the same approved endpoint. There is no model substitution or paid fallback.

## Protocol

Each profile has ten new conversations and thirteen scripted turns. The full run has 150 conversations and 195 turns, plus local title calls, memory-tool iterations, and auxiliary REST setup requests. P01 smoke has ten conversations and thirteen turns. All task answers stay in chat.

| Stage | Purpose |
|---|---|
| C1–C2 | Natural recurring context and preference; C2 adds a temporary draft label |
| C3 | Blind recall before any explicit remembering instruction |
| C4 | Explicit global context/style/notebook and workspace A heading |
| C5 | Global recall in B, absent A heading, then establish B heading |
| C6 | Return to A and recall its heading |
| C7 | Peer account probe and denial of the owner's workspace |
| C8 | Correct context and forget the global notebook label |
| C9 | Corrected context in B; forgotten and temporary labels absent |
| C10 | Restart gateway/engines, sign in again, new conversation in A |

P01–P15 cover school revision, stationery, badminton, reading, baking, plants, photography, Spanish, cycling, tabletop games, crochet, astronomy, podcast editing, exhibition notes, and programming. No actual orders, locations, account histories, health records, or financial details are used.

A is `workspace/personal`; B is `workspace/project`. Both are plain directories without Git or memory bindings. Scratch lives in `workspace/sessions`; session deletion must preserve A/B. Accounts run in pairs: P01/P02 through P13/P14, then P15/sentinel. Smoke uses P01/sentinel. Only the sentinel is seeded, through its own authenticated memory API, with notebook label `Guard-P16`.

Within a batch, both owners complete C1–C6 before peer probes, then C8–C9. The gateway restarts with existing data before C10; provisioning is never repeated. Fresh UUIDs prevent transcript reuse. Account SQLite stores start empty; only the real model writes persona memories.

### What the scores mean

Automatic save requires persisted matching content before C3, without an explicit request or consent question. Correct global scope is reported separately; a target fact embedded in a temporary workspace note can satisfy storage/recall while failing scope and noise checks. Recall is scored separately; a lucky correct reply without stored memory is not joint success. Existing guidance intentionally treats ambiguous incidental phrasing conservatively.

Persisted rows and tool results establish saves. Hosted `memory_saved` events are best-effort and can be absent. Format and preference-reason retention are separate. Matching uses fixed normalized token/phrase groups, not another LLM.

Workspace scope selects **injected context**; an account's memory listing and `memory_read` remain account-wide. A/B injection is checked against the actual SQLite workspace column. A wrong-workspace answer is a model outcome; incorrect injection is a harness/application failure. Negative controls are checked independently: a correct heading does not excuse mentioning the other heading, and an UNKNOWN reply does not prove a temporary memory was removed. Cross-account memory and folder access remain isolation boundaries.

Correction and forgetting need earlier stored controls. Missing prerequisites produce `null`/unexercised outcomes, never a successful deletion. Correction requires the new context and absence of the original active value. Unexpected rows, duplicates, temporary saves/attempts, malformed arguments, false save claims, permission requests, and errors are reported. Save claims without row changes are a heuristic, and fixed concept matching can undercount paraphrases.

Tool failures include framework failures and error-valued memory results, even when the turn completes. Non-memory tool calls are counted separately from approval requests: an automatic `todo_write` call violates the prompt but requests no approval. These diagnostics do not change the existing memory guidance or expected fact matching.

Structured questions receive “No additional consent is granted. Follow the instructions already in my message.” Grouped answers use the supplied headers. Unrelated tool approvals are denied.

## Prerequisites and portable setup

Run on a Linux operator account with:

- A checkout of the tested source and Python 3.10+; install `pip install -e '.[dev,openshell]'` in a private virtual environment if needed.
- A healthy, configured OpenShell gateway (`openshell gateway info`) and its client configuration.
- Nginx, OpenSSL, and a production SPA at `surfaces/gui/dist/index.html`. Build it with `npm ci` and `npm run build` in `surfaces/gui` if missing.
- Network access to the explicitly supplied local inference endpoint. The runner supports literal RFC1918/loopback IPv4, ULA/loopback IPv6, and localhost; public inference and redirects are rejected.
- Three unused loopback ports: 18453, 18866, and 18867 by default.

Historical VM defaults are `ubuntu@10.42.0.248` and interpreter `/home/ubuntu/openworker-phase2-20261002/.venv/bin/python`. Verify actual versions and availability. Use an isolated source copy under the operator's home; preserve existing deployments. Source transfer must exclude `.env`, account data, credentials, and private artifacts. Verify source hashes after transfer; a Git archive may include `.evaluation-revision` containing the committed SHA for reporting.

No browser or VM account history is required. HTTPS is exercised with HTTP and WebSocket clients through Nginx. The temporary certificate is explicitly trusted by these clients; TLS verification stays enabled. Nginx, gateway, and recording proxy bind to loopback. Quick Tunnel and the Windows sandbox gate are outside this evaluation.

On another Linux machine, configure OpenShell and replace the local endpoint/model arguments. A machine lacking VM/local-inference access can validate the corpus and run offline tests, but cannot claim the live gate passed. The script does not install or serve the local LLM.

## Commands

From the checkout root, using the installed Python interpreter:

```bash
python scripts/eval_memory_personas.py --help
python scripts/eval_memory_personas.py validate
python -m pytest tests/test_memory_persona_eval.py tests/test_memory.py \
  tests/test_memory_api.py tests/test_hosted_acceptance_helpers.py \
  tests/test_hosted_supervisor.py
```

Run smoke before committing/pushing the harness:

```bash
PERSONA_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
PERSONA_SMOKE_ROOT="$HOME/.cache/openworker-persona-smoke-$PERSONA_STAMP"
PERSONA_SMOKE_OUTPUT="$HOME/.cache/openworker-persona-smoke-results-$PERSONA_STAMP"
python scripts/eval_memory_personas.py smoke \
  --base-url http://10.42.0.202:8090/v1 \
  --models Ornith-1.5-35B-Uncensored-Q6_K \
  --root "$PERSONA_SMOKE_ROOT" --output "$PERSONA_SMOKE_OUTPUT" \
  --spa surfaces/gui/dist
```

After the harness push succeeds, deploy that committed revision and run:

```bash
PERSONA_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
PERSONA_FULL_ROOT="$HOME/.cache/openworker-persona-full-$PERSONA_STAMP"
PERSONA_FULL_OUTPUT="$HOME/.cache/openworker-persona-full-results-$PERSONA_STAMP"
python scripts/eval_memory_personas.py run \
  --base-url http://10.42.0.202:8090/v1 \
  --models Ornith-1.5-35B-Uncensored-Q6_K --runs 1 \
  --root "$PERSONA_FULL_ROOT" --output "$PERSONA_FULL_OUTPUT" \
  --spa surfaces/gui/dist
```

Optional port flags are `--https-port`, `--gateway-port`, and `--model-proxy-port`. Root/output must be new, separate directories. Deployment roots must stay outside `/tmp` for OpenShell bind mounts.

`--runs` adjusts repetitions in the full action; smoke always uses one. Multiple explicitly requested local model IDs run sequentially with independent stores. Endpoint/model failures stop execution without fallback. Per-turn deadline is 180 seconds; main settings are effort low, output limit 2048, and six iterations. Both reviewer modes are disabled. Main temperature is unset; title calls retain their application defaults.

The recording proxy serializes all local inference and separates title/main usage, queues, latency, effective wire parameters, and failed requests. Application/SDK parameter-fix retries may appear in the request ledger; the harness never retries a turn. Missing usage stays null and local cost is unpriced.

## Outputs and cleanup

- `results.json`: sanitized aggregate and per-persona records.
- `report.md`: readable metrics, environment, coverage, and limitations.
- `conversations/`: incremental sanitized checkpoints, including failed-run evidence.
- `requests.jsonl`: local request metadata and usage; no auth headers or prompts.
- `private/`: operational diagnostics; keep private and exclude from Git.

Cleanup runs after each batch and releases the recording proxy at exit. Recovery after interruption:

```bash
python scripts/eval_memory_personas.py cleanup --root "$PERSONA_FULL_ROOT"
```

Cleanup requires the runner ownership marker, tracks process identity, and selects OpenShell sandboxes by the account registry label. It removes account state, certificates, and owned process roots; preserves the shared operator gateway; and checks released ports. It is idempotent when the root is already removed.

Before committing evidence, inspect it for passwords, cookies, CSRF/engine tokens, private keys, and operator credentials. Never commit private manifests, raw logs, or certificates. Retain raw diagnostics in the private output directory. Sanitized JSON contains only synthetic content and metadata.

A complete run executes every scheduled conversation with no automatic reruns, validates fresh-session routing/scope/isolation, performs restart, and finishes cleanup. Model misses remain results. Infrastructure failures cannot be marked complete. One repetition is descriptive; do not combine percentages with the earlier four-scenario model comparison. If scorer-only corrections are replayed against captured evidence, retain the collection revision/hash and record the scoring revision/hash separately; do not rerun inference or silently alter expected facts.

## Recorded execution

See the [summary report](summary.md), [full local-model report](report.md), [sanitized full results](results.json), [P01 smoke findings](smoke.md), and [execution checklist](checklist.md). The earlier model comparison remains separate in [model evaluations](../../model-evaluations/2026-10-02.md).
