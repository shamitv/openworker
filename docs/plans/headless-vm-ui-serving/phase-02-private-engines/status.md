# Phase 2 status

Status: In progress - code and automated coverage implemented; live Windows acceptance blocked.

Updated: 2026-10-02 (Asia/Calcutta). The selected verification target is this native Windows PC. The user requested finishing the code and documenting the blocked live checks instead of retrying setup.

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

Consequently, real concurrent sandbox isolation, pipe/process takeover denial, private credential enforcement, read-only roots, actual engine listener isolation, scheduling without a browser/after logout, recovery after an actual engine kill, and account-disable cleanup remain unverified. A passing mocked test is not evidence for these checks. OpenShell/Linux and Seatbelt/macOS enforcement also remain unverified.

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

## Security scope

The gateway and private engines share the operator's OS identity; these changes do not contain a backend code-execution compromise. The Windows restricting list includes Everyone and Builtin Users so the public Windows runtime remains reachable. Managed homes and private sandbox runtime folders exclude those broad grants. Public files accessible to ordinary local users remain accessible; this is not a claim that every filesystem location outside a workspace is blocked. The `open` network profile permits local/network connections, so engine-token authentication remains required. This hosted token design must pass the native gate before Phase 2 can be marked complete.
