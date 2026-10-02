# Host the full OpenWorker UI on one VM

This deployment serves the built GUI over HTTPS to at most 20 administrator-provisioned accounts. One loopback engine per enabled account retains its own state, keys, sessions, and workspaces. Browser logout revokes the browser session; scheduled work continues in that account's engine. The gateway and engines run under one OS identity, so a code-execution compromise of the backend can still cross homes. Place the gateway and the user homes on a dedicated VM.

## Build and install

On the VM, use Python 3.10+ and Node.js compatible with the GUI build:

```sh
python3 -m venv /opt/openworker/venv
/opt/openworker/venv/bin/pip install -e .
cd surfaces/gui
npm ci
npm run build
```

The SPA is `surfaces/gui/dist`. Serve it through `openworker-web`; do not run Vite's development server on the public VM. Install and prove one enforcing sandbox provider before provisioning users. Linux deployments normally use OpenShell; follow [OpenShell setup](openshell.md), including its gateway and image. `direct` and `runner_local` are not accepted for this deployment. The gateway checks sandbox availability and declines to start a private engine when it is unavailable.

### Native Windows verification

Hosted Windows tools use a unique restricted logon under one of the two existing network accounts, with private credential/home/cache/temp folders. Managed homes receive Windows ACLs, and runtime/root/pipe grants name the logon rather than the shared account. Public Windows files accessible to ordinary local users remain accessible. Engine launch environments exclude operator provider secrets and plugin paths.

This implementation has automated coverage; live enforcement and recovery are still pending. On the selected PC, sandbox setup reached a canceled UAC prompt, and the execution context denied window-station creation. See [Phase 2 status and its live-gate command](plans/headless-vm-ui-serving/phase-02-private-engines/status.md) before treating this Windows deployment as verified. Hosted mode refuses direct execution and alternate provider overrides. Configured base-directory artifact previews/downloads and hosted credential copying refuse hard links whose ownership cannot be established from their path.

## Provision accounts and start

Choose a private data directory on persistent storage. The operator running the gateway owns this directory and its backups. Account passwords are prompted without echo; do not put them in shell arguments or automation logs.

```sh
/opt/openworker/venv/bin/openworker-web --data-dir /var/lib/openworker-web user create alice
/opt/openworker/venv/bin/openworker-web --data-dir /var/lib/openworker-web user list
/opt/openworker/venv/bin/openworker-web --data-dir /var/lib/openworker-web user reset-password alice
/opt/openworker/venv/bin/openworker-web --data-dir /var/lib/openworker-web user disable alice
```

The admin-supplied password must be changed at the first login and after a reset. Disabling an account revokes its browser sessions and stops its engine during the next supervisor reconciliation. Homes are assigned by the database under `/var/lib/openworker-web/homes/<id>`; the browser session endpoint tells each user the path of their own `workspace` directory for VM path entry. Do not edit the ownership mapping by hand.

The account database upgrades automatically on gateway or account-command startup. Schema version 1 adopts existing compatible unversioned hosted databases without changing accounts, sessions, or home files. An incompatible schema or one written by a newer application is rejected; restore a compatible backup or use the matching application version rather than editing the version marker.

Start the gateway on loopback:

```sh
/opt/openworker/venv/bin/openworker-web serve \
  --spa /path/to/openworker/surfaces/gui/dist \
  --data-dir /var/lib/openworker-web \
  --public-origin https://worker.example.com \
  --sandbox-provider openshell \
  --host 127.0.0.1 --port 8766
```

Use a service manager such as systemd to restart the gateway. On startup it launches all enabled engines, even if nobody is signed in. The gateway refuses a public bind; it does not terminate TLS itself. The child engines bind only to `127.0.0.1` on ephemeral ports and receive launch tokens only in their process environment. Restrict local shell and filesystem access to the service operator. Keep the HTTPS proxy and gateway on the same VM.

## HTTPS reverse proxy

The following Nginx example preserves browser `Origin`, WebSocket upgrades, and the request path. Configure a real certificate and replace the domain. Restrict direct access to port 8766 with the host firewall.

