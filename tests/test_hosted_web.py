"""The public gateway must keep cookies, users, and engine credentials separate."""

from __future__ import annotations

import socket
import threading
import time
import uuid
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.testclient import TestClient

from coworker.hosted.accounts import AccountStore
from coworker.hosted import app as hosted_app
from coworker.hosted.supervisor import EngineEndpoint
from coworker.hosted import supervisor as hosted_supervisor

ORIGIN = "https://worker.example.test"


def _engine(name: str, token: str) -> FastAPI:
    app = FastAPI()

    @app.get("/v1/whoami")
    async def whoami(request: Request):
        if request.headers.get("x-openworker-token") != token:
            return {"error": "wrong engine token"}
        return {
            "user": name,
            "actor": request.headers.get("x-openworker-actor"),
            "cookie": request.headers.get("cookie"),
        }

    @app.post("/v1/write")
    async def write(request: Request):
        return {"user": name, "actor": request.headers.get("x-openworker-actor")}

    @app.get("/v1/sessions/{session_id}")
    async def session(session_id: str):
        if session_id != f"{name}-session":
            from fastapi.responses import Response

            return Response(status_code=404)
        return {"session": session_id}

    @app.get("/v1/sessions/{session_id}/artifacts/download")
    async def download(session_id: str, path: str, request: Request):
        from fastapi.responses import Response

        if session_id != f"{name}-session" or request.headers.get("x-openworker-token") != token:
            return Response(status_code=404)
        return Response(content=f"{name}:{path}", media_type="application/octet-stream")

    @app.get("/mcp/oauth/callback")
    async def oauth_callback(state: str):
        return {"user": name, "state": state}

    @app.websocket("/ws/session/{session_id}")
    async def ws(ws: WebSocket, session_id: str):
        protocols = (ws.headers.get("sec-websocket-protocol") or "").split(", ")
        if token not in protocols or session_id != f"{name}-session":
            await ws.close(code=1008)
            return
        await ws.accept(subprotocol="openworker")
        await ws.receive_text()
        await ws.send_json({"user": name, "actor": ws.headers.get("x-openworker-actor")})

    @app.websocket("/ws/machine")
    async def machine_ws(ws: WebSocket):
        await ws.accept()
        await ws.receive_text()
        await ws.send_json({"user": name})

    return app


def _serve(app: FastAPI) -> tuple[int, uvicorn.Server, threading.Thread]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            return port, server, thread
        time.sleep(0.02)
    raise AssertionError("test engine failed to start")


class _Supervisor:
    def __init__(self, data_dir, store, provider, origin):
        self.endpoints: dict[str, EngineEndpoint] = {}

    async def start(self):
        pass

    async def stop(self):
        pass

    async def ensure(self, user):
        return self.endpoints.get(user["username"])


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/web/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return client.get("/web/auth/session").json()


def test_accounts_revocation_and_throttling(tmp_path):
    store = AccountStore(tmp_path)
    store.create("alice", "initial password with enough length")
    assert store.authenticate("alice", "bad password", "192.0.2.1") is None
    session = store.authenticate("alice", "initial password with enough length", "192.0.2.1")
    assert session is not None
    token, csrf, user = session
    assert user["must_change"] is True
    assert store.get_session(token)["csrf"] == csrf
    assert store.change_password(token, "initial password with enough length", "another long secure password")
    assert store.get_session(token) is None
    token, _, user = store.authenticate("alice", "another long secure password", "192.0.2.1")
    assert user["must_change"] is False
    store.disable("alice")
    assert store.get_session(token) is None
    assert store.authenticate("alice", "another long secure password", "192.0.2.1") is None


