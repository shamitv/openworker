"""HTTPS-terminated browser gateway. Only a local reverse proxy may reach this app."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import mimetypes
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from .accounts import AccountStore
from .supervisor import EngineSupervisor

COOKIE = "__Host-openworker-session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
MAX_BODY = 32 * 1024 * 1024
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length"}
DROP = HOP | {"cookie", "authorization", "x-openworker-token", "x-openworker-actor", "x-ocw-org", "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip", "origin", "referer", "sec-websocket-protocol"}
BLOCKED_HOSTED = {
    "/v1/workspaces/pick", "/v1/mcp/config/reveal", "/v1/settings/sandbox",
    "/v1/settings/sandbox/setup", "/v1/settings/sandbox/setup/cancel",
    "/v1/settings/sandbox/windows/setup", "/v1/settings/sandbox/windows/remove",
}
ASSET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _login_html() -> str:
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in · OpenWorker</title>
<style>body{font:16px system-ui;max-width:24rem;margin:12vh auto;padding:1rem;color:#222}input,button{font:inherit;box-sizing:border-box;width:100%;padding:.7rem;margin:.4rem 0}button{background:#2872b4;color:white;border:0;border-radius:5px;cursor:pointer}#error{color:#9c281f}</style>
<h1>OpenWorker</h1><form id="login"><label>Username<input name="username" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><button>Sign in</button></form><p id="error" role="alert"></p>
<script>document.getElementById('login').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);let r=await fetch('/web/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:f.get('username'),password:f.get('password')})});if(r.ok){location.assign('/');return}document.getElementById('error').textContent='Invalid username or password';}</script></html>"""