```nginx
server {
    listen 443 ssl http2;
    server_name worker.example.com;
    ssl_certificate /etc/letsencrypt/live/worker.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/worker.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8766;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Origin $http_origin;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
        client_max_body_size 32m;
    }
}

server {
    listen 80;
    server_name worker.example.com;
    return 301 https://$host$request_uri;
}
```

The gateway compares `Origin` with the exact `--public-origin` on every state-changing browser request and WebSocket. Keep the reverse proxy from rewriting an unrelated origin into the expected one. Cookies use `Secure`, `HttpOnly`, `SameSite=Strict`, and the `__Host-` prefix. `/web/health` reports gateway liveness; engine launch failures are visible in the gateway log and each home’s `state/engine.log`.

With `SameSite=Strict`, a navigation arriving from another site may omit the session cookie and initially show the login page. Navigate directly to the configured public origin to resume an existing session. Account-scoped OAuth callbacks validate engine-side flow state without relying on the browser session cookie.

## OAuth and machine joins

Hosted app sign-in uses administrator-provisioned username/password accounts. External OAuth is optional for service connections; API-key providers and local models do not require it. Phase 4 acceptance covers this password-based hosted experience. Real external provider consent and callback verification is an explicit [Phase 5 gate](plans/headless-vm-ui-serving/phase-05-deployment-and-verification/todo.md).

MCP OAuth registers callbacks at `https://worker.example.com/h/<account-id>/mcp/oauth/callback`; the provider must allow the public HTTPS redirect. Managed connector OAuth uses the same account route for `/oauth/callback`. Cloud sign-in requires an Auth0 application configured to allow each hosted account’s `https://worker.example.com/h/<account-id>/auth/callback` redirect; set its `cloud_auth_domain`, `cloud_client_id`, and `cloud_audience` in that home’s `state/config.toml`. The default desktop Auth0 client may not allow a new VM domain. The browser launches consent pages, and the engine checks one-time flow state before accepting callbacks. OpenAI Codex subscription sign-in currently requires its fixed localhost callback and is unavailable in hosted mode; use an API key provider there.

Machine join links generated by an account’s engine use `/h/<account-id>/j/<token>` on the public origin. The joined machine connects to `/h/<account-id>/ws/machine`; enrollment tokens and signed machine identity are validated by the account’s engine. Keep an account enabled while its joined machines or automations should run.

## Operations and backup

- Treat `accounts.sqlite3` and the entire `homes/` tree as one backup unit. Stop the gateway for a simple consistent filesystem copy, or use SQLite’s backup API plus a coordinated home snapshot. Include SQLite WAL files if copying a live database. Protect backups at least as tightly as the live secrets.
- Review `account_audit` in the central SQLite database for account and login events. Engine logs are per home at `state/engine.log`; gateway supervisor logs go to the service manager.
- Size memory for 20 resident engine processes plus their active model, connector, and sandbox workloads. Measure one idle and one active engine on the target VM before setting resource limits; no fixed RAM number is reliable across models and sandbox providers.
- Test recovery by restarting the gateway and confirming enabled engines resume scheduled work, then disable a test account and confirm its browser session and engine stop. A failed sandbox preflight makes that engine unavailable instead of running tools directly.

The gateway provides application-level separation across accounts. It does not create OS accounts or containers per user. Use a separate VM or stronger process isolation when the threat model includes a compromised backend process.

## Linux Phase 2 acceptance gate

Install the Python OpenShell extra (`pip install -e '.[dev,openshell]'`), Docker, OpenShell **0.0.116**, and its pinned base image before running the gate. The OpenShell gateway must run as the same operator that starts `openworker-web`, with bind mounts enabled; see [OpenShell setup](openshell.md). Private engines use their own home, state, configuration, cache, and runtime directories, and link only the operator's OpenShell client configuration into their configuration tree.

Use Linux's default `allowlist` network profile and configure explicit allowed destinations. The existing `open` profile is rejected by OpenShell 0.0.116 and prevents sandbox startup. Linux Phase 2 passed on the supplied Ubuntu VM; see [the recorded acceptance evidence](plans/headless-vm-ui-serving/phase-02-private-engines/status.md).

From the repository on the Linux VM:

