"""Lifecycle and boundary coverage; these tests do not prove OS sandbox enforcement."""
import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest

from coworker.hosted import supervisor as module
from coworker.sandbox import selection, workspace


class Process:
    def __init__(self):
        self.returncode = None
        self.terminated = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    async def wait(self):
        return self.returncode


@pytest.fixture
def supervised(tmp_path, monkeypatch):
    home = tmp_path / "homes" / "alice"
    home.mkdir(parents=True)
    row = {"id": "alice", "home": str(home), "enabled": True}
    rows = [row]
    store = type("Store", (), {"list_users": lambda self: rows})()
    supervisor = module.EngineSupervisor(tmp_path, store, "windows", "https://test.example")
    launches = []

    async def launch(user_id, owned_home):
        engine = module._Engine(Process(), module.EngineEndpoint(10001 + len(launches), f"token-{len(launches)}"), owned_home, time.monotonic())
        launches.append(engine)
        return engine

    async def available():
        return True

    monkeypatch.setattr(supervisor, "_launch", launch)
    monkeypatch.setattr(supervisor, "_provider_available", available)
    return supervisor, row, rows, launches


async def test_canonical_home_and_concurrent_ensure_launch_once(supervised):
    supervisor, row, _, launches = supervised
    try:
        forged = {**row, "home": "C:/another-account"}
        results = await asyncio.gather(*(supervisor.ensure(forged) for _ in range(8)))
        assert len(launches) == 1
        assert launches[0].home == Path(row["home"]).resolve()
        assert len(set(results)) == 1
    finally:
        await supervisor.stop()


async def test_disabled_and_deleted_accounts_stop_and_never_relaunch(supervised):
    supervisor, row, rows, launches = supervised
    await supervisor.ensure(row)
    row["enabled"] = False
    assert await supervisor.ensure(row) is None
    assert launches[0].process.terminated
    row["enabled"] = True
    await supervisor.ensure(row)
    rows.clear()
    assert await supervisor.ensure(row) is None
    assert launches[-1].process.terminated
    await supervisor.stop()


async def test_startup_failure_backoff_is_bounded_and_recovers(supervised, monkeypatch):
    supervisor, row, _, _ = supervised
    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    attempts = []

    async def fail(user_id, home):
        attempts.append(user_id)
        raise RuntimeError("runner failed")

    monkeypatch.setattr(supervisor, "_launch", fail)
    for expected in (2, 4, 8, 16, 32, 60, 60):
        assert await supervisor.ensure(row) is None
        assert supervisor._retry_at[row["id"]] == clock[0] + expected
        assert await supervisor.ensure(row) is None
        clock[0] += expected
    assert len(attempts) == 7
    await supervisor.stop()


async def test_crash_rotates_token_and_stable_uptime_resets_failures(supervised):
    supervisor, row, _, launches = supervised
    try:
        first = await supervisor.ensure(row)
        launches[0].process.returncode = 9
        assert await supervisor.ensure(row) is None
        supervisor._retry_at[row["id"]] = 0
        second = await supervisor.ensure(row)
        assert first.token != second.token and first.port != second.port
        launches[-1].started_at -= module._STABLE_UPTIME_SECONDS + 1
        await supervisor.ensure(row)
        assert row["id"] not in supervisor._failures
    finally:
        await supervisor.stop()


async def test_provider_unavailable_never_launches(supervised, monkeypatch):
    supervisor, row, _, launches = supervised

    async def unavailable():
        return False

    monkeypatch.setattr(supervisor, "_provider_available", unavailable)
    assert await supervisor.ensure(row) is None
    assert not launches
    await supervisor.stop()


async def test_stop_cancels_monitor_and_all_processes(supervised):
    supervisor, _, _, launches = supervised
    await supervisor.start()
    monitor = supervisor._monitor
    await supervisor.stop()
    assert monitor.cancelled()
    assert not supervisor._engines
    assert all(engine.process.terminated for engine in launches)


@pytest.mark.parametrize("mutation", ["outside", "unexpected", "duplicate_id", "excess"])
async def test_invalid_account_mapping_fails_before_launch(supervised, mutation):
    supervisor, row, rows, launches = supervised
    if mutation == "outside":
        row["home"] = str(supervisor.data_dir.parent / "outside")
    elif mutation == "unexpected":
        row["home"] = str(supervisor.homes_dir / "bob")
    elif mutation == "duplicate_id":
        rows.append(dict(row))
    else:
        rows.extend({"id": str(index), "home": str(supervisor.homes_dir / str(index)), "enabled": True} for index in range(20))
    with pytest.raises(ValueError):
        await supervisor.ensure(row)
    assert not launches


def _link(link, target):
    if os.name == "nt":
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def test_home_and_child_junctions_are_rejected(tmp_path):
    homes = tmp_path / "homes"
    homes.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _link(homes / "alice", outside)
    supervisor = module.EngineSupervisor(tmp_path, None, "windows", "https://test.example")
    with pytest.raises(ValueError):
        supervisor._home({"id": "alice", "home": str(homes / "alice")})
    _link(outside / "state", homes)
    with pytest.raises(ValueError):
        supervisor._child_dir(outside, "state")


def test_replaced_homes_directory_is_rejected(tmp_path):
    homes = tmp_path / "homes"
    homes.mkdir()
    supervisor = module.EngineSupervisor(tmp_path, None, "windows", "https://test.example")
    homes.rmdir()
    outside = tmp_path / "outside"
    (outside / "alice").mkdir(parents=True)
    _link(homes, outside)
    with pytest.raises(ValueError):
        supervisor._home({"id": "alice", "home": str(homes / "alice")})


def test_child_environment_drops_operator_credentials_and_plugins(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "operator-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "operator-cloud-key")
    monkeypatch.setenv("PYTHONPATH", "operator-plugins")
    monkeypatch.setenv("COWORKER_API_TOKEN", "operator-engine-token")
    monkeypatch.setenv("PATH", "runtime-bin")
    environment = module._engine_environment()
    assert environment["PATH"] == "runtime-bin"
    assert not any(key in environment for key in ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "PYTHONPATH", "COWORKER_API_TOKEN"))


async def test_launch_refuses_hardlinked_engine_log_before_process_creation(tmp_path, monkeypatch):
    if os.name == "nt":
        from coworker.sandbox import winsec
        monkeypatch.setattr(winsec, "protect_directory", lambda _: None)
    supervisor = module.EngineSupervisor(tmp_path, None, "windows", "https://test.example")
    state = tmp_path / "homes" / "alice" / "state"
    state.mkdir(parents=True)
    other = tmp_path / "foreign.log"
    other.write_text("foreign")
    os.link(other, state / "engine.log")
    with pytest.raises(ValueError, match="hard link"):
        await supervisor._launch("alice", state.parent)
    assert other.read_text() == "foreign"


@pytest.mark.parametrize("provider", ["", "direct", "runner-local"])
def test_hosted_selection_cannot_fall_back(monkeypatch, provider):
    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    monkeypatch.setenv("OPENWORKER_SANDBOX_PROVIDER", provider)
    with pytest.raises(ValueError, match="enforcing"):
        selection.select(headless=True)


@pytest.mark.parametrize("provider", ["direct", "runner-local", "seatbelt"])
def test_hosted_workspace_cannot_override_administrator_provider(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    monkeypatch.setenv("OPENWORKER_SANDBOX_PROVIDER", "windows")
    with pytest.raises(ValueError, match="administrator"):
        workspace.open_workspace(cwd=tmp_path, provider=provider)