def _password_html() -> str:
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Change password · OpenWorker</title>
<style>body{font:16px system-ui;max-width:24rem;margin:12vh auto;padding:1rem}input,button{font:inherit;box-sizing:border-box;width:100%;padding:.7rem;margin:.4rem 0}button{background:#2872b4;color:white;border:0;border-radius:5px}#error{color:#9c281f}</style>
<h1>Change your password</h1><form id="form"><label>Current password<input name="current" type="password" autocomplete="current-password" required></label><label>New password<input name="new" type="password" autocomplete="new-password" minlength="15" required></label><button>Change password</button></form><p id="error" role="alert"></p>
<script>let csrf='';fetch('/web/auth/session').then(r=>r.json()).then(s=>csrf=s.csrf||'');document.getElementById('form').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);let r=await fetch('/web/auth/password',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({current:f.get('current'),new:f.get('new')})});if(r.ok){location.assign('/web/login');return}document.getElementById('error').textContent='Password change failed';}</script></html>"""


def _no_cache(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
        "font-src 'self' data:; connect-src 'self' wss: https:; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    return response


def create_app(*, spa: Path, data_dir: Path, public_origin: str, sandbox_provider: str) -> FastAPI:
    spa = spa.resolve(strict=True)
    if not (spa / "index.html").is_file():
        raise ValueError(f"built SPA index.html missing in {spa}")
    parsed = urlsplit(public_origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("public origin must be an https origin without a path")
    public_origin = public_origin.rstrip("/")
    data_dir = data_dir.resolve()
    store = AccountStore(data_dir)
    supervisor = EngineSupervisor(data_dir, store, sandbox_provider, public_origin)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await supervisor.start()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=None), trust_env=False) as client:
            app.state.client = client
            try:
                yield
            finally:
                await supervisor.stop()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store
    app.state.supervisor = supervisor

    def user_for(request: Request) -> dict | None:
        return store.get_session(request.cookies.get(COOKIE, ""))

    def origin_ok(origin: str | None) -> bool:
        return bool(origin and hmac.compare_digest(origin, public_origin))

    def csrf_ok(request: Request, user: dict) -> bool:
        token = request.headers.get("x-csrf-token", "")
        return bool(token and hmac.compare_digest(token, user["csrf"]))

    def peer_ip(request: Request) -> str:
        peer = request.client.host if request.client else "unknown"
        if peer in {"127.0.0.1", "::1"}:
            # The loopback reverse proxy appends the actual peer last. Never take
            # the leftmost value, which a remote client could have supplied.
            forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
        return peer

    def _check(request: Request, *, unsafe: bool = False) -> tuple[dict | None, Response | None]:
        user = user_for(request)
        if not user:
            return None, _no_cache(JSONResponse({"error": "authentication required"}, status_code=401))
        if user.get("must_change"):
            return None, _no_cache(JSONResponse({"error": "password change required"}, status_code=403))
        if unsafe and (not origin_ok(request.headers.get("origin")) or not csrf_ok(request, user)):
            return None, _no_cache(JSONResponse({"error": "request verification failed"}, status_code=403))
        return user, None

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # The reverse proxy must rewrite Host; never infer security decisions from it.
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/web/login")
    async def login_page(request: Request):
        if user_for(request):
            return RedirectResponse("/", status_code=303)
        return _no_cache(HTMLResponse(_login_html()))

    @app.get("/web/change-password")
    async def change_page(request: Request):
        if not user_for(request):
            return RedirectResponse("/web/login", status_code=303)
        return _no_cache(HTMLResponse(_password_html()))

    @app.post("/web/auth/login")
    async def login(request: Request):
        if not origin_ok(request.headers.get("origin")):
            return JSONResponse({"error": "request verification failed"}, status_code=403)
        try:
            body = await request.json()
            username = str(body.get("username", ""))
            password = str(body.get("password", ""))
        except (ValueError, AttributeError):
            return JSONResponse({"error": "invalid credentials"}, status_code=401)
        if len(username) > 128 or len(password) > 1024:
            return JSONResponse({"error": "invalid credentials"}, status_code=401)
        client_ip = peer_ip(request)
        result = store.authenticate(username, password, client_ip)
        if not result:
            return JSONResponse({"error": "invalid credentials"}, status_code=401)
        token, csrf, user = result
        response = _no_cache(JSONResponse({"ok": True, "must_change": user["must_change"]}))
        response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="lax", path="/", max_age=7 * 86400)
        return response

    @app.get("/web/auth/session")
    async def session(request: Request):
        user = user_for(request)
        if not user:
            return _no_cache(JSONResponse({"error": "authentication required"}, status_code=401))
        return _no_cache(JSONResponse({"user": user["username"], "csrf": user["csrf"], "must_change": user["must_change"], "workspace_root": str(Path(user["home"]) / "workspace")}))

    @app.post("/web/auth/logout")
    async def logout(request: Request):
        user = user_for(request)
        if not user:
            return JSONResponse({"error": "authentication required"}, status_code=401)
        if not origin_ok(request.headers.get("origin")) or not csrf_ok(request, user):
            return JSONResponse({"error": "request verification failed"}, status_code=403)
        store.revoke(request.cookies[COOKIE])
        response = _no_cache(JSONResponse({"ok": True}))
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.post("/web/auth/password")
    async def change_password(request: Request):
        user = user_for(request)
        if not user:
            return JSONResponse({"error": "authentication required"}, status_code=401)
        if not origin_ok(request.headers.get("origin")) or not csrf_ok(request, user):
            return JSONResponse({"error": "request verification failed"}, status_code=403)
        try:
            body = await request.json()
            ok = store.change_password(request.cookies[COOKIE], str(body.get("current", "")), str(body.get("new", "")))
        except (ValueError, AttributeError):
            ok = False
        if not ok:
            return JSONResponse({"error": "password change failed"}, status_code=400)
        # Password change revokes every existing session; user signs in with the new password.
        response = _no_cache(JSONResponse({"ok": True}))
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.get("/web/health")
    async def health():
        return {"status": "ok"}

    def machine_user(user_id: str) -> dict | None:
        if not re.fullmatch(r"[0-9a-f]{32}", user_id):
            return None
        return next((u for u in store.list_users() if u["id"] == user_id and u["enabled"]), None)

    @app.api_route("/h/{user_id}/{path:path}", methods=["GET", "POST"])
    async def public_engine_flow(user_id: str, path: str, request: Request):
        # These are externally reached by OAuth providers and joined machines. Each
        # engine validates its own one-time state, enrollment token, or device code.
        allowed = (
            request.method == "GET" and (
                re.fullmatch(r"j/[A-Za-z0-9_-]{20,128}", path)
                or path in {"mcp/oauth/callback", "auth/callback"}
            )
        ) or (
            request.method == "POST" and path in {
                "oauth/callback", "v1/remote/device/start", "v1/remote/device/poll"
            }
        )
        user = machine_user(user_id) if allowed else None
        if user is None:
            return Response(status_code=404)
        endpoint = await supervisor.ensure(user)
        if endpoint is None:
            return JSONResponse({"error": "engine unavailable"}, status_code=503)
        body = await request.body()
        if len(body) > 1024 * 1024:
            return Response(status_code=413)
        url = f"http://127.0.0.1:{endpoint.port}/{path}"
        if request.url.query:
            url += "?" + request.url.query
        headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP}
        headers["X-OpenWorker-Token"] = endpoint.token
        try:
            response = await app.state.client.request(request.method, url, headers=headers, content=body)
        except httpx.HTTPError:
            return JSONResponse({"error": "engine unavailable"}, status_code=503)
        safe = {k: v for k, v in response.headers.items() if k.lower() in {"content-type", "location"}}
        return Response(content=response.content, status_code=response.status_code, headers=safe)

    @app.websocket("/h/{user_id}/ws/machine")
    async def public_machine_ws(ws: WebSocket, user_id: str):
        if ws.headers.get("origin") is not None:
            await ws.close(code=1008)
            return
        user = machine_user(user_id)
        if user is None:
            await ws.close(code=1008)
            return
        endpoint = await supervisor.ensure(user)
        if endpoint is None:
            await ws.close(code=1013)
            return
        from websockets.asyncio.client import connect

        try:
            async with connect(f"ws://127.0.0.1:{endpoint.port}/ws/machine", max_size=16 * 1024 * 1024) as upstream:
                await ws.accept()

                async def to_engine():
                    while True:
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        if message.get("text") is not None:
                            await upstream.send(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"])

                async def to_machine():
                    while True:
                        message = await upstream.recv()
                        if isinstance(message, bytes):
                            await ws.send_bytes(message)
                        else:
                            await ws.send_text(message)

                done, pending = await asyncio.wait([asyncio.create_task(to_engine()), asyncio.create_task(to_machine())], return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        except Exception:
            pass
        try:
            await ws.close()
        except RuntimeError:
            pass

    @app.get("/web/artifacts/download")
    async def download(request: Request, session: str, path: str):
        user, error = _check(request)
        if error:
            return error
        endpoint = await supervisor.ensure(user)
        if endpoint is None:
            return JSONResponse({"error": "engine unavailable"}, status_code=503)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", session) or session in (".", "..") or len(path) > 4096:
            return JSONResponse({"error": "not found"}, status_code=404)
        url = f"http://127.0.0.1:{endpoint.port}/v1/sessions/{session}/artifacts/download?{urlencode({'path': path})}"
        try:
            upstream = app.state.client.build_request("GET", url, headers={"X-OpenWorker-Token": endpoint.token})
            result = await app.state.client.send(upstream, stream=True)
        except httpx.HTTPError:
            return JSONResponse({"error": "engine unavailable"}, status_code=503)
        out_headers = {k: v for k, v in result.headers.items() if k.lower() in {"content-type", "content-disposition", "content-length"}}
        out_headers["X-Content-Type-Options"] = "nosniff"
        return StreamingResponse(result.aiter_raw(), status_code=result.status_code, headers=out_headers, background=BackgroundTask(result.aclose))

    @app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def proxy_api(path: str, request: Request):
        user, error = _check(request, unsafe=request.method in UNSAFE)
        if error:
            return error
        route = "/v1/" + path
        if route in BLOCKED_HOSTED or route.endswith("/artifacts/reveal") or route.endswith("/reveal"):
            return JSONResponse({"error": "desktop action unavailable in browser hosting"}, status_code=403)
        endpoint = await supervisor.ensure(user)
        if endpoint is None:
            return JSONResponse({"error": "engine unavailable"}, status_code=503)
        content = await request.body()
        if len(content) > MAX_BODY:
            return JSONResponse({"error": "request too large"}, status_code=413)
        headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP}
        headers["X-OpenWorker-Token"] = endpoint.token
        headers["X-OpenWorker-Actor"] = user["username"]
        url = f"http://127.0.0.1:{endpoint.port}{route}"
        if request.url.query:
            url += "?" + request.url.query
        try:
            upstream = app.state.client.build_request(request.method, url, headers=headers, content=content)
            result = await app.state.client.send(upstream, stream=True)
        except httpx.HTTPError:
            return JSONResponse({"error": "engine unavailable"}, status_code=503)
        out_headers = {k: v for k, v in result.headers.items() if k.lower() not in HOP | {"set-cookie", "access-control-allow-origin", "access-control-allow-credentials"}}
        return StreamingResponse(result.aiter_raw(), status_code=result.status_code, headers=out_headers, background=BackgroundTask(result.aclose))

    @app.websocket("/ws/{path:path}")
    async def proxy_ws(ws: WebSocket, path: str):
        if not origin_ok(ws.headers.get("origin")):
            await ws.close(code=1008)
            return
        cookie = ws.cookies.get(COOKIE, "")
        user = store.get_session(cookie)
        if not user or user.get("must_change"):
            await ws.close(code=1008)
            return
        endpoint = await supervisor.ensure(user)
        if endpoint is None:
            await ws.close(code=1013)
            return
        from websockets.asyncio.client import connect
        url = f"ws://127.0.0.1:{endpoint.port}/ws/{path}"
        if ws.url.query:
            url += "?" + ws.url.query
        try:
            async with connect(url, subprotocols=["openworker", endpoint.token], additional_headers={"X-OpenWorker-Actor": user["username"]}, max_size=16 * 1024 * 1024) as upstream:
                await ws.accept(subprotocol="openworker" if "openworker" in ws.scope.get("subprotocols", []) else None)

                async def browser_to_engine():
                    while True:
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        if not store.get_session(cookie):
                            break
                        if message.get("text") is not None:
                            await upstream.send(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"])

                async def engine_to_browser():
                    while True:
                        frame = await upstream.recv()
                        if not store.get_session(cookie):
                            break
                        if isinstance(frame, bytes):
                            await ws.send_bytes(frame)
                        else:
                            await ws.send_text(frame)

                async def watch_session():
                    while True:
                        await asyncio.sleep(15)
                        if not store.get_session(cookie, touch=False):
                            break

                done, pending = await asyncio.wait([asyncio.create_task(browser_to_engine()), asyncio.create_task(engine_to_browser()), asyncio.create_task(watch_session())], return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        except (WebSocketDisconnect, OSError, Exception):
            pass
        try:
            await ws.close()
        except RuntimeError:
            pass

    @app.get("/{path:path}")
    async def spa_file(path: str, request: Request):
        user = user_for(request)
        if not user:
            return RedirectResponse("/web/login", status_code=303)
        if user.get("must_change"):
            return RedirectResponse("/web/change-password", status_code=303)
        if path and (not ASSET_NAME.fullmatch(path) or ".." in Path(path).parts):
            return Response(status_code=404)
        target = (spa / path).resolve() if path else spa / "index.html"
        if target.is_file() and target.is_relative_to(spa) and target.name != "index.html":
            return FileResponse(target, media_type=mimetypes.guess_type(target.name)[0])
        index = (spa / "index.html").read_text(encoding="utf-8")
        index = index.replace("</head>", "<script>window.__COWORKER_WEB__=true;</script></head>", 1)
        return _no_cache(HTMLResponse(index))

    return app