```bash
OPENWORKER_TEST_HOSTED_LINUX=1 .venv/bin/python -m pytest \
  tests/test_hosted_linux_live.py -v \
  --basetemp "$HOME/.cache/openworker-hosted-linux-acceptance"
```

Use that dedicated test directory rather than pytest's default `/tmp`: the gateway service may use `PrivateTmp=true`, which hides host `/tmp` bind-mount sources. Pytest clears the dedicated directory between runs. Opting in makes missing prerequisites fail the gate. The scenarios create real sandbox containers and real private engines; a deterministic local model exercises scheduled tools without a paid API key. They cover concurrent sandbox boundaries, private credentials, read-only mounts, engine authentication/listeners, cross-account requests, unattended work, crash recovery, and cleanup. Passing this gate establishes Phase 2 Linux evidence; public HTTPS, real-browser product flows, and the Windows live gate retain their separate verification requirements.

## Phase 3 HTTPS browser acceptance

The explicit browser gates use the **built SPA**, Nginx, two real private engines,
OpenShell, and independent Chromium/Alice and Firefox/Bob sessions. The regular
GUI `e2e` suite remains hermetic. Install the GUI dependencies and browsers on
whichever machine runs Playwright:

```bash
cd surfaces/gui
npm ci
npx playwright install chromium firefox
npm run build
```

On the sandbox-ready fixture host, install Nginx and OpenSSL. Run from the
repository root using its Python environment with development/OpenShell
extras. Keep the disposable data under the operator's home, outside `/tmp`, so
OpenShell can bind-mount it. Choose an unused HTTPS port and loopback gateway
port; the defaults below are 18443 and 18766.

```bash
PHASE3_ROOT="$HOME/.cache/openworker-phase3-fixture"
.venv/bin/python scripts/hosted_browser_fixture.py prepare \
  --root "$PHASE3_ROOT" --origin https://10.42.0.248:18443 --mode fixture
.venv/bin/python scripts/hosted_browser_fixture.py proxy --root "$PHASE3_ROOT"
.venv/bin/python scripts/hosted_browser_fixture.py serve \
  --root "$PHASE3_ROOT" --spa surfaces/gui/dist
```

`prepare` refuses to reuse an existing data directory. `serve` must start both
private engines or fail. The fixture generates a temporary self-signed
certificate; certificate exceptions apply only to the test browser contexts.
The standalone Nginx configuration uses private temporary directories and
forwards the original browser Origin and WebSocket upgrades. Production TLS
trust and public-domain deployment retain their separate verification gate.

The private `manifest.json` contains disposable passwords and launch tokens
used only by the test runner's non-disclosure assertions. Do not commit,
publish, or print it. After gateway startup completes, pass its path to the
runner. When browsers run on another machine, copy the manifest privately and
provide `HOSTED_TEST_SSH_RUNNER`, an executable accepting one remote command
argument, plus the fixture host's Python interpreter path. The SSH runner
must preserve that command as one argument and use the operator's existing
SSH authentication. Do not place credentials in arguments.

```bash
cd surfaces/gui
HOSTED_TEST_MANIFEST=/private/path/manifest.json \
HOSTED_TEST_PYTHON=/path/on/fixture/host/.venv/bin/python \
HOSTED_TEST_SSH_RUNNER=/path/to/operator-ssh-wrapper \
npm run e2e:hosted
```

Omit `HOSTED_TEST_SSH_RUNNER` when the test runner and fixture share a host.
The control helper checks account-owned files directly and expires only the
disposable Alice account; it is never exposed through the gateway.

For the required real LLM gate, stop the deterministic gateway and proxy,
then prepare a **new** directory with `--mode llm`:

```bash
.venv/bin/python scripts/hosted_browser_fixture.py prepare \
  --root "$HOME/.cache/openworker-phase3-llm" --mode llm \
  --llm-base-url http://10.42.0.202:8090/v1 \
  --llm-model Ornith-1.5-35B-Uncensored-Q6_K
```

Start `proxy` and `serve` with that new root, retrieve its updated private
manifest after startup, and invoke `npm run e2e:hosted:llm` with the same runner
variables. Each account uses its own OpenAI-compatible provider profile with
a harmless placeholder API key and an explicitly selected local model.
Model calls occur in the private engine; file tools remain inside OpenShell,
so no additional sandbox network grant is necessary.

