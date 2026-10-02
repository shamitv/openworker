# Phase 3 status

Status: Complete — Linux HTTPS browser acceptance and required real LLM gate passed on 2026-10-02.

The gateway strips browser credentials, CSRF, forwarding and hop headers, injects verified engine credentials, and removes cookies after HTTPX builds requests. Decoded dot segments are rejected before route checks, request bodies are bounded while reading, and raw upstream streams close on failure or browser disconnect. Accepted browser sockets close with `4401` after session expiry or revocation; engine events do not extend idle expiry. Upstream refusal/busy close codes and relay cleanup are covered. Authenticated HTML remains uncached; fingerprinted assets are immutable, stable assets revalidate, and missing/reserved/escaping paths return `404`.

The browser deduplicates hosted-session checks after socket closure and same-origin REST `401`, including machine/cloud routes. Expired sessions and required password changes redirect; valid sessions and transient failures retain reconnect behavior. Hosted transport remains same-origin with CSRF and no engine token. Desktop/Auth0 behavior and the `headless_web` capability remain intact. Production CLI and authentication endpoint shapes are unchanged.

## Regression evidence

- Hosted backend suite: **126 passed in 40.33s**, covering accounts, gateway edges, supervisor, boundaries and acceptance helpers.
- Server, remote-home and cloud compatibility suite: **129 passed in 58.69s**.
- GUI unit suite: **489 passed across 49 files in 13.48s**. Production TypeScript/Vite build passed; existing bundle-size warnings remain.
- Existing hermetic Playwright suite: **all 327 cases passed across runs**. The first run raced browser installation; rerunning those failures passed 162 cases, and the remaining onboarding timeout passed on a targeted rerun. This was not one clean full-suite run.
- Final real-engine/OpenShell Linux regression on the VM: **2 passed in 42.37s**.
- Final deterministic HTTPS hosted gate: **1 passed in 16.0s**.
- Required real LLM HTTPS hosted gate: **1 passed in approximately 96s**, with no mocks, fallback, skip or automatic retry. An earlier strict-filename failure was retained; the prompt was clarified to specify the file path and exact contents, then the complete gate passed.

## Live acceptance evidence

The isolated deployment used `ubuntu@10.42.0.248` (Ubuntu 26.04.1, Python 3.14.4, OpenShell 0.0.116), the built SPA, and Nginx at `https://10.42.0.248:18443`. Gateway/model fixture listeners and both private engines bound to loopback. Browser certificate exceptions were confined to the test contexts for the temporary self-signed certificate.

Chromium/Alice and Firefox/Bob signed in with independent accounts and concurrently ran chat over WebSockets. Each account used the existing OpenAI-compatible provider at `http://10.42.0.202:8090/v1`, a harmless placeholder key, and `openai:Ornith-1.5-35B-Uncensored-Q6_K`. Both sessions reported OpenShell with full enforcement. Each browser approved `write_file` through the UI, observed successful execution, an assistant response and turn completion, and produced a uniquely named file with its exact random marker (a trailing newline is allowed). Authenticated downloads matched the VM filesystem. Reload preserved the transcript and artifact; cross-account transcript/artifact retrieval did not disclose the peer marker. Alice's expiry redirected to login while Bob remained authenticated and completed another real-model file turn. Engine launch tokens were absent from observed browser traffic, HTML and storage. Each turn has a 180-second deadline.

The reproducible commands are `npm run e2e:hosted` and `npm run e2e:hosted:llm`; see [the operator instructions](../../../headless-vm-ui.md#phase-3-https-browser-acceptance). Private evidence is retained on the verification workstation under `/tmp/openworker-phase3-evidence`: per-browser event JSON and traces, run/build/regression logs, the initial model failure, and sanitized VM gateway/engine/proxy logs in `vm-logs.tar.gz`. Credentials and private manifests are excluded from Git.

Cleanup completed: disposable gateway/proxy services, test engines and sandbox containers stopped; test listener ports closed; temporary deployment, account roots and copied manifests removed. The existing OpenShell gateway remains active. Nginx remains installed with its default service disabled.

## Remaining deployment scope

Public-domain certificate trust, Phase 5 deployment/OAuth acceptance, and the separate Windows sandbox live gate remain pending. [Phase 4 password-based product acceptance](../phase-04-headless-flows/status.md) is now complete. This completion establishes Linux Phase 3 with a temporary test certificate. Engine processes still share an OS identity, as described in the [overview](../plan.md).