@pytest.mark.asyncio
async def test_supervisor_20_accounts_restart_disable_and_sandbox_failure(tmp_path, monkeypatch):
    class Users:
        def __init__(self):
            self.rows = []

        def list_users(self):
            return self.rows

    class Process:
        returncode = None

        def terminate(self):
            self.returncode = 0

        async def wait(self):
            return self.returncode

    data = tmp_path / "data"
    users = Users()
    for i in range(20):
        user_id = uuid.uuid4().hex
        home = data / "homes" / user_id
        home.mkdir(parents=True)
        users.rows.append({"id": user_id, "home": str(home), "enabled": True, "username": f"user{i}"})
    supervisor = hosted_supervisor.EngineSupervisor(data, users, "openshell", ORIGIN)
    launches = []

    async def launch(user_id, home):
        launches.append(user_id)
        return hosted_supervisor._Engine(Process(), EngineEndpoint(10000 + len(launches), "private"), home, time.monotonic())

    async def available():
        return True

    monkeypatch.setattr(supervisor, "_launch", launch)
    monkeypatch.setattr(supervisor, "_provider_available", available)
    await supervisor.start()
    try:
        assert len(supervisor._engines) == 20
        first = users.rows[0]
        # A crashed engine backs off, then restarts; unattended work has a
        # resident engine independent of any browser cookie.
        supervisor._engines[first["id"]].process.returncode = 1
        await supervisor.reconcile()
        assert len(supervisor._engines) == 19
        supervisor._retry_at[first["id"]] = 0
        await supervisor.reconcile()
        assert len(supervisor._engines) == 20
        first["enabled"] = False
        await supervisor.reconcile()
        assert first["id"] not in supervisor._engines
        first["enabled"] = True

        async def unavailable():
            return False

        monkeypatch.setattr(supervisor, "_provider_available", unavailable)
        supervisor._retry_at[first["id"]] = 0
        assert await supervisor.ensure(first) is None
        assert first["id"] not in supervisor._engines
        user_id = uuid.uuid4().hex
        home = data / "homes" / user_id
        home.mkdir()
        users.rows.append({"id": user_id, "home": str(home), "enabled": True, "username": "excess"})
        with pytest.raises(ValueError, match="at most 20"):
            await supervisor.reconcile()
    finally:
        await supervisor.stop()


