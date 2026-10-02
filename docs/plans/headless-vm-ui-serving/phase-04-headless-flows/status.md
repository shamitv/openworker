# Phase 4 status

Status: Complete — password-based Linux HTTPS acceptance passed on 2026-10-02.

## Scope and implementation

Administrator-provisioned username/password accounts are the Phase 4 identity. The UI displays the signed-in username, account workspace path and **Hosted VM** labels. Folder selection uses typed VM paths and recent workspaces. Hosted Add machine shows the generated account HTTPS join URL directly, reports enrollment failures and offers renewal. Skill-folder reveal is removed from the hosted UI; skill and MCP reveal endpoints refuse hosted requests before calling native code, following the existing `ok: false` error format. No authentication API or database migration was added.

External provider OAuth consent and account-scoped callback/token exchange acceptance moves to [Phase 5](../phase-05-deployment-and-verification/todo.md). Existing callback generation/routing regressions still pass; they do not establish live provider acceptance. Public certificate trust and the separate Windows sandbox gate remain later requirements.

## Commands and regression results

Executed from this checkout on the Linux verification workstation, with Python 3.12 and Node 22.16.0:

```bash
/tmp/openworker-test-venv/bin/python -m pytest \
  tests/test_hosted_accounts.py tests/test_hosted_web.py \
  tests/test_hosted_gateway_edges.py tests/test_hosted_supervisor.py \
  tests/test_hosted_boundaries.py tests/test_hosted_product_flows.py \
  tests/test_hosted_acceptance_helpers.py tests/test_remote_home.py \
  tests/test_skills_api.py tests/test_temp_workspace.py tests/test_cloud.py \
  tests/test_mcp_oauth.py tests/test_server.py -q
cd surfaces/gui
npm test
npm run build
npm run e2e
```

- Affected backend suites: **302 passed in 108.15s**, including password change/account authentication, artifact boundaries, machine enrollment, controlled-clock token expiry over a real WebSocket, native endpoint refusal, and desktop/cloud/MCP compatibility.
- GUI units: **489 passed across 49 files in 16.11s**.
- Production TypeScript/Vite build: passed in **14.20s**; existing bundle-size warnings remain.
- Full hermetic browser suite: **335 passed in 4.0 minutes** in the final complete run, including eight hosted cases for workspace forms, downloads, identity, machine enrollment, failures, expiry countdown and renewal. An earlier remote-folder case raced model loading; a targeted rerun passed, then an explicit loading wait was added before the clean full-suite run.

## Live HTTPS acceptance

The final fresh deployment used Ubuntu 26.04.1, Python 3.14.4 and OpenShell 0.0.116 at `ubuntu@10.42.0.248`, the built production SPA, and a disposable Nginx proxy at `https://10.42.0.248:18443`. The gateway, deterministic model fixture and two independent account engines bound to loopback. Chromium **149.0.7827.55 / Alice** and Firefox **151.0 / Bob** ran on the verification workstation. The deterministic model requested real UI-approved writes through fully enforcing OpenShell; HTTP, WebSockets, passwords, downloads, machine connections and filesystem contents were real. Phase 3 separately retains its real-LLM acceptance evidence.

The [operator guide](../../../headless-vm-ui.md#phase-4-password-based-product-acceptance) records disposable `prepare --flows`, `proxy`, and `serve` setup. The final gate ran with these environment values:

```bash
HOSTED_TEST_MANIFEST=/tmp/openworker-phase4-private/manifest-final-build.json \
HOSTED_TEST_PYTHON=/home/ubuntu/openworker-phase2-20261002/.venv/bin/python \
HOSTED_TEST_SSH_RUNNER=/tmp/openworker-vm-run.py \
HOSTED_TEST_EXTERNAL_PYTHON=/tmp/openworker-test-venv/bin/python \
HOSTED_TEST_CA=/tmp/openworker-phase4-private/ca-final-build.pem \
npm run e2e:hosted:flows -- --output=/tmp/openworker-phase4-evidence/live-final-build
```

Result: **1 passed in approximately 1.2 minutes**, **zero skipped scenarios and zero automatic retries**. The dedicated configuration uses one worker and `retries: 0`. Each acceptance attempt used new accounts and data. Earlier diagnostic runs corrected test navigation to Files for project previews, an ambiguous New session selector, and a login URL assertion to allow the browser-preserved session fragment; those failures are retained privately. A complete gate passed in 29.2s before the final label review; the final build then passed with fresh accounts while the full browser suite also ran. Settings scope and connector views now use Hosted VM as well.

Verified scenarios:

- Both password accounts logged in independently. Alice's expiry redirected to the login path and denied her artifact; Bob remained usable and completed another approved file write. Bob's logout revoked his browser session.
- Both accounts rejected missing paths, regular files, peer paths and symlink escapes. Each selected its own project through the UI, wrote there, reloaded and selected that project from recents.
- Each browser opened the file preview and clicked Download. Browser-downloaded bytes exactly matched the VM file; transcripts and authenticated artifacts survived reload. Missing and peer artifacts returned `404`.
- The actual workstation `openworker join` client used Alice's UI-generated HTTPS account URL and isolated state. It appeared only for Alice, served remote workspace requests through the gateway, supported UI folder selection, and reconnected with the same stored machine identity using `openworker up`. Bob could neither list nor address it.
- Real join connections rejected invalid, reused, wrong-account and disarmed tokens. Backend controlled-clock and hermetic browser cases separately verified server token expiry and countdown renewal without reducing the production TTL.
- Observed hosted flows invoked no native picker/reveal endpoint and disclosed no engine launch token. Backend guards proved native manager actions are never called.

Browser certificate exceptions were confined to the two test contexts. The CLI trusted the temporary certificate only through its child-process `SSL_CERT_FILE`; certificate verification and system trust were unchanged.

## Evidence and cleanup

Private evidence is retained on the workstation under `/tmp/openworker-phase4-evidence`: successful and diagnostic run logs, per-browser event JSON and traces, sanitized external joiner logs, backend/unit/build/browser logs, and sanitized VM gateway/engine/Nginx logs in `vm-logs.tar.gz`. Traces can contain disposable credentials and join URLs; all evidence directories are mode `0700` and files `0600`, and nothing was added to Git.

Cleanup completed after evidence collection: all five disposable deployment/account roots and uploaded archives were removed, gateways and proxies stopped normally, every private engine listener and ports 18443/18766/18767 closed, and OpenShell reported no sandboxes. External joiner processes and state, copied certificates and private manifests were removed. The existing OpenShell gateway and reused VM checkout remain available; Nginx remains installed with its default service disabled.
