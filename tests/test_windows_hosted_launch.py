"""Mocked Win32 API ordering and failures; no native isolation claims."""
import ctypes
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 ctypes structures")


class Function:
    def __init__(self, callback=None, value=1):
        self.callback, self.value = callback, value
    def __call__(self, *args):
        return self.callback(*args) if self.callback else self.value


def test_suspended_logon_confines_process_thread_and_token_before_resume(monkeypatch):
    from coworker.sandbox import winsec

    events = []
    def create(*args):
        info = args[-1]._obj
        info.hProcess, info.hThread, info.dwProcessId = 101, 102, 10
        assert args[6] & winsec.CREATE_SUSPENDED
        events.append("created-suspended")
        return 1
    def open_token(process, access, pointer):
        assert access & 0x40000  # WRITE_DAC before the bootstrap can execute
        pointer._obj.value = 103
        return 1
    adv = SimpleNamespace(CreateProcessWithLogonW=Function(create), OpenProcessToken=Function(open_token),
                          SetKernelObjectSecurity=Function(lambda handle, *_: events.append(("protect", handle.value if hasattr(handle, "value") else handle)) or 1))
    kernel = SimpleNamespace(CreateJobObjectW=Function(value=104), SetInformationJobObject=Function(),
                             AssignProcessToJobObject=Function(lambda *_: events.append("job") or 1),
                             ResumeThread=Function(lambda *_: events.append("resume") or 0),
                             CloseHandle=Function(), LocalFree=Function(), TerminateProcess=Function())
    group = winsec.SID_AND_ATTRIBUTES(123, 0)
    buffer = ctypes.create_string_buffer(ctypes.sizeof(ctypes.c_void_p) + ctypes.sizeof(group))
    ctypes.memmove(ctypes.addressof(buffer) + ctypes.sizeof(ctypes.c_void_p), ctypes.byref(group), ctypes.sizeof(group))
    monkeypatch.setattr(winsec, "_adv", adv)
    monkeypatch.setattr(winsec, "_k32", kernel)
    monkeypatch.setattr(winsec, "_token_info", lambda *_: buffer)
    monkeypatch.setattr(winsec, "_sid_text", lambda *_: "S-1-5-5-1-2")
    monkeypatch.setattr(winsec, "current_user_sid", lambda: "S-1-5-21-1")
    monkeypatch.setattr(winsec, "_descriptor", lambda text: ctypes.c_void_p(123))
    desktop = SimpleNamespace(name="station\\default", confine=lambda sid: events.append("desktop"))
    process = winsec.spawn_as_account(["python.exe", "trusted.pyz"], account="account", password="unused",
                                     desktop=desktop, cwd="C:/Windows", environment={"HOME": "private"},
                                     before_resume=lambda sid: events.append("grants"))
    assert events == ["created-suspended", "job", ("protect", 101), ("protect", 102), ("protect", 103), "desktop", "grants", "resume"]
    process.close()
    events.clear()
    adv.SetKernelObjectSecurity = Function(value=0)
    monkeypatch.setattr(winsec, "_fail", lambda _: OSError("blocked"))
    kernel.TerminateProcess = Function(lambda *_: events.append("terminate") or 1)
    with pytest.raises(OSError, match="blocked"):
        winsec.spawn_as_account(["python.exe"], account="account", password="unused", desktop=desktop,
                                cwd="C:/Windows", before_resume=lambda _: pytest.fail("must not grant after failure"))
    assert "terminate" in events and "resume" not in events


