#!/usr/bin/env python3
"""Disposable real-engine fixture for the separate HTTPS browser acceptance gate.

Run from an installed repository on the sandbox-ready host. The private manifest
contains test credentials and launch tokens; never publish it or add it to Git.
"""
import argparse
import base64
import json
import ipaddress
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from coworker.hosted.accounts import AccountStore
from coworker.hosted.app import create_app
from coworker.secrets import SecretStore


def deterministic_model():
    app = FastAPI()
    @app.get('/v1/models')
    def models():
        return {'object': 'list', 'data': [{'id': 'hosted-fixture', 'object': 'model'}]}
    @app.post('/v1/chat/completions')
    async def complete(request: Request):
        body = await request.json()
        users = [message for message in body['messages'] if message['role'] == 'user']
        prompt = users[-1]['content'] if users else ''
        if isinstance(prompt, list): prompt = ' '.join(part.get('text', '') for part in prompt)
        match = re.search(r'HOSTED_FILE=([A-Za-z0-9_.-]+) HOSTED_MARKER=([A-Za-z0-9_-]+)', prompt)
        last_user = max((i for i, message in enumerate(body['messages']) if message['role'] == 'user'), default=-1)
        finished = not match or any(message['role'] == 'tool' for message in body['messages'][last_user + 1:]) or not body.get('tools')
        call = {'id': 'hosted-write', 'type': 'function', 'function': {'name': 'write_file', 'arguments': json.dumps({'path': match[1], 'content': match[2]})}} if match else None
        message = {'role': 'assistant', 'content': 'The requested file has been created.' if finished else None}
        if not finished: message['tool_calls'] = [call]
        reason = 'stop' if finished else 'tool_calls'
        common = {'id': 'hosted-fixture', 'created': int(time.time()), 'model': 'hosted-fixture'}
        if not body.get('stream'):
            return {**common, 'object': 'chat.completion', 'choices': [{'index': 0, 'message': message, 'finish_reason': reason}]}
        delta = dict(message)
        if not finished: delta['tool_calls'] = [{**call, 'index': 0}]
        frames = [{**common, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                  {**common, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': reason}]}]
        return StreamingResponse(iter([*('data: ' + json.dumps(frame) + '\n\n' for frame in frames), 'data: [DONE]\n\n']), media_type='text/event-stream')
    return app


def prepare(args):
    root = args.root.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    store = AccountStore(root / 'data')
    base = args.llm_base_url if args.mode == 'llm' else f'http://127.0.0.1:{args.model_port}/v1'
    model = args.llm_model if args.mode == 'llm' else 'hosted-fixture'
    if args.mode == 'llm':
        response = httpx.get(base.rstrip('/') + '/models', timeout=15, trust_env=False)
        response.raise_for_status()
        if model not in {item['id'] for item in response.json()['data']}:
            raise RuntimeError('requested live model is not available')
    accounts = []
    for name in ('alice', 'bob'):
        initial, password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        user = store.create(name, initial)
        token, _, _ = store.authenticate(name, initial, 'fixture')
        assert store.change_password(token, initial, password)
        state = Path(user['home']) / 'state'
        state.mkdir(exist_ok=True)
        (state / 'config.toml').write_text(f'model = "openai:{model}"\nsandbox_network_profile = "allowlist"\n')
        SecretStore(state / 'secrets.json').put('provider:openai', {'api_key': 'local-acceptance', 'base_url': base})
        accounts.append({'username': name, 'password': password, 'home': user['home'], 'id': user['id']})
    manifest = {'origin': args.origin, 'mode': args.mode, 'model': f'openai:{model}', 'llm_base_url': base,
                'accounts': accounts, 'root': str(root), 'source': str(Path(__file__).resolve().parents[1]), 'engine_tokens': []}
    path = root / 'manifest.json'
    path.write_text(json.dumps(manifest))
    path.chmod(0o600)
    print('Prepared isolated hosted browser fixture')


def serve(args):
    manifest = json.loads((args.root / 'manifest.json').read_text())
    if manifest['mode'] == 'fixture':
        server = uvicorn.Server(uvicorn.Config(deterministic_model(), host='127.0.0.1', port=args.model_port, log_level='warning'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started: break
            time.sleep(.1)
        if not server.started: raise RuntimeError('deterministic model did not start')
    app = create_app(spa=args.spa, data_dir=args.root / 'data', public_origin=manifest['origin'], sandbox_provider='openshell')
    lifecycle = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(app):
        async with lifecycle(app):
            if len(app.state.supervisor._engines) != 2:
                raise RuntimeError('both real private engines must start')
            manifest['engine_tokens'] = [engine.endpoint.token for engine in app.state.supervisor._engines.values()]
            manifest['engine_ports'] = [engine.endpoint.port for engine in app.state.supervisor._engines.values()]
            (args.root / 'manifest.json').write_text(json.dumps(manifest))
            yield
    app.router.lifespan_context = lifespan
    uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False, log_level='info')


def control(args):
    request = json.loads(base64.b64decode(args.request))
    store = AccountStore(args.root / 'data')
    user = next(user for user in store.list_users() if user['username'] == request['user'])
    if request['action'] == 'expire':
        with sqlite3.connect(store.db_path) as db:
            db.execute('UPDATE sessions SET absolute_expires_at=0 WHERE user_id=?', (user['id'],))
        print(json.dumps({'expired': True}))
    elif request['action'] == 'file':
        filename = request['filename']
        if not re.fullmatch(r'hosted-[A-Za-z0-9_-]+\.txt', filename): raise ValueError('invalid fixture filename')
        files = list((Path(user['home']) / 'workspace').rglob(filename))
        if len(files) != 1: raise RuntimeError(f'expected exactly one account-owned artifact, found {len(files)}')
        if not files[0].resolve().is_relative_to(Path(user['home']) / 'workspace') or files[0].stat().st_nlink != 1:
            raise RuntimeError('artifact is not an account-owned regular file')
        print(json.dumps({'content': files[0].read_text(), 'path': str(files[0])}))
    else: raise ValueError('invalid fixture action')


def proxy(args):
    manifest = json.loads((args.root / 'manifest.json').read_text())
    origin = urlsplit(manifest['origin'])
    directory = args.root.resolve() / 'proxy'
    directory.mkdir(mode=0o700, exist_ok=True)
    try:
        ipaddress.ip_address(origin.hostname)
        san = 'IP:' + origin.hostname
    except ValueError:
        san = 'DNS:' + origin.hostname
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                    '-keyout', str(directory / 'key.pem'), '-out', str(directory / 'cert.pem'),
                    '-subj', '/CN=OpenWorker acceptance', '-addext', 'subjectAltName=' + san],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    configuration = f'''pid {directory}/nginx.pid;
error_log {directory}/error.log;
events {{ worker_connections 1024; }}
http {{
    access_log {directory}/access.log;
    client_body_temp_path {directory}/client_temp;
    proxy_temp_path {directory}/proxy_temp;
    map $http_upgrade $upgrade_connection {{ default upgrade; '' close; }}
    server {{
        listen {origin.port or 443} ssl;
        ssl_certificate {directory}/cert.pem;
        ssl_certificate_key {directory}/key.pem;
        location / {{
            proxy_pass http://127.0.0.1:{args.port};
            proxy_http_version 1.1;
            proxy_buffering off;
            proxy_set_header Host $host;
            proxy_set_header Origin $http_origin;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $upgrade_connection;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_read_timeout 3600s;
            client_max_body_size 32m;
        }}
    }}
}}
'''
    (directory / 'nginx.conf').write_text(configuration)
    subprocess.run(['nginx', '-p', str(directory) + '/', '-c', str(directory / 'nginx.conf')], check=True)
    print('Started isolated HTTPS test proxy')


def stop_proxy(args):
    directory = args.root.resolve() / 'proxy'
    subprocess.run(['nginx', '-p', str(directory) + '/', '-c', str(directory / 'nginx.conf'), '-s', 'quit'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'serve', 'control', 'proxy', 'stop-proxy'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--origin', default='https://10.42.0.248:18443')
    parser.add_argument('--spa', type=Path, default=Path('surfaces/gui/dist'))
    parser.add_argument('--port', type=int, default=18766)
    parser.add_argument('--model-port', type=int, default=18767)
    parser.add_argument('--mode', choices=['fixture', 'llm'], default='fixture')
    parser.add_argument('--llm-base-url', default='http://10.42.0.202:8090/v1')
    parser.add_argument('--llm-model', default='Ornith-1.5-35B-Uncensored-Q6_K')
    parser.add_argument('--request', help='base64-encoded test control request; never exposed by the gateway')
    args = parser.parse_args()
    {'prepare': prepare, 'serve': serve, 'control': control, 'proxy': proxy, 'stop-proxy': stop_proxy}[args.action](args)


if __name__ == '__main__': main()
