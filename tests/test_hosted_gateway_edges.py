"""Phase 3 transport boundaries and live socket revocation."""
import gzip
import sqlite3

import httpx
import pytest
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from coworker.hosted import app as gateway
from coworker.hosted.accounts import AccountStore
from coworker.hosted.supervisor import EngineEndpoint
from test_hosted_web import _Supervisor, _serve, ORIGIN

PASSWORD = 'phase three replacement password'


def engine(name, token):
    app = FastAPI()
    @app.api_route('/v1/probe', methods=['GET', 'POST'])
    async def probe(request: Request):
        return JSONResponse({'user': name, 'headers': dict(request.headers), 'body': (await request.body()).decode()}, headers={
            'Set-Cookie': f'private_engine={name}; Path=/', 'Connection': 'X-Private', 'X-Private': 'drop', 'X-OpenWorker-Token': token})
    @app.get('/mcp/oauth/callback')
    async def callback(request: Request):
        return Response(request.headers.get('cookie', 'clean'))
    @app.get('/v1/sessions/{session}/artifacts/download')
    async def download(session: str, request: Request):
        assert not request.headers.get('cookie')
        return Response(gzip.compress(name.encode()), headers={'Content-Encoding': 'gzip', 'Content-Type': 'application/octet-stream'})
    @app.websocket('/ws/{path:path}')
    async def socket(ws: WebSocket, path: str):
        assert token in ws.scope['subprotocols'] and not ws.headers.get('cookie')
        await ws.accept(subprotocol='openworker')
        await ws.send_json({'user': name})
        if path.startswith('close/'):
            await ws.close(code=int(path.split('/')[-1]))
            return
        while True:
            message = await ws.receive()
            if message['type'] == 'websocket.disconnect': return
            if message.get('bytes') is not None: await ws.send_bytes(message['bytes'])
            else: await ws.send_text(message['text'])
    return app


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    spa, data = tmp_path / 'spa', tmp_path / 'data'
    spa.mkdir()
    (spa / 'index.html').write_text('<html><head><script src="./assets/main-Ab12cd34.js"></script></head><body>UI</body></html>')
    (spa / 'assets').mkdir()
    (spa / 'assets/main-Ab12cd34.js').write_text('console.log("UI")')
    (spa / 'favicon.svg').write_text('<svg/>')
    outside = tmp_path / 'outside.js'
    outside.write_text('private')
    (spa / 'assets/escape.js').symlink_to(outside)
    store = AccountStore(data)
    users, tokens, csrf = {}, {}, {}
    for name in ('alice', 'bob'):
        users[name] = store.create(name, 'phase three initial password')
        initial, _, _ = store.authenticate(name, 'phase three initial password', 'test')
        assert store.change_password(initial, 'phase three initial password', PASSWORD)
        tokens[name], csrf[name], _ = store.authenticate(name, PASSWORD, 'test')
    servers = [_serve(engine(name, f'{name}-private-token')) for name in users]
    monkeypatch.setattr(gateway, 'EngineSupervisor', _Supervisor)
    monkeypatch.setattr(gateway, 'SESSION_CHECK_SECONDS', .03)
    app = gateway.create_app(spa=spa, data_dir=data, public_origin=ORIGIN, sandbox_provider='openshell')
    app.state.supervisor.endpoints.update({name: EngineEndpoint(server[0], f'{name}-private-token') for name, server in zip(users, servers)})
    try:
        with TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 1234)) as client:
            yield client, app, store, users, tokens, csrf
    finally:
        for _, server, thread in servers:
            server.should_exit = True
            thread.join(timeout=5)


def headers(tokens, name='alice'):
    return {'Cookie': f'{gateway.COOKIE}={tokens[name]}', 'Origin': ORIGIN}


