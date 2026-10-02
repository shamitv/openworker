#!/usr/bin/env python3
"""Run a supervised Quick Tunnel and the password-based web gateway on Linux.

Requires cloudflared, the installed Python environment, a built SPA and existing
accounts. Ctrl+C stops both children; rerunning discovers a new public origin.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = re.compile(rb"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.trycloudflare\.com(?![a-z0-9.-])")


class LaunchError(Exception):
    pass


class Stopped(Exception):
    pass


def positive_seconds(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a positive number of seconds")
    return number


def private_file(path: Path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb", buffering=0)


def stop_child(process: subprocess.Popen | None, timeout: float) -> None:
    if process is None:
        return
    # Let the gateway shut down its engines before terminating any leftovers.
    if process.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        process.poll()
        time.sleep(.1)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def run(args: argparse.Namespace) -> int:
    data = args.data_dir.expanduser().resolve()
    spa = args.spa.expanduser().resolve()
    cloudflared = shutil.which(os.path.expanduser(args.cloudflared))
    python = shutil.which(os.path.expanduser(args.python))
    if not cloudflared:
        raise LaunchError("cloudflared is missing. Install it from https://developers.cloudflare.com/tunnel/downloads/ or use --cloudflared PATH.")
    if not python:
        raise LaunchError("Python interpreter is missing; use --python PATH to the installed OpenWorker environment.")
    if not (spa / "index.html").is_file():
        raise LaunchError(f"Built SPA is missing at {spa}; run npm run build in surfaces/gui first.")
    if not (data / "accounts.sqlite3").is_file():
        raise LaunchError(f"No account database at {data}. Create an account with openworker-web --data-dir '{data}' user create admin first.")

    logs = data / "quick-tunnel"
    logs.mkdir(mode=0o700, exist_ok=True)
    logs.chmod(0o700)
    lock_fd = os.open(logs / "launcher.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "r+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LaunchError(f"A launcher already uses {data}. Stop it before restarting.") from None
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", args.port))
            except OSError as error:
                raise LaunchError(f"Loopback port {args.port} is unavailable: {error}") from None
        directory = Path(tempfile.mkdtemp(prefix="run-", dir=logs))
        print(f"Logs: {directory}", flush=True)
        return supervise(args, python, cloudflared, data, spa, directory)


def supervise(args, python: str, cloudflared: str, data: Path, spa: Path, directory: Path) -> int:
    stopped = threading.Event()
    received_signal = 0
    children: list[tuple[str, subprocess.Popen]] = []

    def request_stop(signum, _frame):
        nonlocal received_signal
        if not received_signal:
            received_signal = signum
        stopped.set()

    def check():
        if stopped.is_set():
            raise Stopped()
        for name, process in children:
            code = process.poll()
            if code is not None:
                raise LaunchError(f"{name} exited with status {code}; see {directory}.")

    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {sig: signal.signal(sig, request_stop) for sig in signals}
    local_origin = f"http://127.0.0.1:{args.port}"
    try:
        with private_file(directory / "cloudflared.log") as tunnel_log, private_file(directory / "gateway.log") as gateway_log:
            check()
            tunnel = subprocess.Popen(
                [cloudflared, "tunnel", "--no-autoupdate", "--url", local_origin],
                stdin=subprocess.DEVNULL, stdout=tunnel_log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            children.append(("cloudflared", tunnel))
            print("Waiting for the Quick Tunnel URL…", flush=True)
            deadline = time.monotonic() + args.tunnel_timeout
            pending = b""
            with (directory / "cloudflared.log").open("rb") as reader:
                while True:
                    check()
                    pending = (pending + reader.read())[-65536:]
                    match = ORIGIN.search(pending)
                    if match:
                        origin = match.group().decode("ascii")
                        break
                    if time.monotonic() >= deadline:
                        raise LaunchError(f"Timed out waiting for the tunnel URL; see {directory / 'cloudflared.log'}.")
                    stopped.wait(.2)
            check()
            with private_file(directory / "public-url.txt") as output:
                output.write((origin + "\n").encode("ascii"))
            print(f"Tunnel URL: {origin}\nStarting OpenWorker…", flush=True)
            gateway = subprocess.Popen(
                [python, "-u", "-m", "coworker.hosted.run", "serve", "--spa", str(spa),
                 "--data-dir", str(data), "--public-origin", origin, "--sandbox-provider", "openshell",
                 "--host", "127.0.0.1", "--port", str(args.port)],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=gateway_log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            children.append(("OpenWorker", gateway))
            # Loopback health must not pass through operator HTTP proxy settings.
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic() + args.startup_timeout
            while True:
                check()
                try:
                    with opener.open(local_origin + "/web/health", timeout=1) as response:
                        body = json.load(response)
                        healthy = response.status == 200 and isinstance(body, dict) and body.get("status") == "ok"
                except (URLError, OSError, ValueError):
                    healthy = False
                check()
                if healthy:
                    break
                if time.monotonic() >= deadline:
                    raise LaunchError(f"Timed out waiting for OpenWorker; see {directory / 'gateway.log'}.")
                stopped.wait(.2)
            print(f"OpenWorker is listening. Open {origin}\nURL file: {directory / 'public-url.txt'}\nPress Ctrl+C to stop. Rerun this command to restart.", flush=True)
            while True:
                check()
                stopped.wait(.5)
    except Stopped:
        print("Stopping OpenWorker and the tunnel…", flush=True)
        return 128 + received_signal
    finally:
        try:
            # Stop the gateway first so its private engines can shut down normally.
            for _, process in reversed(children):
                try:
                    stop_child(process, args.shutdown_timeout)
                except (OSError, subprocess.TimeoutExpired) as error:
                    print(f"Cleanup failed for child {process.pid}: {error}", file=sys.stderr)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".local/share/openworker-web", help="existing account data directory (default: %(default)s)")
    parser.add_argument("--spa", type=Path, default=ROOT / "surfaces/gui/dist", help="built SPA directory (default: %(default)s)")
    default_python = ROOT / ".venv/bin/python"
    parser.add_argument("--python", default=str(default_python) if default_python.exists() else sys.executable, help="installed OpenWorker Python interpreter")
    parser.add_argument("--cloudflared", default="cloudflared", help="cloudflared executable name or path")
    parser.add_argument("--port", type=int, default=8766, help="loopback gateway port (default: %(default)s)")
    parser.add_argument("--tunnel-timeout", type=positive_seconds, default=60, help="seconds to discover the URL (default: %(default)s)")
    parser.add_argument("--startup-timeout", type=positive_seconds, default=600, help="seconds for gateway startup (default: %(default)s)")
    parser.add_argument("--shutdown-timeout", type=positive_seconds, default=30, help="seconds for each child to stop normally (default: %(default)s)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        return run(args)
    except (LaunchError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
