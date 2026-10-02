# Host the full OpenWorker UI on one VM

This deployment serves the built GUI over HTTPS to at most 20 administrator-provisioned accounts, using supervised temporary internet access through Cloudflare Quick Tunnel. One loopback engine per enabled account retains its own state, keys, sessions, and workspaces. Browser logout revokes the browser session; scheduled work continues in that account's engine. The gateway and engines run under one OS identity, so a code-execution compromise of the backend can still cross homes. Place the gateway and the user homes on a dedicated VM.

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

## Temporary internet access with Cloudflare Quick Tunnel

The default public path is browser → Cloudflare HTTPS edge → `cloudflared` on
this VM → loopback gateway → private engines → OpenShell. Install `cloudflared`
using [Cloudflare's downloads](https://developers.cloudflare.com/tunnel/downloads/)
and record `cloudflared --version` when verifying the deployment. Keep the
built SPA, accounts and enforcing sandbox ready before starting exposure.

### One-command launcher on Linux

[`scripts/hosted_quick_tunnel.py`](../scripts/hosted_quick_tunnel.py) starts
`cloudflared`, reads its generated HTTPS URL, and starts the gateway with that
exact public origin. It waits for loopback gateway health, prints the URL, and
saves it as `public-url.txt` beside private `cloudflared.log` and `gateway.log`
files in a new run directory under `<data-dir>/quick-tunnel/`. It stops its
children on Ctrl+C, SIGTERM, terminal hangup or either child's exit. Existing
account data and the operator's OpenShell gateway are retained.

For the existing Ubuntu checkout and the accounts created under
`/home/ubuntu/.local/share/openworker-web`, run:

```sh
cd /home/ubuntu/openworker-phase2-20261002
.venv/bin/python scripts/hosted_quick_tunnel.py
```

The defaults are the current user's `~/.local/share/openworker-web`, the
checkout's `surfaces/gui/dist`, its `.venv/bin/python` when present, OpenShell,
and port 8766 on `127.0.0.1`. Account creation, SPA building and installation of
`cloudflared` are prerequisites. The launcher refuses a missing account database,
an occupied port or another launcher using the same data directory. It reports
startup failures with the private log location.

For an installation using the data directory and Python environment from the
account commands above, run from the repository:

```sh
python3 scripts/hosted_quick_tunnel.py \
  --python /opt/openworker/venv/bin/python \
  --data-dir /var/lib/openworker-web
```

Use `--spa`, `--port` or `--cloudflared` for different paths/ports; `--help`
lists the discovery, startup and shutdown timeouts. Stop with Ctrl+C and rerun
the same command to restart. The launcher discovers the new URL automatically;
sign in at the new hostname and update external machine connections as below.
It runs in the foreground; unattended boot and restart services remain outside
this plan. Loopback health alone does not complete the public Phase 5 gate.

### Manual startup

In a supervised terminal on the VM, start the tunnel:

```sh
cloudflared tunnel --url http://127.0.0.1:8766
```

Keep that process running and copy its generated `https://<random>.trycloudflare.com`
URL. Requests can fail until the gateway starts. In another terminal, set that
exact origin and start the gateway on loopback:

```sh
OPENWORKER_TUNNEL_ORIGIN='https://<random>.trycloudflare.com'
/opt/openworker/venv/bin/openworker-web serve \
  --spa /path/to/openworker/surfaces/gui/dist \
  --data-dir /var/lib/openworker-web \
  --public-origin "$OPENWORKER_TUNNEL_ORIGIN" \
  --sandbox-provider openshell \
  --host 127.0.0.1 --port 8766
```

Replace the placeholder with the URL printed by the running tunnel, with no
path, query or fragment. Cloudflare provides the public HTTPS certificate;
`cloudflared` reaches the gateway over HTTP on loopback. This path requires no
custom domain, public Nginx listener, VM certificate or inbound web port.
Use normal browser and CLI certificate verification. Authenticate users with
the application's administrator-provisioned username/password accounts.

On startup the gateway launches all enabled engines, even if nobody is signed
in. It refuses a public bind and does not terminate TLS itself. Child engines
bind only to `127.0.0.1` on ephemeral ports and receive launch tokens in their
process environment. Restrict local shell and filesystem access to the service
operator. Supervise the gateway and tunnel for this temporary session using the
launcher or the manual procedure; unattended boot/restart services are outside
this plan.

The gateway compares `Origin` with the exact `--public-origin` on state-changing
browser requests and WebSockets. Preserve the browser's original Origin and
verify forwarded client identity when testing login throttling through Cloudflare.
Cookies use `Secure`, `HttpOnly`, `SameSite=Strict`, and the `__Host-` prefix.
`/web/health` reports gateway liveness; engine failures appear in the gateway log
and each home's `state/engine.log`.

With `SameSite=Strict`, navigation from another site may omit the session cookie
and initially show login. Navigate directly to the current tunnel origin to
resume an existing session on that hostname.

Quick Tunnels create a new hostname on restart, have no uptime guarantee,
permit at most 200 in-flight requests and do not support SSE. The hosted UI uses
WebSockets; verify session and machine sockets through the tunnel. Treat this
as temporary exposure, without a stable production availability claim. See
[Cloudflare's Quick Tunnel documentation](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
The 20-account target remains subject to VM resource measurements and the tunnel's
separate concurrent-request limit.

### Tunnel restart and hostname changes

1. Stop the external joiner processes and gateway normally; stop the old tunnel
   if it is still running. Preserve the account data directory and each machine's
   existing state and identity keys.
2. Start a new Quick Tunnel with the same loopback target and obtain its new
   HTTPS hostname.
3. Restart the gateway with the new `--public-origin` and the same `--data-dir`.
   Enabled engines now generate account join URLs on the new hostname.
4. Open the new URL and sign in again. Browser cookies for the old hostname are
   not usable at the new hostname. Verify existing workspaces, sessions and files.
5. In the owning account's Machines settings, generate a fresh join URL. Run the
   copied command on the external workstation using the same state directory:

   ```sh
   COWORKER_STATE_DIR=/path/to/existing/machine-state \
     openworker join 'https://<new-host>.trycloudflare.com/h/<account-id>/j/<fresh-token>' --name=my-box
   ```

   The client uses its existing identity keys and saves the new controller URL
   after the signed handshake. Verify its machine ID is unchanged; stop it and
   run `openworker up` with the same `COWORKER_STATE_DIR` to verify reconnect.

With the launcher, Ctrl+C and rerunning its command automate the tunnel and
gateway steps above. The sign-in and external machine steps still apply.

A gateway restart while the tunnel process stays alive retains the public
hostname. A tunnel restart requires the manual origin and machine steps above;
existing joiners cannot discover the new hostname automatically.

### Local Nginx HTTPS fixtures

The completed Phase 3 and Phase 4 gates below retain their disposable Nginx
proxy, temporary self-signed certificate, WebSocket forwarding and cleanup
commands. Their `scripts/hosted_browser_fixture.py proxy` and `stop-proxy`
commands provide the local HTTPS setup. These remain useful local regressions;
public Quick Tunnel acceptance requires ordinary certificate verification.

## Machine joins and authentication scope

Machine join links generated by an account's engine use `/h/<account-id>/j/<token>`
on the current public origin. The joined machine connects to
`/h/<account-id>/ws/machine`; the account's engine validates enrollment tokens
and signed machine identity. Keep the account enabled while its joined machines
or automations should run. Use the UI-generated HTTPS join URL directly on the
external workstation.

This multi-phase plan uses username/password app authentication. External OAuth
consent, callback configuration and token exchange are outside its scope,
superseding their earlier deferral to Phase 5. Existing OAuth implementation and
historical tests remain; use API-key providers or local models for this acceptance.
Hosted OpenAI Codex subscription sign-in remains unavailable because its fixed
localhost callback is unsupported. No new authentication API or database
migration is required for this revision.

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
forwards the original browser Origin and WebSocket upgrades. Public HTTPS
certificate verification through Quick Tunnel remains a separate Phase 5 gate.

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
production enrollment TTL. External OAuth acceptance is outside this multi-phase plan.

The live runner removes its isolated external machine state and stops its child
processes in cleanup. Browser traces and sanitized CLI logs are written to
`surfaces/gui/test-results-hosted-flows/`, or to the directory supplied with
`--output`. Keep them private: traces can contain disposable passwords and join
links. Stop `serve` normally, stop the fixture's proxy with `stop-proxy`, confirm
the engines/sandboxes/listeners stopped, and remove the fixture roots and copied
manifests after retaining needed evidence. Leave the existing OpenShell gateway
running.

## Phase 5 public Quick Tunnel acceptance

Phase 5 remains pending. Follow the setup above on a fresh Linux VM with a
new disposable acceptance data directory and two private OpenShell engines.
Keep the tunnel hostname fixed for each run and record the generated URL,
`cloudflared`, OS, Python, Node, OpenShell and browser versions.

Add a public-tunnel variant of the existing hosted browser gate. The current
Phase 3/4 runners allow the fixture's self-signed certificate in browser contexts,
and the Phase 4 CLI uses `HOSTED_TEST_CA`; those settings do not establish public
TLS acceptance. The public variant must use `ignoreHTTPSErrors: false`, normal
CLI certificate verification and the ordinary system CA trust store, without a
fixture CA or certificate-verification bypass. No public acceptance command or
passing result is claimed until that variant is implemented and run.

Require independent Chromium/Alice and Firefox/Bob sessions and a real external
workstation joiner. Verify password login/logout/expiry, approved work, confined
typed/recent workspaces, previews, exact downloaded bytes, persistence and
cross-account isolation. Extend checks to secrets, inbox, approvals, files,
revocation, session/machine WebSockets, CSRF/origin rejection, login throttling
and forwarded client identity. Verify sandbox failure, crash recovery, unattended
scheduled work, backup/restore and idle/active resource measurements. Complete
existing desktop authentication and Tauri regressions.

Exercise the manual hostname-change procedure with the same acceptance data
and external machine state. Verify the account data and machine ID persist,
fresh URLs target the new hostname, and `openworker up` reconnects after the
controller URL has been updated. The public gate must have no skipped scenarios
or automatic retries. External OAuth acceptance is outside this plan; the
separate Windows sandbox live gate remains pending.

Retain sanitized gateway/engine/tunnel logs, events and browser traces privately;
traces may contain disposable passwords and join URLs. After recording results,
stop the joiners, gateway and tunnel, confirm disposable engines/sandboxes and
listeners stopped, then remove the disposable account roots, copied manifests
and external joiner state. Keep operational account data and the existing
OpenShell gateway. Record evidence and cleanup in the [Phase 5 status](plans/headless-vm-ui-serving/phase-05-deployment-and-verification/status.md)
before marking it complete.