def test_proxy_credentials_cookie_jar_and_response_headers(hosted):
    client, app, _, users, tokens, csrf = hosted
    forged = {**headers(tokens), 'Authorization': 'Bearer forged', 'X-OpenWorker-Token': 'bob-private-token', 'X-OpenWorker-Actor': 'bob',
              'X-OCW-Org': 'bob', 'X-CSRF-Token': csrf['alice'], 'X-Forwarded-Port': '443', 'X-Forwarded-Prefix': '/bob',
              'Forwarded': 'for=forged', 'Connection': 'X-Client-Private', 'X-Client-Private': 'drop'}
    response = client.post('/v1/probe?value=one', headers=forged, content='hello')
    got = response.json()['headers']
    assert got['x-openworker-token'] == 'alice-private-token' and got['x-openworker-actor'] == 'alice'
    assert response.json()['body'] == 'hello'
    for key in ('cookie', 'authorization', 'x-ocw-org', 'x-csrf-token', 'x-forwarded-port', 'x-forwarded-prefix', 'forwarded', 'x-client-private'):
        assert key not in got
    for key in ('set-cookie', 'x-openworker-token', 'connection', 'x-private'): assert key not in response.headers
    assert app.state.client.cookies.get('private_engine') == 'alice'
    assert 'cookie' not in client.get('/v1/probe', headers=headers(tokens, 'bob')).json()['headers']
    assert client.get(f"/h/{users['bob']['id']}/mcp/oauth/callback").text == 'clean'
    download = client.get('/web/artifacts/download?session=bob-session&path=file.txt', headers=headers(tokens, 'bob'))
    assert download.headers['content-encoding'] == 'gzip' and download.content == b'bob'


@pytest.mark.parametrize('path', ['/v1/foo/%2e%2e/workspaces/pick', '/v1/foo/%252e%252e/settings/sandbox', '/assets/%2e%2e/index.html'])
def test_encoded_paths_fail_before_proxy(hosted, path):
    client, _, _, _, tokens, csrf = hosted
    assert client.post(path, headers={**headers(tokens), 'X-CSRF-Token': csrf['alice']}).status_code == 404


def test_spa_assets_and_deep_link(hosted):
    client, _, _, _, tokens, _ = hosted
    auth = headers(tokens)
    response = client.get('/assets/main-Ab12cd34.js', headers=auth)
    assert response.headers['cache-control'] == 'private, max-age=31536000, immutable'
    assert 'javascript' in response.headers['content-type']
    assert client.get('/favicon.svg', headers=auth).headers['cache-control'] == 'private, no-cache'
    for path in ('/', '/index.html', '/sessions/new'):
        response = client.get(path, headers=auth)
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        assert 'src="/assets/' in response.text and '__COWORKER_WEB__=true' in response.text
    for path in ('/assets/missing.js', '/assets/escape.js', '/web/missing', '/favicon.ico'):
        assert client.get(path, headers=auth).status_code == 404
    assert client.get('/', follow_redirects=False).headers['location'] == '/web/login'


@pytest.mark.parametrize('action', ['idle', 'absolute', 'logout', 'reset', 'change', 'disable'])
def test_live_socket_revocation_preserves_other_account(hosted, action):
    client, _, store, _, tokens, csrf = hosted
    with client.websocket_connect(ORIGIN.replace('https:', 'wss:') + '/ws/session/alice', headers=headers(tokens)) as alice:
        with client.websocket_connect(ORIGIN.replace('https:', 'wss:') + '/ws/session/bob', headers=headers(tokens, 'bob')) as bob:
            assert alice.receive_json()['user'] == 'alice' and bob.receive_json()['user'] == 'bob'
            if action in ('idle', 'absolute'):
                with sqlite3.connect(store.db_path) as db:
                    db.execute(f"UPDATE sessions SET {action}_expires_at=0 WHERE user_id=(SELECT id FROM users WHERE username='alice')")
            elif action == 'logout':
                assert client.post('/web/auth/logout', headers={**headers(tokens), 'X-CSRF-Token': csrf['alice']}).status_code == 200
            elif action == 'reset': store.reset_password('alice', PASSWORD)
            elif action == 'change': assert store.change_password(tokens['alice'], PASSWORD, PASSWORD + ' changed')
            else: store.disable('alice')
            with pytest.raises(WebSocketDisconnect) as closed: alice.receive_text()
            assert closed.value.code == 4401
            bob.send_bytes(b'still here')
            assert bob.receive_bytes() == b'still here'


@pytest.mark.parametrize('code', [4403, 1013])
def test_upstream_close_code_preserved(hosted, code):
    client, _, _, _, tokens, _ = hosted
    with client.websocket_connect(ORIGIN.replace('https:', 'wss:') + f'/ws/close/{code}', headers=headers(tokens)) as ws:
        ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as closed: ws.receive_text()
        assert closed.value.code == code


