"""Shared real-engine acceptance scenarios for Windows and Linux hosted engines."""
import json
import socket
import sqlite3
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
from coworker.sandbox.network_profiles import default_profile

ORIGIN = "https://phase2.example.test"
WS_ORIGIN = "wss://phase2.example.test"


def _wait(check, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.2)
    pytest.fail("real hosted acceptance condition did not become true")


def _non_loopback_ipv4():
    # Ubuntu commonly resolves its hostname to 127.0.1.1. Selecting a route
    # supplies the real interface address without sending a datagram.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("192.0.2.1", 9))
        return sock.getsockname()[0]


def model_app():
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


def exercise_real_engines(tmp_path, sandbox_provider):
    from test_hosted_web import _serve

    port, model_server, model_thread = _serve(model_app())
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
            # Exercise each platform's supported default. OpenShell requires
            # explicit destination rules; Windows defaults to an open network.
            profile = default_profile("win32" if sandbox_provider == "windows" else "linux")
            (state / "config.toml").write_text(f'model = "ollama:phase2"\nsandbox_network_profile = "{profile}"\n')
            SecretStore(state / "secrets.json").put("provider:ollama", {"base_url": f"http://127.0.0.1:{port}"})
            store = TaskStore(state / "automation.db")
            stores.append(store)
            task = ScheduledTask(name, "Write marker.txt", Schedule("cron", cron="* * * * *"), str(work),
                                 model="ollama:phase2", always_allowed_tools=["write_file"], notify_on_completion=False)
            store.save(task)
            _make_due(state / "automation.db", task.id)
            tasks[name] = task
        gateway = create_app(spa=spa, data_dir=data, public_origin=ORIGIN, sandbox_provider=sandbox_provider)
        with TestClient(gateway, base_url=ORIGIN) as client:
            supervisor = gateway.state.supervisor
            assert len(supervisor._engines) == 2
            # Both real scheduled tool runs must finish before anybody signs in.
            for store, task in zip(stores, tasks.values()):
                _wait(lambda: any(run.status == "ok" for run in store.runs(task.id)))
                assert (Path(task.workspace) / "marker.txt").read_text() == "scheduled work ran"
            for engine in supervisor._engines.values():
                assert httpx.get(f"http://127.0.0.1:{engine.endpoint.port}/v1/capabilities").status_code == 401
                interface = _non_loopback_ipv4()
                assert not interface.startswith("127."), "a non-loopback IPv4 interface is required"
                with pytest.raises(OSError):
                    socket.create_connection((interface, engine.endpoint.port), timeout=1).close()
            assert client.post("/web/auth/login", headers={"Origin": ORIGIN}, json={"username": "alice", "password": password}).status_code == 200
            session = client.get("/web/auth/session").json()
            bob_run = stores[1].runs(tasks["bob"].id)[0].session_id
            assert client.get(f"/v1/sessions/{bob_run}/messages").json()["messages"] == []
            assert client.get("/web/artifacts/download", params={"session": bob_run, "path": "marker.txt"}).status_code == 404
            bob_token = supervisor._engines[users["bob"]["id"]].endpoint.token
            with client.websocket_connect(f"{WS_ORIGIN}/ws/session/{bob_run}", headers={"Origin": ORIGIN, "X-OpenWorker-Actor": "bob"},
                                          subprotocols=["openworker", bob_token]) as websocket:
                ready = websocket.receive_json()
                assert ready["type"] == "ready"
                assert Path(ready["data"]["workspace"]).is_relative_to(Path(users["alice"]["home"]))
                websocket.send_json([])
                assert websocket.receive_json()["type"] == "input_rejected"
            # Opening a new Alice-local ID initializes its system prompt. Bob's
            # scheduled user/assistant/tool history must never cross the gateway.
            messages = client.get(f"/v1/sessions/{bob_run}/messages").json()["messages"]
            assert not any(message.get("role") in {"user", "assistant", "tool"} for message in messages)
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