Both gates require approval through the UI, successful file-tool execution,
full sandbox enforcement, exact account-specific artifact bytes, transcript
and artifact persistence after reload, peer-account rejection, expiry redirect,
and a subsequent successful Bob turn. The live gate has no model fallback,
unavailable-model skip, or automatic retry. Model turns have a 180-second
bound. Test results retain per-browser traces and WebSocket events; retain
gateway/engine logs when diagnosing failures.

After each run, stop `serve` normally and stop its isolated proxy:

```bash
.venv/bin/python scripts/hosted_browser_fixture.py stop-proxy --root "$PHASE3_ROOT"
```

Confirm the fixture's engines and sandbox containers have stopped. Preserve
needed evidence privately, then remove the disposable roots and copied
manifests. The operator's existing OpenShell gateway is left running.

## Phase 4 password-based product acceptance

`npm run e2e:hosted:flows` runs a separate gate against the built SPA and the
same real HTTPS/private-engine/OpenShell setup. It uses Chromium/Alice and
Firefox/Bob, with a real `openworker join` client on the verification
workstation **outside the VM**. The deterministic model fixture requests real
UI-approved writes; HTTP, WebSockets, authentication, downloads and machine
enrollment are not mocked. No scenario skips or automatic retries are enabled.

Prepare a new disposable root on the sandbox-ready VM; the flag adds permitted
project directories and invalid-path fixtures. Never reuse a Phase 3 or previous
Phase 4 account root for the final gate:

```bash
PHASE4_ROOT="$HOME/.cache/openworker-phase4-fixture"
.venv/bin/python scripts/hosted_browser_fixture.py prepare \
  --root "$PHASE4_ROOT" --origin https://10.42.0.248:18443 --flows
.venv/bin/python scripts/hosted_browser_fixture.py proxy --root "$PHASE4_ROOT"
.venv/bin/python scripts/hosted_browser_fixture.py serve \
  --root "$PHASE4_ROOT" --spa surfaces/gui/dist
```

Wait for both engines to start, then privately copy the updated manifest and
`proxy/cert.pem` to the verification workstation. Use the SSH runner described
above. Install this checkout with development dependencies in the workstation's
Python environment; that interpreter runs the actual machine CLI. The
certificate is trusted only in that test child process through `SSL_CERT_FILE`;
the gate does not disable CLI certificate verification or change system trust.

```bash
cd surfaces/gui
HOSTED_TEST_MANIFEST=/private/path/manifest.json \
HOSTED_TEST_PYTHON=/path/on/vm/.venv/bin/python \
HOSTED_TEST_SSH_RUNNER=/path/to/operator-ssh-wrapper \
HOSTED_TEST_EXTERNAL_PYTHON=/path/on/workstation/.venv/bin/python \
HOSTED_TEST_CA=/private/path/cert.pem \
npm run e2e:hosted:flows
```

The gate verifies password login/logout and independent session expiry, typed
and recent VM projects, rejection of missing/non-directory/peer/symlink paths,
approved file writes, exact browser-downloaded bytes, persistence and peer
artifact denial. Select project files through **Files** to open their preview;
**Artifacts** lists the session's scratch outputs. It then verifies account
HTTPS join URLs, signed reconnect, remote workspace selection, peer machine
denial, and invalid/used/wrong-account/disarmed token rejection. It asserts that
native picker/reveal routes are not invoked and engine tokens are not disclosed.

The ordinary hermetic browser suite additionally tests enrollment errors,
retry, countdown expiry and renewal; the backend suite proves token expiry
through a real WebSocket with a controlled clock. These checks retain the
production enrollment TTL. External OAuth consent remains a Phase 5 gate.

The live runner removes its isolated external machine state and stops its child
processes in cleanup. Browser traces and sanitized CLI logs are written to
`surfaces/gui/test-results-hosted-flows/`, or to the directory supplied with
`--output`. Keep them private: traces can contain disposable passwords and join
links. Stop `serve` normally, stop the fixture's proxy with `stop-proxy`, confirm
the engines/sandboxes/listeners stopped, and remove the fixture roots and copied
manifests after retaining needed evidence. Leave the existing OpenShell gateway
running.