def test_public_callback_and_join_url_scoping(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from coworker import cloud
    from coworker.config import Config
    from coworker.mcp import oauth as mcp_oauth
    from coworker.remote.joiner import _ws_url, parse_join_url

    user_id = uuid.uuid4().hex
    monkeypatch.setenv("OPENWORKER_HOSTED_WEB", "1")
    monkeypatch.setenv("OPENWORKER_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("OPENWORKER_HOSTED_USER_ID", user_id)
    target = f"{ORIGIN}/h/{user_id}"
    assert mcp_oauth.redirect_base() == target
    auth = cloud.begin_login(Config())
    assert parse_qs(urlsplit(auth["authorize_url"]).query)["redirect_uri"] == [target + "/auth/callback"]
    assert cloud._login_redirect_uri(Config()) == target + "/auth/callback"
    assert parse_join_url(target + "/j/secure-token") == (target, "secure-token")
    assert _ws_url(target) == f"wss://worker.example.test/h/{user_id}/ws/machine"


def test_gateway_private_http_websocket_and_csrf(tmp_path, monkeypatch):
    data = tmp_path / "data"
    spa = tmp_path / "spa"
    spa.mkdir()
    (spa / "index.html").write_text("<html><head></head><body>full UI</body></html>")
    store = AccountStore(data)
    store.create("alice", "alice initial password long")
    store.create("bob", "bob initial password long")
    alice_port, alice_server, alice_thread = _serve(_engine("alice", "alice-engine-token"))
    bob_port, bob_server, bob_thread = _serve(_engine("bob", "bob-engine-token"))
    monkeypatch.setattr(hosted_app, "EngineSupervisor", _Supervisor)
    app = hosted_app.create_app(spa=spa, data_dir=data, public_origin=ORIGIN, sandbox_provider="openshell")
    app.state.supervisor.endpoints.update({
        "alice": EngineEndpoint(alice_port, "alice-engine-token"),
        "bob": EngineEndpoint(bob_port, "bob-engine-token"),
    })
    try:
        with TestClient(app, base_url=ORIGIN) as alice:
            assert alice.get("/v1/whoami").status_code == 401
            alice_session = _login(alice, "alice", "alice initial password long")
            assert alice_session["must_change"]
            # Provisioned users must first replace the admin-supplied password.
            assert alice.get("/v1/whoami").status_code == 403
            assert alice.post("/web/auth/password", headers={"Origin": ORIGIN, "X-CSRF-Token": alice_session["csrf"]}, json={"current": "alice initial password long", "new": "alice replacement password long"}).status_code == 200
            alice_session = _login(alice, "alice", "alice replacement password long")
            alice_cookie = alice.cookies.get(hosted_app.COOKIE)
            bob_session = _login(alice, "bob", "bob initial password long")
            assert bob_session["must_change"]
            assert alice.post("/web/auth/password", headers={"Origin": ORIGIN, "X-CSRF-Token": bob_session["csrf"]}, json={"current": "bob initial password long", "new": "bob replacement password long"}).status_code == 200
            bob_session = _login(alice, "bob", "bob replacement password long")
            bob_cookie = alice.cookies.get(hosted_app.COOKIE)
            alice_headers = {"Cookie": f"{hosted_app.COOKIE}={alice_cookie}"}
            assert alice.get("/v1/whoami", headers={**alice_headers, "X-OpenWorker-Token": "bob-engine-token", "X-OpenWorker-Actor": "bob"}).json() == {"user": "alice", "actor": "alice", "cookie": None}
            assert alice.get("/v1/whoami").json()["user"] == "bob"
            assert alice.get("/v1/sessions/bob-session", headers=alice_headers).status_code == 404
            assert alice.post("/v1/write", headers={**alice_headers, "Origin": ORIGIN}).status_code == 403
            assert alice.post("/v1/write", headers={**alice_headers, "Origin": "https://evil.example", "X-CSRF-Token": alice_session["csrf"]}).status_code == 403
            assert alice.post("/v1/write", headers={**alice_headers, "Origin": ORIGIN, "X-CSRF-Token": alice_session["csrf"]}).json()["user"] == "alice"
            alice_id = next(u["id"] for u in store.list_users() if u["username"] == "alice")
            bob_id = next(u["id"] for u in store.list_users() if u["username"] == "bob")
            assert alice.get("/web/artifacts/download", params={"session": "alice-session", "path": "hello.txt"}, headers=alice_headers).content == b"alice:hello.txt"
            assert alice.get("/web/artifacts/download", params={"session": "bob-session", "path": "hello.txt"}, headers=alice_headers).status_code == 404
            assert alice.get(f"/h/{alice_id}/mcp/oauth/callback", params={"state": "flow"}).json()["user"] == "alice"
            assert alice.get(f"/h/{bob_id}/mcp/oauth/callback", params={"state": "flow"}).json()["user"] == "bob"
            with alice.websocket_connect("/ws/session/alice-session", headers={"Origin": ORIGIN, **alice_headers, "Sec-WebSocket-Protocol": "openworker, bob-engine-token"}) as ws:
                ws.send_text("hello")
                assert ws.receive_json() == {"user": "alice", "actor": "alice"}
            with alice.websocket_connect("/ws/session/bob-session", headers={"Origin": ORIGIN, "Cookie": f"{hosted_app.COOKIE}={bob_cookie}"}) as ws:
                ws.send_text("hello")
                assert ws.receive_json()["user"] == "bob"
            with alice.websocket_connect(f"/h/{alice_id}/ws/machine") as ws:
                ws.send_text("hello")
                assert ws.receive_json()["user"] == "alice"
            assert "alice-engine-token" not in alice.get("/", headers=alice_headers).text
            assert "window.__COWORKER_WEB__=true" in alice.get("/", headers=alice_headers).text
            assert alice.post("/web/auth/logout", headers={**alice_headers, "Origin": ORIGIN, "X-CSRF-Token": alice_session["csrf"]}).status_code == 200
            assert alice.get("/v1/whoami", headers=alice_headers).status_code == 401
            assert alice.get("/v1/whoami", headers={"Cookie": f"{hosted_app.COOKIE}={bob_cookie}"}).status_code == 200
    finally:
        alice_server.should_exit = True
        bob_server.should_exit = True
        alice_thread.join(timeout=3)
        bob_thread.join(timeout=3)
