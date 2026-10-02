"""Supervise the private, loopback-only OpenWorker engines behind the web gateway.

The account store is authoritative for user-to-home ownership.  Browser requests
never provide an engine id, port, token, or filesystem path to this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from ..basedir import is_reparse_point


log = logging.getLogger(__name__)

_ENFORCING_PROVIDERS = frozenset({"openshell", "seatbelt", "windows"})
_MAX_ENGINES = 20
_READY_TIMEOUT_SECONDS = 30.0
_RECONCILE_SECONDS = 2.0
_STABLE_UPTIME_SECONDS = 120.0


def _is_link(path: Path) -> bool:
    return is_reparse_point(path)


def _engine_environment() -> dict[str, str]:
    """Only runtime settings cross from the operator into a private engine."""
    allowed = {
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE",
        "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "LANG", "LC_ALL",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "VIRTUAL_ENV",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


@dataclass(frozen=True)
class EngineEndpoint:
    """Private endpoint; ``token`` must only be used on the gateway-to-engine hop."""

    port: int
    token: str


@dataclass
class _Engine:
    process: asyncio.subprocess.Process
    endpoint: EngineEndpoint
    home: Path
    started_at: float


class EngineSupervisor:
    """Own one engine per enabled account and keep it running after browser logout.

    ``store.list_users()`` must return dictionaries with ``id``, ``enabled``, and
    ``home`` fields. Homes are restricted to ``data_dir/homes``; the store remains
    the source of truth, so an ``ensure`` caller cannot select another home.
    """

    def __init__(
        self,
        data_dir: Path,
        store: Any,
        sandbox_provider: str,
        public_origin: str,
    ) -> None:
        provider = sandbox_provider.strip().lower()
        if provider not in _ENFORCING_PROVIDERS:
            raise ValueError(
                "hosted engines require an enforcing sandbox provider: "
                "openshell, seatbelt, or windows"
            )
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.homes_dir = self.data_dir / "homes"
        if _is_link(self.homes_dir):
            raise ValueError("hosted homes directory cannot be a symlink")
        self.store = store
        self.sandbox_provider = provider
        self.public_origin = public_origin.rstrip("/")
        self._engines: dict[str, _Engine] = {}
        self._failures: dict[str, int] = {}
        self._retry_at: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._monitor: asyncio.Task[None] | None = None
        self._stopping = False
        self._provider_checked_at = float("-inf")
        self._provider_problem: str | None = None

    async def start(self) -> None:
        """Start all enabled engines, then watch for crashes and account changes."""
        if self._monitor is not None:
            return
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.homes_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "nt":
            from ..sandbox.winsec import protect_directory

            protect_directory(str(self.homes_dir))
        self._stopping = False
        await self.reconcile()
        self._monitor = asyncio.create_task(self._monitor_loop(), name="openworker-engines")

    async def stop(self) -> None:
        """Stop the watcher and every child when the gateway shuts down."""
        self._stopping = True
        monitor, self._monitor = self._monitor, None
        if monitor is not None:
            monitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor
        async with self._lock:
            for user_id in list(self._engines):
                await self._stop_locked(user_id)

    async def ensure(self, user: dict[str, Any]) -> EngineEndpoint | None:
        """Return the database-owned engine for ``user``, starting it if needed.

        ``None`` means the account is disabled, the sandbox is unavailable, or a
        crashed process is in restart backoff. The caller should return 503 for
        an unavailable enabled engine. A caller-supplied home is never trusted.
        """
        user_id = str(user["id"])
        accounts = self._account_rows()
        enabled = [row for row in accounts.values() if row.get("enabled")]
        if len(enabled) > _MAX_ENGINES:
            raise ValueError(f"hosted gateway supports at most {_MAX_ENGINES} enabled accounts")
        self._validate_unique_homes(enabled)
        canonical = accounts.get(user_id)
        if canonical is None:
            async with self._lock:
                await self._stop_locked(user_id)
            return None
        async with self._lock:
            return await self._ensure_locked(canonical)

    async def reconcile(self) -> None:
        """Apply account changes and restart failed engines with bounded backoff."""
        accounts = self._account_rows()
        enabled = [row for row in accounts.values() if row.get("enabled")]
        if len(enabled) > _MAX_ENGINES:
            raise ValueError(f"hosted gateway supports at most {_MAX_ENGINES} enabled accounts")
        self._validate_unique_homes(enabled)
        async with self._lock:
            for user_id, engine in list(self._engines.items()):
                row = accounts.get(user_id)
                if not row or not row.get("enabled"):
                    await self._stop_locked(user_id)
                    self._failures.pop(user_id, None)
                    self._retry_at.pop(user_id, None)
                    continue
                if engine.home != self._home(row):
                    await self._stop_locked(user_id)
            for row in enabled:
                await self._ensure_locked(row)

    def _account_rows(self) -> dict[str, dict[str, Any]]:
        rows = self.store.list_users()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            user_id = str(row["id"])
            if user_id in result:
                raise ValueError(f"duplicate hosted account id: {user_id}")
            result[user_id] = row
        return result

    def _validate_unique_homes(self, rows: list[dict[str, Any]]) -> None:
        owners: dict[Path, str] = {}
        for row in rows:
            home = self._home(row)
            user_id = str(row["id"])
            previous = owners.setdefault(home, user_id)
            if previous != user_id:
                raise ValueError("two hosted accounts cannot share a home")

    def _home(self, user: dict[str, Any]) -> Path:
        if _is_link(self.homes_dir):
            raise ValueError("hosted homes directory cannot be a reparse point")
        user_id = str(user["id"])
        if not user_id or Path(user_id).name != user_id or user_id in (".", ".."):
            raise ValueError("invalid hosted account id")
        raw_home = Path(str(user["home"])).expanduser()
        expected = self.homes_dir / user_id
        if _is_link(raw_home) or raw_home.absolute() != expected.absolute():
            raise ValueError(f"account {user_id} has an unexpected home path")
        home = raw_home.resolve()
        root = self.homes_dir.resolve()
        if home == root or not home.is_relative_to(root) or home != expected.absolute():
            raise ValueError(f"account {user_id} has a home outside {root}")
        return home

    @staticmethod
    def _child_dir(home: Path, name: str) -> Path:
        raw_child = home / name
        if _is_link(raw_child):
            raise ValueError(f"private {name} directory cannot be a symlink")
        child = raw_child.resolve()
        if child.parent != home or child != raw_child.absolute():
            raise ValueError(f"private {name} directory must stay inside the account home")
        child.mkdir(mode=0o700, parents=True, exist_ok=True)
        child.chmod(0o700)
        return child

    async def _provider_available(self) -> bool:
        now = time.monotonic()
        if now - self._provider_checked_at < 10.0:
            return self._provider_problem is None
        try:
            await asyncio.to_thread(self._preflight)
            problem = None
        except Exception as exc:
            problem = str(exc)
        self._provider_checked_at = time.monotonic()
        if problem != self._provider_problem:
            if problem:
                log.error("hosted sandbox unavailable (%s): %s", self.sandbox_provider, problem)
            else:
                log.info("hosted sandbox available (%s)", self.sandbox_provider)
        self._provider_problem = problem
        return problem is None

    def _preflight(self) -> None:
        if self.sandbox_provider == "openshell":
            from ..sandbox.providers import openshell

            openshell.preflight()
        elif self.sandbox_provider == "seatbelt":
            from ..sandbox.providers import seatbelt

            seatbelt.preflight()
        else:
            from ..sandbox.providers import windows

            windows.preflight()

    async def _ensure_locked(self, user: dict[str, Any]) -> EngineEndpoint | None:
        user_id = str(user["id"])
        if not user.get("enabled") or self._stopping:
            await self._stop_locked(user_id)
            return None
        home = self._home(user)
        existing = self._engines.get(user_id)
        if existing is not None:
            if existing.home != home:
                await self._stop_locked(user_id)
            elif existing.process.returncode is None:
                if time.monotonic() - existing.started_at >= _STABLE_UPTIME_SECONDS:
                    self._failures.pop(user_id, None)
                return existing.endpoint
            else:
                await existing.process.wait()
                self._engines.pop(user_id, None)
                self._failed(user_id, existing.process.returncode)
        if time.monotonic() < self._retry_at.get(user_id, 0.0):
            return None
        if not await self._provider_available():
            self._failed(user_id, "sandbox unavailable")
            return None
        try:
            engine = await self._launch(user_id, home)
        except (OSError, RuntimeError, ValueError) as exc:
            log.error("could not start engine for account %s: %s", user_id, exc)
            self._failed(user_id, exc)
            return None
        self._engines[user_id] = engine
        self._retry_at.pop(user_id, None)
        return engine.endpoint

    def _failed(self, user_id: str, reason: object) -> None:
        count = self._failures.get(user_id, 0) + 1
        self._failures[user_id] = count
        delay = min(60.0, float(2 ** min(count, 6)))
        self._retry_at[user_id] = time.monotonic() + delay
        log.warning("engine for account %s unavailable (%s); retry in %.0fs", user_id, reason, delay)

    async def _launch(self, user_id: str, home: Path) -> _Engine:
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
        home.chmod(0o700)
        if os.name == "nt":
            from ..sandbox.winsec import protect_directory

            protect_directory(str(home))
        state = self._child_dir(home, "state")
        workspace = self._child_dir(home, "workspace")
        self._child_dir(home, "cache")
        config = self._child_dir(home, "config")
        self._child_dir(home, "data")
        if self.sandbox_provider == "openshell":
            # OpenShell's client certificate and active-gateway pointer belong
            # to the VM operator. The provider and CLI look them up beneath
            # XDG_CONFIG_HOME. Give each engine a private XDG tree, with only
            # this machine-level OpenShell configuration linked into it.
            operator_config = Path(
                os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
            ) / "openshell"
            if not operator_config.is_dir():
                raise RuntimeError("OpenShell client configuration is missing")
            operator_config = operator_config.resolve()
            link = config / "openshell"
            if link.is_symlink():
                if link.resolve() != operator_config:
                    raise RuntimeError("OpenShell client configuration link has changed")
            elif link.exists():
                raise RuntimeError("OpenShell client configuration path is occupied")
            else:
                link.symlink_to(operator_config, target_is_directory=True)
        token = secrets.token_hex(32)
        port = self._free_port()
        endpoint = EngineEndpoint(port=port, token=token)
        env = _engine_environment()
        env.update(
            {
                "COWORKER_API_TOKEN": token,
                "COWORKER_STATE_DIR": str(state),
                "COWORKER_STATE_LOCK": "strict",
                "COWORKER_EXIT_WITH_PARENT": "1",
                "COWORKER_PARENT_PID": str(os.getpid()),
                "OPENWORKER_BASE_DIR": str(home),
                "OPENWORKER_SANDBOX_PROVIDER": self.sandbox_provider,
                "OPENWORKER_HEADLESS": "1",
                "OPENWORKER_HOSTED_WEB": "1",
                "OPENWORKER_PUBLIC_ORIGIN": self.public_origin,
                "OPENWORKER_HOSTED_USER_ID": user_id,
                "HOME": str(home),
                "USERPROFILE": str(home),
                "APPDATA": str(home / "config"),
                "LOCALAPPDATA": str(home / "cache"),
                "TEMP": str(home / "cache"),
                "TMP": str(home / "cache"),
                "XDG_CONFIG_HOME": str(home / "config"),
                "XDG_DATA_HOME": str(home / "data"),
                "XDG_CACHE_HOME": str(home / "cache"),
                "PYTHONUNBUFFERED": "1",
            }
        )
        command = [
            sys.executable,
            "-m",
            "coworker.server.run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--cwd",
            str(workspace),
        ]
        log_path = state / "engine.log"
        if _is_link(log_path):
            raise ValueError("private engine log cannot be a reparse point")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(log_path, flags, 0o600)
        try:
            if os.fstat(fd).st_nlink != 1:
                raise ValueError("private engine log cannot be a hard link")
            if os.name != "nt":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "ab", buffering=0) as output:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    env=env,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=output,
                    stderr=asyncio.subprocess.STDOUT,
                )
        except BaseException:
            # The fd belongs to fdopen once it succeeds. If fdopen itself fails,
            # close the raw descriptor here too.
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        try:
            await self._wait_ready(process, endpoint)
        except BaseException:
            await self._terminate(process)
            raise
        log.info("started private engine for account %s on loopback port %d", user_id, port)
        return _Engine(process=process, endpoint=endpoint, home=home, started_at=time.monotonic())

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    async def _wait_ready(process: asyncio.subprocess.Process, endpoint: EngineEndpoint) -> None:
        deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
        url = f"http://127.0.0.1:{endpoint.port}/v1/capabilities"
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
            while time.monotonic() < deadline:
                if process.returncode is not None:
                    raise RuntimeError(f"engine exited during startup ({process.returncode})")
                try:
                    response = await client.get(url, headers={"X-OpenWorker-Token": endpoint.token})
                    if response.status_code == 200 and response.json().get("mode") == "desktop":
                        return
                    if response.status_code == 401:
                        raise RuntimeError("engine port is occupied by a different process")
                except (httpx.RequestError, ValueError):
                    pass
                await asyncio.sleep(0.25)
        raise RuntimeError("engine did not become ready within 30 seconds")

    async def _stop_locked(self, user_id: str) -> None:
        engine = self._engines.pop(user_id, None)
        if engine is not None:
            await self._terminate(engine.process)
            log.info("stopped private engine for account %s", user_id)

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=8.0)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
        else:
            await process.wait()

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(_RECONCILE_SECONDS)
            try:
                await self.reconcile()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("could not reconcile hosted engines")