@pytest.mark.parametrize('kind', ['origin', 'cookie', 'no-origin'])
def test_unauthorized_websocket(hosted, kind):
    client, _, _, _, tokens, _ = hosted
    auth = headers(tokens)
    if kind == 'origin': auth['Origin'] = 'https://evil.example'
    if kind == 'no-origin': auth.pop('Origin')
    if kind == 'cookie': auth['Cookie'] = f'{gateway.COOKIE}=invalid'
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ORIGIN.replace('https:', 'wss:') + '/ws/session/alice', headers=auth):
            pytest.fail('unauthorized upgrade accepted')


def test_forwarded_address_only_trusted_from_loopback(hosted, monkeypatch):
    client, app, store, _, _, _ = hosted
    peers = []
    monkeypatch.setattr(store.__class__, 'authenticate', lambda self, username, password, peer: peers.append(peer))
    body = {'username': 'alice', 'password': PASSWORD}
    for forwarded, expected in [('203.0.113.10, 192.0.2.20', '192.0.2.20'), ('invalid', '127.0.0.1')]:
        client.post('/web/auth/login', headers={'Origin': ORIGIN, 'X-Forwarded-For': forwarded}, json=body)
        assert peers[-1] == expected
    remote = TestClient(app, base_url=ORIGIN, client=('198.51.100.4', 1234))
    remote.post('/web/auth/login', headers={'Origin': ORIGIN, 'X-Forwarded-For': '192.0.2.20'}, json=body)
    assert peers[-1] == '198.51.100.4'
    remote.close()


def test_request_limits(hosted, monkeypatch):
    client, _, _, users, tokens, csrf = hosted
    monkeypatch.setattr(gateway, 'MAX_BODY', 8)
    auth = {**headers(tokens), 'X-CSRF-Token': csrf['alice']}
    assert client.post('/v1/probe', headers=auth, content=b'12345678').status_code == 200
    assert client.post('/v1/probe', headers=auth, content=iter([b'1234', b'56789'])).status_code == 413
    assert client.post('/web/auth/login', headers={'Origin': ORIGIN}, content=b'x' * 16385).status_code == 413
    assert client.post('/web/auth/password', headers=auth, content=b'x' * 16385).status_code == 413
    assert client.post(f"/h/{users['alice']['id']}/oauth/callback", content=b'x' * (1024 * 1024 + 1)).status_code == 413


async def test_outbound_stream_closes_on_error():
    class Broken(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            yield b'first'
            raise httpx.ReadError('lost engine')
        async def aclose(self): self.closed = True
    source = Broken()
    stream = gateway._stream_response(httpx.Response(200, stream=source), {})
    with pytest.raises(httpx.ReadError):
        async for _ in stream.body_iterator: pass
    assert source.closed


async def test_body_limit_stops_reading_the_stream():
    calls = []
    chunks = iter([b'1234', b'56789', b'should not be read'])
    async def receive():
        chunk = next(chunks)
        calls.append(chunk)
        return {'type': 'http.request', 'body': chunk, 'more_body': True}
    request = Request({'type': 'http', 'headers': []}, receive)
    with pytest.raises(gateway.HTTPException) as error:
        await gateway._bounded_body(request, 8)
    assert error.value.status_code == 413 and len(calls) == 2


def test_spa_index_cannot_escape_its_directory(tmp_path):
    spa = tmp_path / 'spa'
    spa.mkdir()
    (tmp_path / 'secret').write_text('private')
    (spa / 'index.html').symlink_to(tmp_path / 'secret')
    with pytest.raises(ValueError):
        gateway.create_app(spa=spa, data_dir=tmp_path / 'data', public_origin=ORIGIN, sandbox_provider='openshell')


async def test_upstream_closes_if_browser_disconnects_before_body_starts():
    from starlette.requests import ClientDisconnect
    class Source(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self): yield b'data'
        async def aclose(self): self.closed = True
    source = Source()
    stream = gateway._stream_response(httpx.Response(200, stream=source), {})
    async def send(message): raise OSError('browser disconnected')
    async def receive(): return {'type': 'http.disconnect'}
    with pytest.raises(ClientDisconnect):
        await stream({'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, send)
    assert source.closed
