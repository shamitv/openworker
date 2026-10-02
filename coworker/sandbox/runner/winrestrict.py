"""Trusted Windows bootstrap. No protocol or agent code runs in this process.

The controller starts it suspended under the network account, confines its
process/desktop to this logon, and grants this logon its roots. This bootstrap
then starts the runner under a full (read AND write) restricted token. All
descendants inherit that token and the controller's kill-on-close job.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes


def run(config_path: str, log_path: str | None = None) -> int:
    from .winpipe import _SecurityAttributes

    if log_path:
        # Launch the trusted Python bootstrap directly. An unrestricted cmd
        # intermediary would create children with the account's default DACL.
        # These handles are created after the controller confines the logon.
        import msvcrt

        with open(log_path, "w") as log, open(os.devnull, "r") as stdin:
            for fd, source in ((0, stdin), (1, log), (2, log)):
                os.dup2(source.fileno(), fd, inheritable=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
        for kind, fd in ((0xFFFFFFF6, 0), (0xFFFFFFF5, 1), (0xFFFFFFF4, 2)):
            if not kernel.SetStdHandle(kind, msvcrt.get_osfhandle(fd)):
                raise ctypes.WinError(ctypes.get_last_error())
        sys.stdout = open(os.dup(1), "w", encoding="utf-8", buffering=1)
        sys.stderr = open(os.dup(2), "w", encoding="utf-8", buffering=1)

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class SidEntry(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    class DefaultDacl(ctypes.Structure):
        _fields_ = [("Dacl", ctypes.c_void_p)]

    class Startup(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("reserved", wintypes.LPWSTR), ("desktop", wintypes.LPWSTR), ("title", wintypes.LPWSTR),
                    *[(name, wintypes.DWORD) for name in ("x", "y", "xs", "ys", "xc", "yc", "fill", "flags")],
                    ("show", wintypes.WORD), ("reserved2", wintypes.WORD), ("reservedptr", ctypes.c_void_p),
                    ("stdin", wintypes.HANDLE), ("stdout", wintypes.HANDLE), ("stderr", wintypes.HANDLE)]

    class ProcessInfo(ctypes.Structure):
        _fields_ = [("process", wintypes.HANDLE), ("thread", wintypes.HANDLE), ("pid", wintypes.DWORD), ("tid", wintypes.DWORD)]

    def checked(ok, label):
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error(), label)

    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    adv.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    adv.CreateRestrictedToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(SidEntry), ctypes.POINTER(wintypes.HANDLE)]
    adv.SetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    adv.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
    adv.SetKernelObjectSecurity.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p]
    adv.CreateProcessAsUserW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                       wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(Startup), ctypes.POINTER(ProcessInfo)]
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    # Everyone/Users permit the Windows runtime's public objects. Managed homes and
    # private runtime directories exclude Everyone, Users, and account-wide ACEs.
    security = _SecurityAttributes([config["operator"], config["sid"], "S-1-5-18"])
    original, restricted = wintypes.HANDLE(), wintypes.HANDLE()
    sids = []
    child = ProcessInfo()
    try:
        checked(adv.OpenProcessToken(kernel.GetCurrentProcess(), 0xF01FF, ctypes.byref(original)), "OpenProcessToken")
        checked(adv.SetKernelObjectSecurity(original, 4, security._descriptor), "protect bootstrap token")
        for value in (config["sid"], "S-1-1-0", "S-1-5-32-545"):
            sid = ctypes.c_void_p()
            checked(adv.ConvertStringSidToSidW(value, ctypes.byref(sid)), "ConvertStringSidToSid")
            sids.append(sid)
        entries = (SidEntry * len(sids))(*(SidEntry(sid, 0) for sid in sids))
        # DISABLE_MAX_PRIVILEGE, deliberately WITHOUT WRITE_RESTRICTED.
        checked(adv.CreateRestrictedToken(original, 1, 0, None, 0, None, len(entries), entries, ctypes.byref(restricted)), "CreateRestrictedToken")
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
        checked(adv.GetSecurityDescriptorDacl(security._descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)), "GetSecurityDescriptorDacl")
        default = DefaultDacl(dacl)
        checked(adv.SetTokenInformation(restricted, 6, ctypes.byref(default), ctypes.sizeof(default)), "TokenDefaultDacl")
        checked(adv.SetKernelObjectSecurity(restricted, 4, security._descriptor), "protect runner token")
        startup = Startup()
        startup.cb = ctypes.sizeof(startup)
        startup.desktop = config["desktop"]
        startup.flags = 0x100
        startup.stdin = kernel.GetStdHandle(0xFFFFFFF6)
        startup.stdout = kernel.GetStdHandle(0xFFFFFFF5)
        startup.stderr = kernel.GetStdHandle(0xFFFFFFF4)
        block = ctypes.create_unicode_buffer("\0".join(f"{key}={value}" for key, value in sorted(config["env"].items())) + "\0\0")
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(config["argv"]))
        checked(adv.CreateProcessAsUserW(restricted, None, command, security.pointer, security.pointer, True,
                                         0x400 | 0x08000000, block, config["cwd"], ctypes.byref(startup), ctypes.byref(child)), "CreateProcessAsUser restricted runner")
        kernel.CloseHandle(child.thread)
        kernel.WaitForSingleObject(child.process, 0xFFFFFFFF)
        code = wintypes.DWORD()
        checked(kernel.GetExitCodeProcess(child.process, ctypes.byref(code)), "GetExitCodeProcess")
        return code.value
    finally:
        for handle in (child.process, restricted, original):
            if handle:
                kernel.CloseHandle(handle)
        for sid in sids:
            kernel.LocalFree(sid)
        security.close()
