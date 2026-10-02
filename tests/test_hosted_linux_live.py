"""Opt-in Linux acceptance gate using real OpenShell containers and engines.

Run OPENWORKER_TEST_HOSTED_LINUX=1 with OpenShell 0.0.116 and grpcio installed.
Use --basetemp beneath the operator's home: a gateway with PrivateTmp cannot
bind-mount pytest's default /tmp paths. Missing prerequisites FAIL the gate.
Only the shared deterministic model endpoint is a fake.
"""
import importlib
import os
import shlex
import sys
from pathlib import Path

import pytest

from hosted_acceptance import _wait, exercise_real_engines

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or os.environ.get("OPENWORKER_TEST_HOSTED_LINUX") != "1",
    reason="opt-in Linux hosted acceptance gate",
)


@pytest.fixture
def usable_openshell(tmp_path):
    from coworker.sandbox.providers import openshell

    importlib.import_module("grpc")  # Opting in makes a missing dependency fail.
    assert not tmp_path.is_relative_to(Path("/tmp")), "use --basetemp under the operator home for gateway bind mounts"
    openshell.preflight()


def test_concurrent_sandboxes_enforce_private_roots_and_cleanup(tmp_path, monkeypatch, usable_openshell):
    from coworker.agents.base import AgentContext
    from coworker import catalog
    from coworker.sandbox.credentials import Grant
    from coworker.sandbox.providers.openshell import OpenShellProvider, _gateway, list_our_sandboxes
    from coworker.sandbox.registry import SandboxRegistry
    from coworker.sandbox.workspace import RunnerWorkspace

    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    monkeypatch.setenv("OPENWORKER_SANDBOX_PROVIDER", "openshell")
    monkeypatch.setenv("COWORKER_API_TOKEN", "operator-engine-token-must-not-cross")
    monkeypatch.setenv("OPENAI_API_KEY", "operator-key-must-not-cross")
    sandboxes = []
    try:
        for name in ("alice", "bob"):
            home = tmp_path / "homes" / name
            project, reference, state = home / "workspace", home / "reference", home / "state"
            for folder in (project, reference, state):
                folder.mkdir(mode=0o700, parents=True)
            (project / "own.txt").write_text(name)
            (reference / "read.txt").write_text("read only")
            (state / "secret.txt").write_text(name + " private secret")
            credential = state / "credential.txt"
            credential.write_text(name + " credential")
            monkeypatch.setenv("OPENWORKER_BASE_DIR", str(home))
            monkeypatch.setenv("COWORKER_STATE_DIR", str(state))
            registry = SandboxRegistry()
            provider = OpenShellProvider(
                roots=[{"path": str(project), "writable": True}, {"path": str(reference), "writable": False}],
                cwd=str(project), registry=registry.id, profile="allowlist",
                credentials=[Grant("custom", "Custom", str(credential), "credential.txt", kind="file")],
            )
            workspace = RunnerWorkspace(provider, cwd=project, registry=registry, session_id=name)
            sandboxes.append((workspace, provider, project, reference, state))
        assert sandboxes[0][1].sandbox_id != sandboxes[1][1].sandbox_id
        assert sandboxes[0][0].registry.id != sandboxes[1][0].registry.id
        namespaces = []
        _, gateway_certs = _gateway()
        for index, (workspace, provider, project, reference, state) in enumerate(sandboxes):
            other = sandboxes[1 - index]
            name = ("alice", "bob")[index]
            monkeypatch.setenv("OPENWORKER_BASE_DIR", str(project.parent))
            tools = {tool.__name__: tool for tool in catalog.expand(
                ["code_files", "git", "search"],
                AgentContext(workspace=project, executor=workspace.executor, sandbox=workspace),
            )}
            assert name in tools["read_file"]("own.txt")["content"]
            tools["write_file"]("written.txt", "through file tool")
            assert (project / "written.txt").read_text() == "through file tool"
            assert tools["grep"](name)["matches"]
            assert workspace.executor.run("git init -q")["exit_code"] == 0
            assert "error" not in tools["git_status"]()
            private_home = Path(provider.copied.home)
            assert workspace.hello["home"] == str(private_home)
            result = workspace.executor.run("cat " + shlex.quote(str(private_home / "credential.txt")))
            assert result["exit_code"] == 0 and name + " credential" in result["output"], result
            assert workspace.executor.run("cat " + shlex.quote(str(reference / "read.txt")))["exit_code"] == 0
            result = workspace.executor.run("echo nope > " + shlex.quote(str(reference / "blocked.txt")))
            assert result["exit_code"] != 0 and not (reference / "blocked.txt").exists(), result
            for secret in (
                state / "secret.txt", other[2] / "own.txt", other[4] / "secret.txt",
                Path(other[1]._tmp) / "policy.yaml", Path(other[1].copied.home) / "credential.txt",
                gateway_certs / "tls.key",
            ):
                denied = workspace.executor.run("cat " + shlex.quote(str(secret)))
                assert denied["exit_code"] != 0, denied
            denied = workspace.executor.run("echo attack > " + shlex.quote(str(other[2] / "attack.txt")))
            assert denied["exit_code"] != 0 and not (other[2] / "attack.txt").exists(), denied
            environment = workspace.executor.run('printf "%s|%s" "$COWORKER_API_TOKEN" "$OPENAI_API_KEY"')
            assert environment["output"].strip() == "|", environment
            namespace = workspace.executor.run("readlink /proc/self/ns/pid")["output"].strip()
            assert namespace and namespace != os.readlink("/proc/self/ns/pid")
            namespaces.append(namespace)
            assert workspace.describe()["enforcement"] == "full"
            # Reaping Bob's registry while Alice is active must preserve Alice.
            workspace.registry.reap()
            assert other[1].sandbox_name in {s["name"] for s in list_our_sandboxes(other[0].registry.id)}
        assert namespaces[0] != namespaces[1]
        first_name = sandboxes[0][1].sandbox_name
        first_runtime = Path(sandboxes[0][1]._tmp)
        sandboxes[0][0].close()
        assert not first_runtime.exists()
        assert first_name not in {s["name"] for s in list_our_sandboxes(sandboxes[0][0].registry.id)}
        alive = sandboxes[1][0].executor.run("echo yes > still-alive.txt; cat still-alive.txt")
        assert alive["exit_code"] == 0 and "yes" in alive["output"], alive
    finally:
        for workspace, provider, *_ in reversed(sandboxes):
            if Path(provider._tmp).exists():
                workspace.close()
    for workspace, provider, *_ in sandboxes:
        assert not Path(provider._tmp).exists()
        assert not list_our_sandboxes(workspace.registry.id)


def test_real_engines_run_without_browser_recover_and_disable(tmp_path, usable_openshell):
    from coworker.hosted.accounts import AccountStore
    from coworker.sandbox.providers.openshell import list_our_sandboxes
    from coworker.sandbox.registry import registry_id

    exercise_real_engines(tmp_path, "openshell")
    for user in AccountStore(tmp_path / "data").list_users():
        registry = registry_id(Path(user["home"]) / "state" / "sandbox" / "registry.db")
        _wait(lambda: not list_our_sandboxes(registry))
