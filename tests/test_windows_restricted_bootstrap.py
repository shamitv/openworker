"""Win32 launcher smoke test, without installing sandbox accounts or changing policy.

This validates token plumbing only; it is not the hosted enforcement gate.
"""
import json
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows token API")
def test_bootstrap_starts_child_with_read_and_write_restrictions(tmp_path):
    from coworker.sandbox import winsec

    try:
        desktop = winsec.Desktop(winsec.logon_sid())
    except OSError as exc:
        if exc.errno == 5:
            pytest.skip("host execution context denies CreateWindowStation; requires an unrestricted Windows test host")
        raise
    try:
        config = tmp_path / "launch.json"
        # GetTokenInformation(TokenRestrictedSids): the array's count is first.
        script = (
            "import ctypes; from ctypes import wintypes; "
            "a=ctypes.WinDLL('advapi32',use_last_error=True); k=ctypes.WinDLL('kernel32'); "
            "k.GetCurrentProcess.restype=wintypes.HANDLE; "
            "a.OpenProcessToken.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE)]; "
            "a.GetTokenInformation.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]; "
            "t=wintypes.HANDLE(); assert a.OpenProcessToken(k.GetCurrentProcess(),8,ctypes.byref(t)); "
            "n=wintypes.DWORD(); a.GetTokenInformation(t,11,None,0,ctypes.byref(n)); "
            "b=ctypes.create_string_buffer(n.value); assert a.GetTokenInformation(t,11,b,n,ctypes.byref(n)); "
            "print('restricting_sids='+str(wintypes.DWORD.from_buffer(b).value))"
        )
        config.write_text(json.dumps({
            "operator": winsec.current_user_sid(), "sid": winsec.logon_sid(),
            "desktop": desktop.name, "cwd": str(tmp_path),
            "argv": [sys.executable, "-I", "-S", "-c", script],
            "env": {key: value for key, value in __import__("os").environ.items()
                    if key.upper() in ("SYSTEMROOT", "WINDIR", "PATH", "COMSPEC")},
        }))
        result = subprocess.run([sys.executable, "-m", "coworker.sandbox.runner", "restricted-serve", "--config", str(config)],
                                capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert "restricting_sids=3" in result.stdout
    finally:
        desktop.close()
