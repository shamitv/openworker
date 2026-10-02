# Phase 2 status

Status: Linux/OpenShell Phase 2 acceptance complete on the supplied VM. The overall phase remains in progress because live Windows acceptance is blocked.

Updated: 2026-10-02 (Asia/Calcutta). Windows evidence below records the earlier native Windows target and its setup blockers. Linux verification now targets the supplied `Ubuntu_26_04_Server` VirtualBox VM.

## Implementation evidence

- [`supervisor.py`](../../../../coworker/hosted/supervisor.py) runs one loopback engine per enabled account, caps enabled engines at 20, uses fresh ports/tokens on restart, and applies bounded backoff. Homes come from the account database. Private directories reject symlinks/junctions; logs reject hard links. Windows homes receive explicit operator/System/Administrators ACLs. An allowlist of runtime environment variables prevents operator model credentials and plugin paths from entering engines.
- [`windows.py`](../../../../coworker/sandbox/providers/windows.py), [`winsec.py`](../../../../coworker/sandbox/winsec.py), and [`winrestrict.py`](../../../../coworker/sandbox/runner/winrestrict.py) implement hosted sandbox launches under the existing two network accounts with a unique logon SID per sandbox. The trusted bootstrap stays suspended while its process, thread, token, and desktop are protected and its roots are granted. It starts the runner with read AND write token restrictions, with no weaker launch fallback. Descendants inherit its restricted token and kill-on-close job.
- Hosted root/pipe grants name the unique logon, not the shared account. OWNER RIGHTS entries suppress account ownership's implicit WRITE_DAC. Credentials, home, temp, cache, and configuration are private to the sandbox. A named operator-only mutex serializes ACL mutations across engines; a controller lease prevents the stale-folder reaper from deleting a sandbox during startup. Closing one sandbox removes its grants without revoking another sandbox's grants.
- [`selection.py`](../../../../coworker/sandbox/selection.py) and [`workspace.py`](../../../../coworker/sandbox/workspace.py) forbid `direct`, `runner-local`, and overriding the administrator's hosted provider. Workspace roots, credential sources, and tool folders are checked before use. Provider availability is checked before tool calls.
- [`manager.py`](../../../../coworker/server/manager.py), [`store.py`](../../../../coworker/skills/store.py), and [`credentials.py`](../../../../coworker/sandbox/credentials.py) revalidate saved workspaces, extra roots, scheduled/manual workspaces, skill scopes, and artifacts. Artifact scans/listings prune foreign junctions; downloads/previews reject hard links when a base directory is configured. Hosted credential copying validates each descendant and rejects hard links. Sandbox startup/error events now finish the original scheduled run as an error rather than reporting success or leaving a running record behind.

## Executed verification

Environment: Windows 11 (10.0.26200), Python 3.14.2, SQLite 3.50.4, repository `.venv`.

Focused coverage includes [`test_hosted_supervisor.py`](../../../../tests/test_hosted_supervisor.py), [`test_hosted_boundaries.py`](../../../../tests/test_hosted_boundaries.py), [`test_hosted_windows_provider.py`](../../../../tests/test_hosted_windows_provider.py), and [`test_windows_hosted_launch.py`](../../../../tests/test_windows_hosted_launch.py). These use mocked process/native launch APIs where necessary; they do not prove OS enforcement. [`test_hosted_acceptance_helpers.py`](../../../../tests/test_hosted_acceptance_helpers.py) exercises the local model fixture through the real provider SDK, including streamed tool calls.

The related regression suite covers hosted accounts/gateway, automation, base-directory boundaries, sandbox runner/selection/settings/lifetime/credentials/toolchains/setup, Windows WFP layouts, session construction, and skills. Windows portability corrections cover junction creation without symlink elevation, local DST simulation without `time.tzset`, a platform-specific OpenShell availability fixture, and a shell-startup timing assumption.

Reproduce the related regression run:

```powershell
$phase2Tests = @(
  'tests/test_hosted_accounts.py', 'tests/test_hosted_web.py',
  'tests/test_hosted_supervisor.py', 'tests/test_hosted_boundaries.py',
  'tests/test_hosted_windows_provider.py', 'tests/test_windows_hosted_launch.py',
  'tests/test_windows_restricted_bootstrap.py', 'tests/test_hosted_windows_live.py',
  'tests/test_hosted_acceptance_helpers.py', 'tests/test_base_dir.py',
  'tests/test_automation.py', 'tests/test_automation_create.py',
  'tests/test_sandbox_selection.py', 'tests/test_sandbox_tools.py',
  'tests/test_sandbox_runner.py', 'tests/test_sandbox_windows.py',
  'tests/test_sandbox_credentials.py', 'tests/test_sandbox_toolchains.py',
  'tests/test_sandbox_settings.py', 'tests/test_sandbox_setup_job.py',
  'tests/test_sandbox_lifetime.py', 'tests/test_session_socket_sandbox_build.py',
  'tests/test_windows_wfp_layout.py', 'tests/test_skills_store.py',
  'tests/test_skills_sessions.py', 'tests/test_skills_api.py'
)
.\.venv\Scripts\python.exe -m pytest @phase2Tests -q -rs
```

