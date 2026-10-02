"""Explicit native Windows acceptance gate. No mocked engines or providers.

Run OPENWORKER_TEST_HOSTED_WINDOWS=1 after setup, from a context permitted to
create window stations. Missing prerequisites FAIL this opted-in gate.
The only fake is a loopback model endpoint; no paid provider or API key is used.
"""
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32" or os.environ.get("OPENWORKER_TEST_HOSTED_WINDOWS") != "1",
                               reason="opt-in native Windows hosted acceptance gate")


@pytest.fixture
def usable_windows():
    from coworker.sandbox import winsec
    from coworker.sandbox.providers.windows import preflight

    preflight()
    desktop = winsec.Desktop(winsec.logon_sid())
    desktop.close()


def test_concurrent_native_sandboxes_enforce_private_roots_and_cleanup(tmp_path, monkeypatch, usable_windows):
    from coworker.agents.base import AgentContext
    from coworker import catalog
    from coworker.sandbox.bundle import build_runner_zipapp
    from coworker.sandbox.credentials import Grant
    from coworker.sandbox.providers.windows import WindowsProvider
    from coworker.sandbox.workspace import RunnerWorkspace
    from coworker.sandbox.winsec import protect_directory

    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    monkeypatch.setenv("COWORKER_API_TOKEN", "operator-engine-token-must-not-cross")
    monkeypatch.setenv("OPENAI_API_KEY", "operator-key-must-not-cross")
    homes = tmp_path / "homes"
    homes.mkdir()
    protect_directory(str(homes))
    bundle = build_runner_zipapp(tmp_path / "runner")
    sandboxes = []
    try:
        for name in ("alice", "bob"):
            home = homes / name
            project, reference, state = home / "workspace", home / "reference", home / "state"
            for folder in (project, reference, state):
                folder.mkdir(parents=True, exist_ok=True)
            protect_directory(str(home))
            (project / "own.txt").write_text(name)
            (reference / "read.txt").write_text("read only")
            (state / "secret.txt").write_text(name + " private secret")
            credential = state / "credential.txt"
            credential.write_text(name + " credential")
            monkeypatch.setenv("OPENWORKER_BASE_DIR", str(home))
            provider = WindowsProvider(roots=[{"path": str(project), "writable": True}, {"path": str(reference), "writable": False}],
                                       cwd=project, runner_path=bundle, network=False,
                                       credentials=[Grant("custom", "Custom", str(credential), "credential.txt", kind="file")])
            workspace = RunnerWorkspace(provider, cwd=project)
            sandboxes.append((workspace, provider, project, reference, state))
        for index, (workspace, provider, project, reference, state) in enumerate(sandboxes):
            other = sandboxes[1 - index]
            tools = {tool.__name__: tool for tool in catalog.expand(["code_files", "git", "search"],
                     AgentContext(workspace=project, executor=workspace.executor, sandbox=workspace))}
            name = "alice" if index == 0 else "bob"
            assert name in tools["read_file"]("own.txt")["content"]
            tools["write_file"]("written.txt", "through file tool")
            assert (project / "written.txt").read_text() == "through file tool"
            assert tools["grep"]("alice" if index == 0 else "bob")["matches"]
            assert workspace.executor.run("git init -q")["exit_code"] == 0
            assert "error" not in tools["git_status"]()
            own_credential = Path(provider._dir, "home", "credential.txt")
            result = workspace.executor.run(f"Get-Content -LiteralPath '{own_credential}' -ErrorAction Stop")
            assert result["exit_code"] == 0 and name + " credential" in result["output"]
            assert workspace.executor.run(f"Get-Content -LiteralPath '{reference / 'read.txt'}'")["exit_code"] == 0
            assert workspace.executor.run(f"Set-Content -LiteralPath '{reference / 'blocked.txt'}' -Value nope")["exit_code"] != 0
            for secret in (state / "secret.txt", other[2] / "own.txt", other[4] / "secret.txt", Path(other[1]._dir) / "launch.json",
                           Path(other[1]._dir, "home", "credential.txt")):
                denied = workspace.executor.run(f"Get-Content -LiteralPath '{secret}' -ErrorAction Stop")
                assert denied["exit_code"] != 0, denied
            # Native denial, independent of file-tool argument validation.
            result = workspace.executor.run(f"Set-Content -LiteralPath '{other[2] / 'attack.txt'}' -Value attack -ErrorAction Stop")
            assert result["exit_code"] != 0 and not (other[2] / "attack.txt").exists()
            assert workspace.hello["home"] == str(Path(provider._dir, "home"))
            assert workspace.executor.run("$env:COWORKER_API_TOKEN")["output"].strip() == ""
            assert workspace.executor.run("$env:OPENAI_API_KEY")["output"].strip() == ""
            # Same-account ownership cannot open the peer's pipe or take over
            # its unrestricted bootstrap through WRITE_DAC / VM_WRITE.
            probe = (
                "import ctypes; from ctypes import wintypes; "
                "k=ctypes.WinDLL('kernel32',use_last_error=True); "
                "k.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]; "
                "k.CreateFileW.restype=wintypes.HANDLE; "
                f"h=k.CreateFileW({other[1].socket_path!r},0xC0000000,0,None,3,0,None); "
                "assert h==wintypes.HANDLE(-1).value and ctypes.get_last_error()==5; "
                "k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]; k.OpenProcess.restype=wintypes.HANDLE; "
                f"assert not k.OpenProcess(0x40000|0x20|0x2,False,{other[1]._daemon.pid}); "
                "assert ctypes.get_last_error()==5; print('peer objects denied')"
            )
            result = workspace.executor.run(f"& '{sys.executable}' -I -S -c '" + probe.replace("'", "''") + "'")
            assert result["exit_code"] == 0 and "peer objects denied" in result["output"], result
        assert sandboxes[0][1].session_sid != sandboxes[1][1].session_sid
        sandboxes[0][0].close()
        alive = sandboxes[1][0].executor.run("Set-Content still-alive.txt yes; Get-Content still-alive.txt")
        assert alive["exit_code"] == 0 and "yes" in alive["output"]
    finally:
        for workspace, *_ in sandboxes:
            if workspace is not sandboxes[0][0] or sandboxes[0][1]._daemon is not None:
                workspace.close()


def test_real_engines_run_without_browser_recover_and_disable(tmp_path, usable_windows):
    from hosted_acceptance import exercise_real_engines

    exercise_real_engines(tmp_path, "windows")
