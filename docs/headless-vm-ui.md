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

MCP OAuth registers callbacks at `https://worker.example.com/h/<account-id>/mcp/oauth/callback`; the provider must allow the public HTTPS redirect. Managed connector OAuth uses the same account route for `/oauth/callback`. Cloud sign-in requires an Auth0 application configured to allow each hosted account’s `https://worker.example.com/h/<account-id>/auth/callback` redirect; set its `cloud_auth_domain`, `cloud_client_id`, and `cloud_audience` in that home’s `state/config.toml`. The default desktop Auth0 client may not allow a new VM domain. The browser launches consent pages, and the engine checks one-time flow state before accepting callbacks. OpenAI Codex subscription sign-in currently requires its fixed localhost callback and is unavailable in hosted mode; use an API key provider there.

Machine join links generated by an account’s engine use `/h/<account-id>/j/<token>` on the public origin. The joined machine connects to `/h/<account-id>/ws/machine`; enrollment tokens and signed machine identity are validated by the account’s engine. Keep an account enabled while its joined machines or automations should run.

## Operations and backup

- Treat `accounts.sqlite3` and the entire `homes/` tree as one backup unit. Stop the gateway for a simple consistent filesystem copy, or use SQLite’s backup API plus a coordinated home snapshot. Include SQLite WAL files if copying a live database. Protect backups at least as tightly as the live secrets.
- Review `account_audit` in the central SQLite database for account and login events. Engine logs are per home at `state/engine.log`; gateway supervisor logs go to the service manager.
- Size memory for 20 resident engine processes plus their active model, connector, and sandbox workloads. Measure one idle and one active engine on the target VM before setting resource limits; no fixed RAM number is reliable across models and sandbox providers.
- Test recovery by restarting the gateway and confirming enabled engines resume scheduled work, then disable a test account and confirm its browser session and engine stop. A failed sandbox preflight makes that engine unavailable instead of running tools directly.

The gateway provides application-level separation across accounts. It does not create OS accounts or containers per user. Use a separate VM or stronger process isolation when the threat model includes a compromised backend process.