Result on 2026-10-02: **288 passed, 40 skipped in 46.18s**, no failures. The skips comprise the two opt-in hosted Windows acceptance cases, the restricted-token smoke test blocked by window-station permissions, 12 existing Windows provider/setup cases lacking prerequisites or setup opt-in, 20 Unix-socket tool cases, one bash-only runner case, three platform-specific credential cases, and one symlink-privilege case. Source compilation and `git diff --check` also passed.

## Blocked live acceptance

1. Windows sandbox setup is absent on this PC. The repaired elevation launcher reached UAC, but Windows reported that the prompt was canceled. Setup did not complete; no enforcing sandbox accounts/rules were verified. The user requested no setup retry in this session.
2. This execution context denies `CreateWindowStation` with access denied (error 5). The native restricted-token smoke test explicitly skips for this host limitation, before exercising the restricted child launch.

Consequently, Windows concurrent sandbox isolation, pipe/process takeover denial, private credential enforcement, read-only roots, engine listener isolation, scheduling without a browser/after logout, crash recovery, and account-disable cleanup remain unverified. A passing mocked test is not evidence for these checks. Seatbelt/macOS enforcement also remains unverified. Linux evidence is recorded below.

[`test_hosted_windows_live.py`](../../../../tests/test_hosted_windows_live.py) is the explicit acceptance gate. It uses real Windows providers and real gateway engine subprocesses, SQLite task stores, and a deterministic loopback model endpoint (no paid model/key). It performs native shell/file/git/search checks, cross-account HTTP/WebSocket/artifact probes, scheduled marker writes before login and after logout, actual process-kill recovery/token rotation/catch-up, listener checks, and disable/cleanup checks.

Run the gate in a Windows context permitted to create window stations, after the one-time sandbox setup has completed. Opting in makes missing prerequisites fail the gate instead of silently skipping:

```powershell
$env:OPENWORKER_TEST_HOSTED_WINDOWS = '1'
try {
  .\.venv\Scripts\python.exe -m pytest tests/test_hosted_windows_live.py -v
} finally {
  Remove-Item Env:OPENWORKER_TEST_HOSTED_WINDOWS
}
```

## Linux implementation and verification

Linux private engines use the enforcing OpenShell provider. The supervisor now assigns private `TMPDIR` and `XDG_RUNTIME_DIR` directories and tightens the managed homes directory to mode `0700`. Added supervisor tests verify private runtime/configuration, removal of operator credentials, reuse of the operator gateway link after restart, and refusal of missing, occupied, or replaced OpenShell configuration. Engines receive a link to the operator's OpenShell configuration for trusted CLI/gRPC calls; that configuration is absent from sandbox mounts.

Live VM testing exposed two gaps fixed in this change. OpenShell requires a bind-mount source to exist before sandbox startup: agent construction now creates its read-only tool-output directory, validating hosted ownership first. Hosted artifact reads/listings/downloads now reject unknown session IDs instead of falling back to the account's default workspace. New boundary tests cover both fixes and preserve desktop artifact behavior.

[`test_hosted_linux_live.py`](../../../../tests/test_hosted_linux_live.py) adds an explicit Linux gate. It checks two simultaneously resident real sandboxes, file/shell/git/search tools, peer home/state/credential denial, operator gateway key absence, read-only roots, distinct container PID namespaces, per-registry cleanup, and continued peer operation after one sandbox closes. [`hosted_acceptance.py`](../../../../tests/hosted_acceptance.py) shares the deterministic model and real-engine lifecycle scenario with Windows, including scheduled work before login and after logout, actual crash recovery/token rotation/catch-up, loopback/token enforcement, cross-account API/WebSocket/artifact probes, and account disable. The Linux wrapper additionally checks sandbox cleanup after gateway shutdown.

Initial related regression runs passed **318 tests with 40 skips** locally (Linux x86_64/Python 3.12.3) and on the VM before the live fixes. After the runtime changes, the local focused suite passed **62 tests in 3.97s**; after the artifact fix, hosted/desktop artifact, temporary-workspace, team-artifact, and fixture coverage passed **36 tests in 5.90s**.

