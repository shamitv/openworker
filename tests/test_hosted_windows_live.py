"""Explicit native Windows acceptance gate. No mocked engines or providers.

Run OPENWORKER_TEST_HOSTED_WINDOWS=1 after setup, from a context permitted to
create window stations. Missing prerequisites FAIL this opted-in gate.
The only fake is a loopback model endpoint; no paid provider or API key is used.
"""
import json
import os
import socket
import sqlite3
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from coworker.automation import Schedule, ScheduledTask, TaskStore
from coworker.hosted.accounts import AccountStore
from coworker.hosted.app import create_app
from coworker.secrets import SecretStore

pytestmark = pytest.mark.skipif(sys.platform != "win32" or os.environ.get("OPENWORKER_TEST_HOSTED_WINDOWS") != "1",
                               reason="opt-in native Windows hosted acceptance gate")
ORIGIN = "https://phase2.example.test"


def _wait(check, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.2)
    pytest.fail("real Windows acceptance condition did not become true")


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


def _model_app():
    app = FastAPI()

    @app.get("/api/tags")
    def tags():
        return {"models": [{"name": "phase2"}]}

    @app.post("/v1/chat/completions")
    async def complete(request: Request):
        body = await request.json()
        finished = any(message.get("role") == "tool" for message in body["messages"]) or not body.get("tools")
        calls = [{"id": "phase2-write", "type": "function", "function": {"name": "write_file",
                  "arguments": json.dumps({"path": "marker.txt", "content": "scheduled work ran"})}}]
        message = {"role": "assistant", "content": "Done" if finished else None}
        if not finished:
            message["tool_calls"] = calls
        reason = "stop" if finished else "tool_calls"
        if not body.get("stream"):
            return {"id": "phase2", "object": "chat.completion", "created": int(time.time()), "model": "phase2",
                    "choices": [{"index": 0, "message": message, "finish_reason": reason}]}
        delta = dict(message)
        if not finished:
            delta["tool_calls"] = [{**calls[0], "index": 0}]
        frames = [{"id": "phase2", "object": "chat.completion.chunk", "created": int(time.time()), "model": "phase2",
                   "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                  {"id": "phase2", "object": "chat.completion.chunk", "created": int(time.time()), "model": "phase2",
                   "choices": [{"index": 0, "delta": {}, "finish_reason": reason}]}]
        return StreamingResponse(iter([*("data: " + json.dumps(frame) + "\n\n" for frame in frames), "data: [DONE]\n\n"]),
                                 media_type="text/event-stream")
    return app


def _make_due(database, task_id):
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE scheduled_tasks SET next_run=? WHERE id=?", (time.time() - 1, task_id))


def test_real_engines_run_without_browser_recover_and_disable(tmp_path, usable_windows):
    from test_hosted_web import _serve

    port, model_server, model_thread = _serve(_model_app())
    stores = []
    try:
        data, spa = tmp_path / "data", tmp_path / "spa"
        spa.mkdir()
        (spa / "index.html").write_text("<html><head></head><body>Phase 2</body></html>")
        accounts = AccountStore(data)
        users, tasks = {}, {}
        password = "phase two test password long enough"
        for name in ("alice", "bob"):
            user = accounts.create(name, "initial test password long enough")
            token, _, _ = accounts.authenticate(name, "initial test password long enough", "127.0.0.1")
            assert accounts.change_password(token, "initial test password long enough", password)
            users[name] = user
            home = Path(user["home"])
            state, work = home / "state", home / "workspace"
            state.mkdir(exist_ok=True)
            work.mkdir(exist_ok=True)
            (state / "config.toml").write_text('model = "ollama:phase2"\nsandbox_network_profile = "open"\n')
            SecretStore(state / "secrets.json").put("provider:ollama", {"base_url": f"http://127.0.0.1:{port}"})
            store = TaskStore(state / "automation.db")
            stores.append(store)
            task = ScheduledTask(name, "Write marker.txt", Schedule("cron", cron="* * * * *"), str(work),
                                 model="ollama:phase2", always_allowed_tools=["write_file"], notify_on_completion=False)
            store.save(task)
            _make_due(state / "automation.db", task.id)
            tasks[name] = task
        gateway = create_app(spa=spa, data_dir=data, public_origin=ORIGIN, sandbox_provider="windows")
        with TestClient(gateway, base_url=ORIGIN) as client:
            supervisor = gateway.state.supervisor
            assert len(supervisor._engines) == 2
            # Both real scheduled tool runs must finish before anybody signs in.
            for store, task in zip(stores, tasks.values()):
                _wait(lambda: any(run.status == "ok" for run in store.runs(task.id)))
                assert (Path(task.workspace) / "marker.txt").read_text() == "scheduled work ran"
            for engine in supervisor._engines.values():
                assert httpx.get(f"http://127.0.0.1:{engine.endpoint.port}/v1/capabilities").status_code == 401
                interface = socket.gethostbyname(socket.gethostname())
                assert not interface.startswith("127."), "a non-loopback IPv4 interface is required"
                with pytest.raises(OSError):
                    socket.create_connection((interface, engine.endpoint.port), timeout=1).close()
            assert client.post("/web/auth/login", headers={"Origin": ORIGIN}, json={"username": "alice", "password": password}).status_code == 200
            session = client.get("/web/auth/session").json()
            bob_run = stores[1].runs(tasks["bob"].id)[0].session_id
            assert client.get(f"/v1/sessions/{bob_run}/messages").json()["messages"] == []
            assert client.get("/web/artifacts/download", params={"session": bob_run, "path": "marker.txt"}).status_code == 404
            bob_token = supervisor._engines[users["bob"]["id"]].endpoint.token
            with client.websocket_connect(f"/ws/session/{bob_run}", headers={"Origin": ORIGIN, "X-OpenWorker-Actor": "bob"},
                                          subprotocols=["openworker", bob_token]) as websocket:
                websocket.send_json([])
                assert websocket.receive_json()["type"] == "input_rejected"
            assert client.get(f"/v1/sessions/{bob_run}/messages").json()["messages"] == []
            # A forged identity and absolute path still cannot select Bob's home.
            response = client.post("/v1/workspaces/open", headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf"],
                                   "X-OpenWorker-Actor": "bob"}, json={"path": users["bob"]["home"]})
            assert not response.json()["ok"]
            assert client.post("/web/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf"]}).status_code == 200
            count = stores[0].get(tasks["alice"].id).run_count
            _make_due(Path(users["alice"]["home"]) / "state" / "automation.db", tasks["alice"].id)
            _wait(lambda: stores[0].get(tasks["alice"].id).run_count > count)
            assert stores[0].runs(tasks["alice"].id)[0].status == "ok"
            old = supervisor._engines[users["alice"]["id"]]
            client.portal.call(old.process.kill)
            _make_due(Path(users["alice"]["home"]) / "state" / "automation.db", tasks["alice"].id)
            _wait(lambda: (engine := supervisor._engines.get(users["alice"]["id"])) and engine.process.pid != old.process.pid)
            assert supervisor._engines[users["alice"]["id"]].endpoint.token != old.endpoint.token
            _wait(lambda: stores[0].get(tasks["alice"].id).run_count > count + 1)
            assert stores[0].runs(tasks["alice"].id)[0].trigger == "catchup"
            accounts.disable("bob")
            _wait(lambda: users["bob"]["id"] not in supervisor._engines)
            assert users["alice"]["id"] in supervisor._engines
    finally:
        for store in stores:
            store.close()
        model_server.should_exit = True
        model_thread.join(timeout=5)
