"""Saved state and path APIs must not extend a hosted account's authority."""
import os
import subprocess
from pathlib import Path

import pytest

from coworker.automation import Schedule, ScheduledTask
from coworker.basedir import OutsideBaseDir
from coworker.events import Event, EventType
from coworker.server.manager import SessionManager
from coworker.sessions import SessionRecord


@pytest.fixture
def confined(tmp_path, monkeypatch):
    home = tmp_path / "alice"
    workspace = home / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("OPENWORKER_BASE_DIR", str(home))
    monkeypatch.setenv("COWORKER_STATE_DIR", str(home / "state"))
    manager = SessionManager(workspace=workspace, data_dir=home / "state")
    return manager, home, tmp_path / "bob"


def _junction(link, target):
    if os.name == "nt":
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def test_persisted_workspace_is_revalidated_before_engine_or_mcp_preparation(confined):
    manager, _, outside = confined
    outside.mkdir()
    manager.session_store.save(SessionRecord("saved", str(outside), "unused", "interactive"))
    with pytest.raises(OutsideBaseDir):
        manager.engine_workspace("saved")
    with pytest.raises(OutsideBaseDir):
        manager.get_engine("saved")


def test_persisted_extra_roots_are_revalidated(confined):
    manager, home, outside = confined
    outside.mkdir()
    manager.session_store.save(SessionRecord("saved", str(home / "workspace"), "unused", "interactive",
                                           extra_roots=[{"path": str(outside), "writable": True}]))
    with pytest.raises(OutsideBaseDir):
        manager.get_engine("saved")


def test_artifact_scan_prunes_junctions_and_saved_foreign_roots(confined):
    manager, _, outside = confined
    outside.mkdir()
    (outside / "secret.txt").write_text("bob secret")
    scratch = Path(manager._provision_scratch("scan"))
    (scratch / "own.txt").write_text("alice")
    _junction(scratch / "escape", outside)
    manager.session_store.save(SessionRecord("scan", str(scratch), "unused", "interactive"))
    assert [item["name"] for item in manager.list_artifacts("scan")] == ["own.txt"]
    assert not manager.read_artifact("scan", "escape/secret.txt")["ok"]
    assert [item["name"] for item in manager.read_artifact("scan", ".")["entries"]] == ["own.txt"]
    manager.session_store.save(SessionRecord("foreign", str(outside), "unused", "interactive"))
    assert not manager.read_artifact("foreign", "secret.txt")["ok"]


def test_hardlinked_artifact_cannot_expose_foreign_state(confined):
    manager, _, outside = confined
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("bob secret")
    scratch = Path(manager._provision_scratch("linked"))
    os.link(secret, scratch / "linked.txt")
    manager.session_store.save(SessionRecord("linked", str(scratch), "unused", "interactive"))
    assert manager.list_artifacts("linked") == []
    assert not manager.read_artifact("linked", "linked.txt")["ok"]
    assert manager.read_artifact("linked", ".")["entries"] == []


def test_skill_scope_junction_cannot_escape_account_home(confined):
    manager, home, outside = confined
    (outside / "skills").mkdir(parents=True)
    _junction(home / "workspace" / ".coworker", outside)
    with pytest.raises(OutsideBaseDir):
        manager.list_skills(str(home / "workspace"))


@pytest.mark.parametrize("link_type", ["junction", "hardlink"])
def test_nested_credential_links_cannot_copy_foreign_files(confined, monkeypatch, tmp_path, link_type):
    from coworker.sandbox import credentials

    _, home, outside = confined
    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    outside.mkdir()
    (outside / "secret.txt").write_text("bob secret")
    source = home / "credential"
    source.mkdir()
    if link_type == "junction":
        _junction(source / "nested", outside)
        expected = OutsideBaseDir
    else:
        os.link(outside / "secret.txt", source / "linked.txt")
        expected = ValueError
    grant = credentials.Grant("custom", "Custom", str(source), "credential")
    staging = tmp_path / "staging"
    with pytest.raises(expected):
        credentials.copy_in([grant], str(staging), home=str(home))
    assert not any(file.read_text() == "bob secret" for file in staging.rglob("*.txt"))


def test_manual_and_scheduled_workspaces_fail_before_directory_creation(confined):
    manager, _, outside = confined
    task = ScheduledTask("invalid", "do work", Schedule("cron", cron="* * * * *"), str(outside / "created"))
    manager.task_store.save(task)
    assert not manager.prepare_manual_run(task.id)["ok"]
    with pytest.raises(OutsideBaseDir):
        manager._build_task_engine(task, session_id="run")
    assert not outside.exists()


@pytest.mark.parametrize("provider", ["openshell", "direct"])
def test_openshell_output_mount_exists_before_first_tool_result(tmp_path, monkeypatch, provider):
    from coworker import agent as module
    from coworker.sandbox.selection import Selection

    home = tmp_path / "alice"
    project = home / "workspace"
    project.mkdir(parents=True)
    spill = home / "cache" / "tool-output"
    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1" if provider == "openshell" else "0")
    monkeypatch.setenv("OPENWORKER_BASE_DIR", str(home))
    monkeypatch.setenv("COWORKER_STATE_DIR", str(home / "state"))
    monkeypatch.setattr(module, "select_sandbox", lambda _: Selection(provider, explicit=True))

    def capture_mounts(**options):
        output = next(root for root in options["roots"] if root.label == "tool-output")
        assert output.path == spill and not output.writable
        assert spill.is_dir() == (provider == "openshell")
        raise RuntimeError("mounts checked")

    monkeypatch.setattr(module, "open_workspace", capture_mounts)
    with pytest.raises(RuntimeError, match="mounts checked"):
        module.build_engine(agent=module.code_agent(), workspace=project, tool_result_spill_dir=spill)


def test_hosted_openshell_refuses_foreign_output_mount_before_creation(tmp_path, monkeypatch):
    from coworker import agent as module
    from coworker.sandbox.selection import Selection

    home = tmp_path / "alice"
    project = home / "workspace"
    project.mkdir(parents=True)
    spill = tmp_path / "bob" / "tool-output"
    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    monkeypatch.setenv("OPENWORKER_BASE_DIR", str(home))
    monkeypatch.setenv("COWORKER_STATE_DIR", str(home / "state"))
    monkeypatch.setattr(module, "select_sandbox", lambda _: Selection("openshell", explicit=True))
    with pytest.raises(OutsideBaseDir):
        module.build_engine(agent=module.code_agent(), workspace=project, tool_result_spill_dir=spill)
    assert not spill.parent.exists()


@pytest.mark.parametrize("failure", ["construction", "sandbox_event"])
async def test_scheduled_failure_finishes_the_original_run_as_error(confined, monkeypatch, failure):
    manager, home, _ = confined
    task = ScheduledTask("failure", "run", Schedule("cron", cron="* * * * *"), str(home / "workspace"), notify_on_completion=False)

    class FailingEngine:
        messages = []

        async def run(self, opening):
            yield Event(EventType.ERROR, {"error": "sandbox unavailable"})

    def build(*args, **kwargs):
        if failure == "construction":
            raise RuntimeError("sandbox unavailable")
        return FailingEngine()

    monkeypatch.setattr(manager, "_build_task_engine", build)
    result = await manager._run_scheduled_task(task, "catchup")
    assert result.status == "error" and "sandbox unavailable" in result.error
    assert result.finished_at is not None
    runs = manager.task_store.runs(task.id)
    assert len(runs) == 1 and runs[0].status == "error"