The supplied `Ubuntu_26_04_Server` VM was identified by its exact VirtualBox name and matching bridged-adapter MAC, then accessed as `ubuntu@10.42.0.248` using `LINUX_VM_TEST_CREDENTIALS` from `.env` without printing or copying the credential. Observed environment: **Ubuntu 26.04.1 LTS, kernel 7.0.0-34-generic, Python 3.14.4, SQLite 3.46.1, 4 vCPUs, about 7.4 GiB RAM**. The real Landlock ABI probe returned available. Source and a private Python environment with development/OpenShell dependencies reside at `/home/ubuntu/openworker-phase2-20261002`; `.env` was excluded from the source copy.

After the user authorized installation, installed **Docker 29.1.3**, **OpenShell 0.0.116**, `python3-venv`, Git, curl, and CA certificates. Added `ubuntu` to the Docker group, enabled Docker and user linger, refreshed the user manager, enabled gateway bind mounts, registered the operator's mTLS client, and pulled the pinned base image `ghcr.io/nvidia/openshell-community/sandboxes/base@sha256:aeef1c63f00e2913ea002ccb3aaf925f338b5c5d70e63576f0d95c16a138044e`. The gateway is an active user service and preflight reports version 0.0.116.

The Linux live gate passed on 2026-10-02: **2 passed in 43.50s**, no skips. It used real OpenShell containers, two real private engines, real SQLite stores, and only a deterministic loopback model fixture. This proves the concurrent boundaries and engine lifecycle checks described above, including successful scheduled file-tool execution before login, after logout, and after a killed engine's catch-up restart. Both engine ports refused the VM's non-loopback address; unauthenticated loopback requests returned 401. After the gate, no test engine processes or Docker containers remained. Docker and the operator gateway remain installed and running. Output is retained at `/home/ubuntu/openworker-phase2-20261002/phase2-live.log`.

Final related regression run on the VM: **359 passed, 40 skipped in 45.97s**, no failures. It uses the regression file list above, adding `test_sandbox_openshell.py`, `test_hosted_linux_live.py`, `test_tool_result_cap.py`, `test_compaction_transcript.py`, `test_artifact_walk.py`, `test_temp_workspace.py`, and `test_team_file_artifacts.py`, with `.venv/bin/python -m pytest ... -q -rs`. The 40 skips are Windows platform/setup cases, the separately executed Linux gate, and opt-in OpenShell/macOS gates. Output is retained at `/home/ubuntu/openworker-phase2-20261002/phase2-regression.log`. Source compilation and `git diff --check` passed.

A real-gateway probe before OpenShell installation verified **HTTP 503 for API/session creation/artifact requests, WebSocket close 1013, zero engines launched, and no execution fallback**. Its script and output are retained at `/home/ubuntu/openworker-phase2-20261002/failclosed_probe.py` and `phase2-failclosed.log`. The opted-in Linux gate also failed on missing OpenShell before installation, establishing prerequisite refusal. The shared lifecycle fixture now uses absolute `wss://phase2.example.test` URLs so secure cookies reach the gateway, consumes the engine's initial ready event, and distinguishes an Alice-local system prompt from Bob's scheduled conversation history.

The Linux gate exercises the platform's default `allowlist` network profile. The pre-existing OpenShell `open` profile is unsupported by pinned 0.0.116: its wildcard host/zero port is rejected, and this version has no unrestricted-network policy setting. Selecting it fails sandbox startup; no execution fallback occurs. Configure explicit allowed destinations for Linux deployments. This gate does not establish unrestricted network support, public HTTPS deployment, real-browser product flows, or Windows/macOS native acceptance.

Reproduce from the VM source directory:

```bash
OPENWORKER_TEST_HOSTED_LINUX=1 .venv/bin/python -m pytest \
  tests/test_hosted_linux_live.py -v \
  --basetemp "$HOME/.cache/openworker-hosted-linux-acceptance"
```

The dedicated pytest base directory must be outside `/tmp` because an OpenShell gateway with `PrivateTmp=true` cannot bind-mount host `/tmp` paths. Opting in makes missing prerequisites fail the gate.

## Security scope

The gateway and private engines share the operator's OS identity; these changes do not contain a backend code-execution compromise. The Windows restricting list includes Everyone and Builtin Users so the public Windows runtime remains reachable. Managed homes and private sandbox runtime folders exclude those broad grants. Public files accessible to ordinary local users remain accessible; this is not a claim that every filesystem location outside a workspace is blocked. Windows's `open` network profile permits local/network connections, so engine-token authentication remains required. The Linux gate passed; the Windows native gate must still pass before the overall phase can be marked complete.