@pytest.mark.parametrize("fail_launch", [False, True])
def test_bootstrap_uses_full_restrictions_and_never_falls_back(tmp_path, monkeypatch, fail_launch):
    from coworker.sandbox.runner import winpipe, winrestrict

    events, restrictions = [], []
    def token(process, access, pointer):
        pointer._obj.value = 100
        return 1
    def sid(text, pointer):
        restrictions.append(text)
        pointer._obj.value = len(restrictions)
        return 1
    def restrict(original, flags, disabled, _, privileges, __, count, entries, pointer):
        assert flags == 1 and disabled == privileges == 0 and count == 3
        pointer._obj.value = 101
        events.append("restricted")
        return 1
    def create(*args):
        assert args[0].value == 101
        events.append("launch")
        if fail_launch:
            return 0
        info = args[-1]._obj
        info.process, info.thread, info.pid = 200, 201, 202
        return 1
    def exit_code(handle, pointer):
        pointer._obj.value = 0
        return 1
    adv = SimpleNamespace(OpenProcessToken=Function(token), ConvertStringSidToSidW=Function(sid),
                          CreateRestrictedToken=Function(restrict), SetTokenInformation=Function(lambda *_: events.append("default-dacl") or 1),
                          GetSecurityDescriptorDacl=Function(), SetKernelObjectSecurity=Function(), CreateProcessAsUserW=Function(create))
    kernel = SimpleNamespace(GetCurrentProcess=Function(value=99), CloseHandle=Function(), LocalFree=Function(),
                             GetStdHandle=Function(value=5), WaitForSingleObject=Function(value=0), GetExitCodeProcess=Function(exit_code))
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **_: adv if name == "advapi32" else kernel)
    monkeypatch.setattr(winpipe, "_SecurityAttributes", lambda _: SimpleNamespace(_descriptor=ctypes.c_void_p(1), pointer=1, close=lambda: None))
    config = tmp_path / "launch.json"
    config.write_text(json.dumps({"operator": "operator", "sid": "S-1-5-5-1-2", "desktop": "desktop",
                                  "cwd": str(tmp_path), "env": {}, "argv": ["python.exe", "runner.pyz"]}))
    if fail_launch:
        with pytest.raises(OSError):
            winrestrict.run(str(config))
    else:
        assert winrestrict.run(str(config)) == 0
    assert restrictions == ["S-1-5-5-1-2", "S-1-1-0", "S-1-5-32-545"]
    assert events == ["restricted", "default-dacl", "launch"]


def test_reaper_keeps_starting_sandbox_with_lease(tmp_path, monkeypatch):
    import msvcrt
    from coworker.sandbox.providers import windows_setup
    from coworker.sandbox.runner import winpipe

    monkeypatch.setattr(windows_setup, "SANDBOXES", tmp_path)
    monkeypatch.setattr(winpipe, "wait_ready", lambda *_: False)
    folder = tmp_path / "owr-starting"
    folder.mkdir()
    with open(folder / ".lease", "w+b") as lease:
        lease.write(b"1")
        lease.flush()
        lease.seek(0)
        msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
        assert windows_setup.reap_private_folders() == []
        assert folder.exists()
    assert windows_setup.reap_private_folders() == [str(folder)]


@pytest.mark.parametrize("output_encoding", ["utf-8", "utf-16"])
def test_elevation_wrapper_preserves_literal_arguments(tmp_path, monkeypatch, output_encoding):
    from coworker.sandbox.providers import windows_setup

    folder = tmp_path / "setup's folder"
    folder.mkdir()
    monkeypatch.setattr(windows_setup.tempfile, "mkdtemp", lambda **_: str(folder))
    def launch(argv, **kwargs):
        wrapper = (folder / "elevated.ps1").read_text(encoding="utf-8-sig")
        assert "'a''b & $value'" in wrapper
        assert "*> '" in wrapper and "exit $LASTEXITCODE" in wrapper
        assert "-Verb RunAs" in argv[-1] and "-WindowStyle Hidden" in argv[-1]
        assert "setup''s folder" in argv[-1]
        (folder / "out.txt").write_text("captured", encoding=output_encoding)
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(windows_setup.subprocess, "run", launch)
    result = windows_setup._powershell("Write-Output 'ok'", ["-Name", "a'b & $value"], elevate=True)
    assert result.returncode == 0 and result.stdout == "captured"
    assert not folder.exists()


@pytest.mark.parametrize("wait_result", [0, 0x80, 258])
def test_acl_mutations_are_serialized_and_timeout_refuses(monkeypatch, wait_result):
    from coworker.sandbox import winsec

    events = []
    kernel = SimpleNamespace(CreateMutexW=Function(value=10), LocalFree=Function(),
                             WaitForSingleObject=Function(value=wait_result),
                             ReleaseMutex=Function(lambda *_: events.append("release") or 1),
                             CloseHandle=Function(lambda *_: events.append("close") or 1))
    monkeypatch.setattr(winsec, "_k32", kernel)
    monkeypatch.setattr(winsec, "_descriptor", lambda _: ctypes.c_void_p(1))
    monkeypatch.setattr(winsec, "current_user_sid", lambda: "operator")
    monkeypatch.setattr(winsec, "_change_dacl_locked", lambda *_: events.append("mutate"))
    if wait_result == 258:
        with pytest.raises(OSError, match="timed out"):
            winsec._change_dacl("path", "sid", 1)
        assert events == ["close"]
    else:
        winsec._change_dacl("path", "sid", 1)
        assert events == ["mutate", "release", "close"]
