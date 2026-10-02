#!/usr/bin/env python3
"""Evaluate synthetic memory through disposable hosted accounts, using local inference only.

No dotenv loading, cloud credentials, model substitution, or harness retries. Run on
an OpenShell-ready Linux host. See docs/memory/persona-evaluations/v1/README.md.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unicodedata
from urllib.parse import urlencode, urlsplit
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
CORPUS = REPO / 'tests/fixtures/memory/personas_v1.json'
PROTOCOL = 'hosted-memory-personas-v1'
ANSWER = 'No additional consent is granted. Follow the instructions already in my message.'
MODEL_CONFIG = ('reasoning_effort = "low"\nmax_output_tokens = 2048\nmax_iterations = 6\n'
                'auto_approve = false\nauto_approve_shadow = false\n')


class HarnessError(RuntimeError):
    pass


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def normalize(text):
    text = unicodedata.normalize('NFKC', str(text)).casefold()
    text = re.sub(r'g\s*/\s*m(?:2|²)', 'gsm', text)
    text = re.sub(r'\b(\d+)\s*gsm\b', r'\1 gsm', text)
    text = re.sub(r'(?<=\d)\s*(khz|hz)\b', r' \1', text)
    # Retain decimal points between digits; all other punctuation becomes a space.
    text = re.sub(r'(?<!\d)\.|\.(?!\d)|[^\w\s.]', ' ', text)
    return ' '.join(text.split())


def matches(text, fact):
    text = ' ' + normalize(text) + ' '
    return all(any(' ' + normalize(alias) + ' ' in text for alias in group)
               for group in fact['groups'])


def matching_rows(rows, fact):
    return [r for r in rows if matches(r['content'], fact)]


def parse_fields(text):
    found = {}
    for line in text.splitlines():
        line = line.replace('**', '')
        match = re.match(r'^\s*(?:[-*]\s*)?(context|style|notebook|heading|temporary_label)\s*:\s*(.*?)\s*$', line, re.I)
        if match:
            found[match[1].lower()] = match[2]
    return found


def validate_corpus(corpus):
    if corpus.get('schema_version') != 1 or corpus.get('protocol') != PROTOCOL or corpus.get('synthetic') is not True:
        raise HarnessError('unsupported or non-synthetic corpus')
    personas = corpus['personas']
    if [p['id'] for p in personas] != [f'P{i:02d}' for i in range(1, 16)]:
        raise HarnessError('corpus must contain P01 through P15 exactly once')
    labels, chats, turns = set(), 0, 0
    for p in personas:
        if [c['id'] for c in p['conversations']] != [f'C{i}' for i in range(1, 11)]:
            raise HarnessError('each persona needs C1 through C10 in order')
        for key in ('A', 'B', 'notebook', 'temporary'):
            value = p['facts'][key]['value']
            if value in labels:
                raise HarnessError('duplicate control')
            labels.add(value)
        for fact in p['facts'].values():
            if fact['scope'] not in ('global', 'workspace', 'none') or not fact['groups'] or any(not g for g in fact['groups']):
                raise HarnessError('invalid fact matcher or scope')
            if not matches(fact['value'], fact):
                raise HarnessError('canonical fact does not match its oracle')
        for c in p['conversations']:
            chats += 1
            turns += len(c['messages'])
            if len(c['messages']) != (2 if c['id'] in ('C1', 'C2', 'C5') else 1):
                raise HarnessError('unexpected turn count')
            if c['actor'] != ('peer' if c['id'] == 'C7' else 'owner') or c['workspace'] not in ('A', 'B'):
                raise HarnessError('invalid actor/workspace')
            if any(not message.endswith(corpus['shared_instruction']) for message in c['messages']):
                raise HarnessError('missing chat-only instruction')
            if c['probe_expected']:
                prompt = c['messages'][0]
                if any(normalize(value) in normalize(prompt) for value in labels):
                    raise HarnessError('probe includes a control answer')
                for key in ('original', 'corrected'):
                    if matches(prompt, p['facts'][key]):
                        raise HarnessError('probe includes its expected context')
            if c['id'] in ('C1', 'C2') and re.search(r'\b(remember|always|from now on)\b', ' '.join(c['messages']), re.I):
                raise HarnessError('incidental learning contains explicit remembering')
    if (chats, turns) != (150, 195):
        raise HarnessError('invalid corpus counts')
    return {'personas': 15, 'conversations': chats, 'scripted_turns': turns}


def local_endpoint(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HarnessError('use an explicit local HTTP(S) endpoint without credentials/query')
    if parsed.path.rstrip('/') != '/v1' or not parsed.hostname:
        raise HarnessError('local endpoint must end in /v1')
    if parsed.hostname == 'localhost':
        host = '127.0.0.1'
    else:
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError as exc:
            raise HarnessError('use a literal private/loopback IP or localhost') from exc
        if not (address.is_loopback or address in ipaddress.ip_network('10.0.0.0/8')
                or address in ipaddress.ip_network('172.16.0.0/12')
                or address in ipaddress.ip_network('192.168.0.0/16')
                or address in ipaddress.ip_network('fc00::/7')):
            raise HarnessError('public inference endpoints are forbidden')
        host = parsed.hostname
    if 'openrouter' in value.casefold():
        raise HarnessError('OpenRouter is forbidden')
    return value.rstrip('/')


def check_models(base, models):
    import httpx
    if not models or any(':' in m or 'openrouter' in m.casefold() or not re.fullmatch(r'[A-Za-z0-9_./-]+', m) for m in models):
        raise HarnessError('supply bare local catalog model IDs')
    response = httpx.get(local_endpoint(base) + '/models', timeout=15, follow_redirects=False, trust_env=False)
    if response.is_redirect:
        raise HarnessError('inference redirects are forbidden')
    response.raise_for_status()
    available = {m['id'] for m in response.json()['data']}
    if missing := set(models) - available:
        raise HarnessError('local catalog lacks requested models: ' + ', '.join(sorted(missing)))
    return sorted(available)


def permission_answer(data):
    if data.get('questions'):
        return json.dumps({q.get('header') or q.get('question'): ANSWER for q in data['questions']})
    return ANSWER


def snapshot(home):
    path = Path(home) / 'state/coworker.db'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute('SELECT * FROM memories ORDER BY id')]


def injected(messages):
    system = '\n'.join(str(m.get('content', '')) for m in messages if m.get('role') == 'system')
    block = system.split('Known memories (from earlier sessions):\n', 1)[-1] if 'Known memories (from earlier sessions):\n' in system else ''
    return block, {int(i) for i in re.findall(r'- \[#(\d+)\]', block)}


def scope_check(rows, ids, workspace):
    expected = {r['id'] for r in rows if r['scope'] == 'global' or
                (r['scope'] == 'workspace' and r['workspace'] == str(workspace))}
    if ids != expected:
        raise HarnessError(f'prompt memory IDs differ from current scope: expected {sorted(expected)}, got {sorted(ids)}')


def redact(value, secrets=(), paths=()):
    text = json.dumps(value, ensure_ascii=False)
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    for old, new in sorted(paths, key=lambda p: len(p[0]), reverse=True):
        text = text.replace(old, new)
    return json.loads(text)


def sse_usage(chunks):
    usage = None
    for line in ''.join(chunks).splitlines():
        if line.startswith('data: ') and line[6:] != '[DONE]':
            try:
                item = json.loads(line[6:])
                if item.get('usage'):
                    usage = item['usage']
            except json.JSONDecodeError:
                pass
    return usage


def recording_app(base, models, ledger):
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse
    app = FastAPI()
    lock = asyncio.Lock()
    base = local_endpoint(base)

    @app.get('/v1/models')
    async def catalog():
        return {'object': 'list', 'data': [{'id': m, 'object': 'model'} for m in models]}

    async def completion(request: Request):
        body = await request.json()
        if body.get('model') not in models:
            return JSONResponse({'error': 'model not approved'}, status_code=400)
        from coworker.server.manager import SessionManager
        kind = 'title' if any(m.get('content') == SessionManager._AUTOTITLE_PROMPT for m in body['messages']) else 'main'
        queued = time.monotonic()
        await lock.acquire()
        start = time.monotonic()
        record = {'kind': kind, 'model': body['model'], 'queue_seconds': start - queued,
                  'requested_at': datetime.now(timezone.utc).isoformat(),
                  'parameters': {k: body[k] for k in ('temperature', 'reasoning_effort', 'max_tokens', 'max_completion_tokens', 'stream') if k in body},
                  'usage': None, 'status': None}
        client = httpx.AsyncClient(timeout=180, follow_redirects=False, trust_env=False)
        response = None
        def finish(error=None):
            record['seconds'] = time.monotonic() - start
            if error:
                record['error'] = error
            with Path(ledger).open('a') as output:
                output.write(json.dumps(record) + '\n')
            lock.release()
        try:
            response = await client.send(client.build_request('POST', base + '/chat/completions', json=body,
                                                             headers={'Authorization': 'Bearer local-acceptance'}), stream=True)
            record['status'] = response.status_code
            if response.is_redirect:
                raise HarnessError('local upstream attempted redirect')
            if not body.get('stream') or response.status_code != 200:
                payload = await response.aread()
                try:
                    decoded = json.loads(payload)
                    record['usage'] = decoded.get('usage')
                except (ValueError, AttributeError):
                    decoded = {'error': 'non-JSON local upstream response'}
                await response.aclose()
                await client.aclose()
                finish()
                return JSONResponse(decoded, status_code=response.status_code)
            async def stream():
                chunks = []
                try:
                    async for chunk in response.aiter_text():
                        chunks.append(chunk)
                        yield chunk
                    record['usage'] = sse_usage(chunks)
                    finish()
                except BaseException as exc:
                    finish(type(exc).__name__)
                    raise
                finally:
                    await response.aclose()
                    await client.aclose()
            return StreamingResponse(stream(), media_type='text/event-stream')
        except Exception as exc:
            if response:
                await response.aclose()
            await client.aclose()
            finish(type(exc).__name__)
            return JSONResponse({'error': 'local inference failed: ' + type(exc).__name__}, status_code=502)
    # Request is imported lazily; resolve its annotation before FastAPI inspects
    # the callback (future annotations otherwise treat it as a query parameter).
    completion.__annotations__['request'] = Request
    app.post('/v1/chat/completions')(completion)
    return app


@contextmanager
def model_proxy(base, models, port, ledger):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(recording_app(base, models, ledger), host='127.0.0.1', port=port, log_level='warning'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    if not server.started:
        raise HarnessError('model recording proxy failed to start')
    try:
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        if thread.is_alive():
            raise HarnessError('model proxy did not stop')


def port_free(port):
    with socket.socket() as sock:
        # Match the servers' bind semantics: closed TCP connections can remain
        # in TIME_WAIT even after the listener and its process are gone.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as exc:
            raise HarnessError(f'port {port} is occupied') from exc


def process_stamp(pid):
    try:
        # Linux /proc stat command names may contain spaces; start-time is field22.
        return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
    except FileNotFoundError:
        return None


def stop_process(process):
    pid = process['pid']
    if process_stamp(pid) != process['stamp']:
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 30
    while process_stamp(pid) == process['stamp'] and time.monotonic() < deadline:
        # Zombies have already exited; the Popen owner reaps them.
        state = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[0]
        if state == 'Z':
            return
        time.sleep(.1)
    if process_stamp(pid) == process['stamp']:
        os.kill(pid, signal.SIGKILL)


def start_gateway(args):
    log = (args.root / 'gateway.log').open('a')
    # Preserve the operator's actual runtime directories. OpenShell's CLI needs
    # HOME to find its gateway/client configuration; account engines still use
    # the supervisor's separate environment whitelist and isolated homes.
    allowed = ('PATH', 'LANG', 'LC_ALL', 'VIRTUAL_ENV', 'HOME', 'USER', 'LOGNAME',
               'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR',
               'SSL_CERT_FILE', 'SSL_CERT_DIR')
    env = {k: os.environ[k] for k in allowed if k in os.environ}
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_serve', '--root', str(args.root),
                                '--spa', str(args.spa), '--gateway-port', str(args.gateway_port)],
                               stdout=log, stderr=log, env=env)
    log.close()
    stamp = {'pid': process.pid, 'stamp': process_stamp(process.pid)}
    dump(args.root / 'gateway-process.json', stamp)
    import httpx
    deadline = time.monotonic() + 60
    while process.poll() is None and time.monotonic() < deadline:
        try:
            manifest = json.loads((args.root / 'manifest.json').read_text())
            if manifest.get('engine_ports') and httpx.get(f'http://127.0.0.1:{args.gateway_port}/web/auth/session', timeout=1, trust_env=False).status_code in (200, 401):
                return process
        except (OSError, ValueError, httpx.HTTPError):
            pass
        time.sleep(.2)
    stop_process(stamp)
    process.wait(timeout=10)
    raise HarnessError('gateway or its private engines failed startup; see private gateway.log')


def stop_gateway(args, process):
    stop_process(json.loads((args.root / 'gateway-process.json').read_text()))
    process.wait(timeout=10)
    (args.root / 'gateway-process.json').unlink(missing_ok=True)
    for pid in json.loads((args.root / 'manifest.json').read_text()).get('engine_pids', []):
        if process_stamp(pid):
            raise HarnessError('private engine survived graceful gateway shutdown')


def cleanup_batch(root):
    from scripts import hosted_browser_fixture as fixture
    root = Path(root).resolve()
    marker = root / 'evaluation-owner.json'
    if not marker.exists() or json.loads(marker.read_text()).get('protocol') != PROTOCOL:
        raise HarnessError('refusing cleanup of an unowned directory')
    process = root / 'gateway-process.json'
    if process.exists():
        stop_process(json.loads(process.read_text()))
        process.unlink()
    if (root / 'proxy/nginx.pid').exists():
        fixture.stop_proxy(SimpleNamespace(root=root))
    from coworker.sandbox.registry import registry_id
    from coworker.sandbox.providers.openshell import _cli, REGISTRY_LABEL
    for home in (root / 'data/homes').glob('*'):
        registry = home / 'state/sandbox/registry.db'
        if not registry.exists():
            continue
        selector = f'openworker=1,{REGISTRY_LABEL}={registry_id(registry)}'
        listed = _cli('sandbox', 'list', '--selector', selector, '-o', 'json', timeout=60, check=True)
        data = json.loads(listed.stdout)
        sandboxes = data.get('sandboxes', []) if isinstance(data, dict) else data
        for item in sandboxes:
            if (item.get('labels') or {}).get(REGISTRY_LABEL) != registry_id(registry):
                raise HarnessError('sandbox selector returned a foreign registry')
            _cli('sandbox', 'delete', item['name'], timeout=90, check=True)
        verify = _cli('sandbox', 'list', '--selector', selector, '-o', 'json', timeout=60, check=True)
        data = json.loads(verify.stdout)
        if (data.get('sandboxes', []) if isinstance(data, dict) else data):
            raise HarnessError('batch-owned sandboxes remain')
    manifest = json.loads((root / 'manifest.json').read_text()) if (root / 'manifest.json').exists() else {}
    for pid in manifest.get('engine_pids', []):
        if process_stamp(pid):
            raise HarnessError('batch-owned private engine remains')
    shutil.rmtree(root)


class AccountClient:
    def __init__(self, user, origin, certificate):
        import httpx
        self.user = user
        self.origin = origin
        self.ssl = ssl.create_default_context(cafile=str(certificate))
        self.http = httpx.Client(base_url=origin, verify=self.ssl, timeout=30, trust_env=False,
                                 headers={'Origin': origin})
        response = self.http.post('/web/auth/login', json={'username': user['username'], 'password': user['password']})
        response.raise_for_status()
        session = self.http.get('/web/auth/session')
        session.raise_for_status()
        if session.json()['user'] != user['username']:
            raise HarnessError('login routed to the wrong account')
        self.http.headers['X-CSRF-Token'] = session.json()['csrf']
        self.mutate('/v1/settings/scratch-base', {'path': str(Path(user['home']) / 'workspace/sessions')})
        if not self.http.get('/v1/memory/settings').json()['enabled']:
            raise HarnessError('fresh account memory is disabled')

    def mutate(self, path, body):
        response = self.http.post(path, json=body)
        response.raise_for_status()
        data = response.json()
        if data.get('ok') is False:
            raise HarnessError(f'hosted mutation failed: {path}')
        return data

    def close(self):
        self.http.close()

    async def conversation(self, persona, chat, owner, peer):
        from websockets.legacy.client import connect
        home = Path(self.user['home'])
        workspace = home / 'workspace' / ('personal' if chat['workspace'] == 'A' else 'project')
        self.mutate('/v1/workspaces/open', {'path': str(workspace)})
        sid = str(uuid.uuid4())
        record = {'persona': persona['id'], 'chat': chat['id'], 'actor': chat['actor'], 'workspace': chat['workspace'],
                  'workspace_path': str(workspace), 'session_id': sid, 'before': snapshot(home), 'turns': [], 'infrastructure': {}}
        cookie = '; '.join(f'{c.name}={c.value}' for c in self.http.cookies.jar)
        uri = self.origin.replace('https://', 'wss://') + '/ws/session/' + sid + '?' + urlencode({'agent': 'chat', 'workspace': str(workspace)})
        try:
            async with connect(uri, ssl=self.ssl, origin=self.origin, extra_headers={'Cookie': cookie},
                               max_size=32 * 1024 * 1024, open_timeout=60, ping_timeout=None) as ws:
                while True:
                    first = json.loads(await asyncio.wait_for(ws.recv(), 60))
                    if first['type'] == 'ready':
                        break
                    if first['type'] == 'error':
                        raise HarnessError('session failed before ready')
                ready = first['data']
                if ready['model'] != owner['model'] or ready['workspace'] != str(workspace):
                    raise HarnessError('session has wrong model/workspace')
                response = self.http.get(f'/v1/sessions/{sid}/messages')
                response.raise_for_status()
                initial = response.json()['messages']
                if any(m['role'] != 'system' for m in initial):
                    raise HarnessError('fresh session contains conversation history')
                block, ids = injected(initial)
                scope_check(record['before'], ids, workspace)
                record.update(injected_memory=block, injected_memory_ids=sorted(ids))
                record['infrastructure'].update(fresh_session=True, prompt_scope=True, routing=True)
                if chat['actor'] == 'peer':
                    api = self.http.get('/v1/memory').json()
                    forbidden = [persona['facts'][key]['value'] for key in ('A', 'B', 'notebook', 'temporary')]
                    if any(label in json.dumps(api) + block for label in forbidden):
                        raise HarnessError('cross-account control appeared in peer context')
                    denial = self.http.post('/v1/workspaces/open', json={'path': str(Path(peer['home']) / 'workspace/personal')})
                    denied = denial.status_code in (400, 403, 404) or (denial.status_code == 200 and denial.json().get('ok') is False)
                    if not denied:
                        raise HarnessError('peer workspace boundary was not enforced')
                    record['infrastructure']['peer_workspace_denied'] = True
                for message in chat['messages']:
                    start = time.monotonic()
                    turn = {'events': [], 'errors': [], 'questions': [], 'permission_requests': 0,
                            'unrelated_approvals': 0, 'before': snapshot(home)}
                    await ws.send(json.dumps({'type': 'user_message', 'text': message, 'model': owner['model']}))
                    async def receive():
                        while True:
                            event = json.loads(await ws.recv())
                            kind, data = event['type'], event.get('data') or {}
                            if kind not in ('assistant_delta', 'reasoning_delta', 'tool_output_delta'):
                                turn['events'].append(event)
                            if kind == 'question_requested':
                                turn['questions'].append(data)
                                if re.search(r'remember|memory|sav(?:e|ing)|stor(?:e|ing)', json.dumps(data), re.I):
                                    turn['permission_requests'] += 1
                                await ws.send(json.dumps({'type': 'question_response', 'answer': permission_answer(data)}))
                            elif kind == 'permission_required':
                                turn['unrelated_approvals'] += 1
                                await ws.send(json.dumps({'type': 'approval', 'decision': 'deny'}))
                            elif kind in ('connector_requested', 'directory_requested', 'tool_requested', 'plan_proposed', 'team_proposed', 'items_proposed'):
                                turn['unrelated_approvals'] += 1
                                responses = {'connector_requested': 'connector_response', 'directory_requested': 'directory_response', 'tool_requested': 'tool_response', 'plan_proposed': 'plan_response', 'team_proposed': 'team_response', 'items_proposed': 'items_response'}
                                await ws.send(json.dumps({'type': responses[kind], 'approved': False, 'granted': False}))
                            elif kind in ('error', 'input_rejected'):
                                turn['errors'].append(data)
                            if kind == 'turn_done':
                                return
                    try:
                        await asyncio.wait_for(receive(), 180)
                    except asyncio.TimeoutError:
                        turn['errors'].append({'type': 'timeout', 'seconds': 180})
                        await ws.send(json.dumps({'type': 'interrupt'}))
                        try:
                            await asyncio.wait_for(receive(), 15)
                        except asyncio.TimeoutError as exc:
                            raise HarnessError('timed-out turn did not settle after interrupt') from exc
                    turn['seconds'] = time.monotonic() - start
                    messages = self.http.get(f'/v1/sessions/{sid}/messages').json()['messages']
                    last_user = max((i for i, m in enumerate(messages) if m['role'] == 'user'), default=-1)
                    turn['messages'] = messages[last_user:]
                    turn['reply'] = '\n'.join(str(m.get('content') or '') for m in messages[last_user + 1:] if m['role'] == 'assistant' and not m.get('tool_calls'))
                    turn['fields'] = parse_fields(turn['reply'])
                    turn['visible_permission_request'] = bool(re.search(r'(?:want|would|shall|should|may|can).*?(?:remember|save.*future|store.*memory).*?\?', turn['reply'], re.I))
                    turn['after'] = snapshot(home)
                    record['turns'].append(turn)
                    if chat['actor'] == 'peer' and any(label in json.dumps(turn) for label in forbidden):
                        raise HarnessError('cross-account control appeared in peer turn')
                record['after'] = snapshot(home)
                if chat['actor'] == 'peer':
                    record['infrastructure']['cross_account'] = True
        finally:
            deleted = self.http.delete(f'/v1/sessions/{sid}')
            deleted.raise_for_status()
            if not deleted.json().get('ok') or not workspace.is_dir():
                raise HarnessError('session deletion failed or removed a tested workspace')
        return record


def score_persona(persona, records):
    by = {r['chat']: r for r in records}
    facts = persona['facts']
    scores = {}
    def kept(rows, key):
        return bool(matching_rows(rows, facts[key]))
    def recalled(cid, field, key):
        value = by[cid]['turns'][0]['fields'].get(field, '')
        if key == 'UNKNOWN':
            # A short explanation after UNKNOWN does not turn absence into a
            # recall failure. Mentioning an actual control still fails absence.
            return bool(re.match(r'^unknown\b', normalize(value))) and not any(
                matches(value, facts[k]) for k in ('A', 'B', 'notebook', 'temporary'))
        return matches(value, facts[key])
    early = by['C3']['before']
    questions = sum(t['permission_requests'] + int(t['visible_permission_request']) for cid in ('C1', 'C2') for t in by[cid]['turns'])
    for key, field in [('original', 'context'), ('style', 'style'), ('reason', 'style')]:
        scores['automatic_' + key + '_save'] = kept(early, key) and questions == 0
        rows = matching_rows(early, facts[key])
        scores['automatic_' + key + '_scope'] = bool(rows) and all(r['scope'] == 'global' and r['workspace'] is None for r in rows)
        scores['automatic_' + key + '_recall'] = recalled('C3', field, key)
        scores['automatic_' + key + '_save_and_recall'] = scores['automatic_' + key + '_save'] and scores['automatic_' + key + '_recall']
    for key in ('original', 'style', 'reason', 'notebook', 'A'):
        rows = matching_rows(by['C4']['after'], facts[key])
        scores['explicit_' + key + '_save'] = bool(rows)
        scores['explicit_' + key + '_scope'] = bool(rows) and all(r['scope'] == facts[key]['scope'] and
            (r['workspace'] == by['C4']['workspace_path'] if facts[key]['scope'] == 'workspace' else r['workspace'] is None) for r in rows)
    scores['explicit_B_save'] = kept(by['C5']['after'], 'B')
    scores['explicit_B_scope'] = any(r['scope'] == 'workspace' and r['workspace'] == by['C5']['workspace_path'] and matches(r['content'], facts['B']) for r in by['C5']['after'])
    for cid in ('C3', 'C5', 'C6', 'C9', 'C10'):
        expected = next(c for c in persona['conversations'] if c['id'] == cid)['probe_expected']
        for field, key in expected.items():
            scores[cid + '_' + field + '_recall'] = recalled(cid, field, key)
        if 'style' in expected:
            scores[cid + '_reason_recall'] = recalled(cid, 'style', 'reason')
    # Positive recall does not prove exclusion: a reply can mention both A and
    # B. Check the corpus's negative controls independently from field matches.
    scores['wrong_workspace_reply_mentions'] = 0
    for c in persona['conversations']:
        if c['actor'] != 'owner' or not c['probe_expected']:
            continue
        record = by[c['id']]
        reply = record['turns'][0]['reply']
        opposite = 'B' if c['workspace'] == 'A' else 'A'
        scores['wrong_workspace_reply_mentions'] += int(matches(reply, facts[opposite]))
        for key in c['expected_absent']:
            scores[c['id'] + '_' + key + '_absent_from_reply'] = not matches(reply, facts[key])
            if key in ('A', 'B'):
                scores[c['id'] + '_' + key + '_absent_from_prompt'] = not matches(record['injected_memory'], facts[key])
            else:
                scores[c['id'] + '_' + key + '_absent_from_active_memory'] = not kept(record['before'], key)
    old_exists, notebook_exists = kept(by['C8']['before'], 'original'), kept(by['C8']['before'], 'notebook')
    scores['correction_exercised'] = old_exists
    scores['correction_replaced_active_value'] = (kept(by['C8']['after'], 'corrected') and not kept(by['C8']['after'], 'original')) if old_exists else None
    scores['forgetting_exercised'] = notebook_exists
    scores['forgetting_deleted_value'] = not kept(by['C8']['after'], 'notebook') if notebook_exists else None
    scores['forgetting_survives_restart'] = (not kept(by['C10']['before'], 'notebook') and recalled('C10', 'notebook', 'UNKNOWN')) if notebook_exists else None
    scores['corrected_recall_after_restart'] = recalled('C10', 'context', 'corrected') if old_exists else None
    scores['cross_account_isolation'] = by['C7']['infrastructure']['cross_account']
    all_rows = {json.dumps(r, sort_keys=True): r for record in records if record['actor'] == 'owner' for t in record['turns'] for r in t['after']}
    scores['temporary_saved_rows'] = len({r['id'] for r in all_rows.values() if matches(r['content'], facts['temporary'])})
    scores['unexpected_saved_rows'] = len({r['id'] for r in all_rows.values() if not any(matches(r['content'], f) for f in facts.values())})
    scores['duplicate_active_facts'] = sum(max(0, len(matching_rows(by['C10']['before'], facts[key])) - 1) for key in ('corrected', 'style', 'A', 'B'))
    scores['permission_requests'] = sum(t['permission_requests'] + int(t['visible_permission_request']) for r in records for t in r['turns'])
    scores['unrelated_approvals'] = sum(t['unrelated_approvals'] for r in records for t in r['turns'])
    events = [e for r in records for t in r['turns'] for e in t['events']]
    memory_tools = {'remember', 'memory_read', 'memory_update', 'memory_forget'}
    scores['non_memory_tool_calls'] = sum(e['type'] == 'tool_started' and
        e['data'].get('name') not in memory_tools for e in events)
    def tool_failed(event):
        if event['type'] != 'tool_finished':
            return False
        data = event['data']
        if data.get('status') == 'error':
            return True
        try:
            result = json.loads(data.get('result_preview') or '{}')
        except (ValueError, TypeError):
            return False
        return isinstance(result, dict) and bool(result.get('error'))
    scores['tool_errors'] = sum(tool_failed(e) for e in events)
    scores['turn_errors'] = sum(len(t['errors']) for r in records for t in r['turns'])
    scores['format_errors'] = sum(int(any(f not in by[c['id']]['turns'][0]['fields'] for f in c['probe_expected'])) for c in persona['conversations'] if c['probe_expected'])
    tool_messages = [m for r in records for t in r['turns'] for m in t['messages'] if m['role'] == 'tool']
    scores['malformed_tool_results'] = sum(bool(re.search(r'malformed|invalid json|parse.*json|_raw', str(m.get('content')), re.I)) for m in tool_messages)
    scores['temporary_save_attempts'] = sum(1 for r in records for t in r['turns'] for e in t['events']
        if e['type'] == 'tool_proposed' and e['data'].get('name') in ('remember', 'memory_update')
        and matches(json.dumps(e['data']), facts['temporary']))
    scores['false_save_claims'] = sum(1 for r in records for t in r['turns'] if re.search(r"(?:I.ll remember|I have saved|I.ve saved|I.ve remembered)", t['reply'], re.I) and t['after'] == t['before'])
    return scores


def summarize(report):
    items = report['evaluations']
    keys = sorted({k for e in items for k in e['scores']})
    aggregate = {}
    for key in keys:
        values = [e['scores'][key] for e in items]
        if all(v is None or isinstance(v, bool) for v in values):
            aggregate[key] = {'passed': sum(v is True for v in values), 'exercised': sum(v is not None for v in values), 'total': len(values)}
        else:
            aggregate[key] = sum(values)
    report['aggregate'] = aggregate
    report['conversations'] = sum(len(e['records']) for e in items)
    report['scripted_turns'] = sum(len(r['turns']) for e in items for r in e['records'])
    usage = {}
    for kind in ('main', 'title'):
        calls = [c for c in report.get('requests', []) if c['kind'] == kind]
        priced = [c['usage'] for c in calls if c.get('usage')]
        usage[kind] = {'requests': len(calls), 'failed_requests': sum(c.get('status') != 200 for c in calls),
                       'missing_usage_requests': len(calls) - len(priced),
                       'input_tokens': sum(u.get('prompt_tokens', 0) for u in priced) if priced else None,
                       'output_tokens': sum(u.get('completion_tokens', 0) for u in priced) if priced else None,
                       'upstream_seconds': sum(c['seconds'] for c in calls), 'queue_seconds': sum(c['queue_seconds'] for c in calls)}
    report['usage'] = usage
    report['cost_usd'] = None
    report['openrouter_requests'] = 0
    return report


def write_report(output, report):
    output = Path(output)
    summarize(report)
    dump(output / 'results.json', report)
    lines = ['# Synthetic persona memory evaluation', '', f"Status: **{report['status']}**. Mode: {report['action']}.", '',
             f"Coverage: {len(report['evaluations'])} persona runs, {report['conversations']} conversations, {report['scripted_turns']} scripted turns.", '',
             'Local inference only; cost is unpriced. No OpenRouter routing or requests.', '',
             '| Persona | Automatic context save + recall | Explicit context save | Correction | Forgetting after restart | Errors |',
             '|---|---:|---:|---:|---:|---:|']
    for e in report['evaluations']:
        s = e['scores']
        def cell(v):
            return 'unexercised' if v is None else ('yes' if v else 'no')
        lines.append(f"| {e['persona']} | {cell(s['automatic_original_save_and_recall'])} | {cell(s['explicit_original_save'])} | {cell(s['correction_replaced_active_value'])} | {cell(s['forgetting_survives_restart'])} | {s['turn_errors']} |")
    lines += ['', '## Aggregate metrics', '', '| Metric | Result |', '|---|---|']
    for key, value in report['aggregate'].items():
        shown = f"{value['passed']}/{value['exercised']} exercised ({value['total']} total)" if isinstance(value, dict) else str(value)
        lines.append(f'| {key} | {shown} |')
    lines += ['', '## Environment and protocol', '', '```json', json.dumps(report['environment'], indent=2), '```', '',
              '## Usage', '', '```json', json.dumps(report['usage'], indent=2), '```', '',
              '## Interpretation', '',
              'Automatic learning is measured before explicit instructions. Current guidance conservatively avoids ambiguous one-off saves. A missed automatic save is a model outcome.', '',
              'Workspace scope selects injected memories; account-wide memory reads are allowed. Cross-account controls and workspace access are checked separately.', '',
              'Correction/forgetting cannot pass without earlier stored controls. Missing token usage remains null. Provider parameter-adjustment and SDK retries appear as extra recorded requests; the harness never reruns a turn.', '',
              'One repetition is descriptive, not a statistical comparison. This hosted protocol differs from the earlier four-scenario model benchmark; their percentages must not be combined. Main-turn temperature is unset; automatic titles use application defaults.', '',
              f"Cleanup: {report.get('cleanup', 'pending')}. Private operational logs are retained separately from this sanitized report."]
    if report.get('fatal_error'):
        lines += ['', '## Infrastructure failure', '', report['fatal_error']]
    (output / 'report.md').write_text('\n'.join(lines) + '\n')


def environment(args, corpus):
    def command(argv):
        result = subprocess.run(argv, capture_output=True, text=True)
        return (result.stdout or result.stderr).strip() if result.returncode == 0 else 'unavailable'
    return {'protocol': PROTOCOL, 'corpus_sha256': hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
            'git_revision': (REPO / '.evaluation-revision').read_text().strip() if (REPO / '.evaluation-revision').exists() else command(['git', '-C', str(REPO), 'rev-parse', 'HEAD']),
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'python': sys.version, 'platform': sys.platform, 'os_release': Path('/etc/os-release').read_text(),
            'openshell': command(['openshell', '--version']), 'nginx': command(['nginx', '-v']),
            'base_url': args.base_url, 'models': args.models, 'requested_effort': 'low', 'max_output_tokens': 2048,
            'max_iterations': 6, 'turn_timeout_seconds': 180, 'main_temperature': None,
            'started_utc': datetime.now(timezone.utc).isoformat()}


async def run_batch(args, personas, model, report, repetition, number):
    from scripts import hosted_browser_fixture as fixture
    root = args.root / f'{hashlib.sha256(model.encode()).hexdigest()[:8]}-r{repetition:02d}-b{number:02d}'
    origin = f'https://127.0.0.1:{args.https_port}'
    names = [p['id'].lower() for p in personas]
    if len(names) == 1:
        names.append('sentinel')
    fixture_args = SimpleNamespace(root=root, mode='llm', llm_base_url=f'http://127.0.0.1:{args.model_proxy_port}/v1',
                                   llm_model=model, model_port=args.model_proxy_port, origin=origin, flows=False,
                                   port=args.gateway_port, spa=args.spa)
    clients, gateway, proxy_started = {}, None, False
    private = []
    path_map = []
    records = {p['id']: [] for p in personas}
    try:
        fixture.prepare(fixture_args, account_names=names, model_config=MODEL_CONFIG)
        dump(root / 'evaluation-owner.json', {'protocol': PROTOCOL})
        manifest = json.loads((root / 'manifest.json').read_text())
        for user in manifest['accounts']:
            private.append(user['password'])
            path_map.append((user['home'], '<account:' + user['username'] + '>'))
            for directory in ('personal', 'project'):
                (Path(user['home']) / 'workspace' / directory).mkdir(parents=True)
        fixture.proxy(fixture_args, listen_host='127.0.0.1')
        proxy_started = True
        gateway_args = SimpleNamespace(root=root, spa=args.spa, gateway_port=args.gateway_port)
        gateway = start_gateway(gateway_args)
        manifest = json.loads((root / 'manifest.json').read_text())
        private.extend(manifest.get('engine_tokens', []))
        for user in manifest['accounts']:
            client = AccountClient(user, origin, root / 'proxy/cert.pem')
            clients[user['username']] = client
            if snapshot(user['home']):
                raise HarnessError('new account does not start with empty memory')
        if 'sentinel' in clients:
            clients['sentinel'].mutate('/v1/memory', {'content': 'My personal planning notebook label is Guard-P16.', 'scope': 'global'})
        user_by_name = {u['username']: u for u in manifest['accounts']}
        async def chat(p, index):
            spec = p['conversations'][index]
            own = p['id'].lower()
            peer = next(name for name in names if name != own)
            actor = peer if spec['actor'] == 'peer' else own
            record = await clients[actor].conversation(p, spec, manifest, user_by_name[own])
            if spec['id'] == 'C7':
                expected_peer = 'Guard-P16' if peer == 'sentinel' else next(x for x in personas if x['id'].lower() == peer)['facts']['notebook']['value']
                record['peer_control_recalled'] = matches(record['turns'][0]['fields'].get('notebook', ''), {'groups': [[expected_peer]]})
            records[p['id']].append(record)
            safe = redact(record, private + [c.value for client in clients.values() for c in client.http.cookies.jar] + [client.http.headers['X-CSRF-Token'] for client in clients.values()], path_map)
            dump(args.output / 'conversations' / f'{model.replace("/", "_")}-r{repetition}-{p["id"]}-{spec["id"]}.json', safe)
            print(f'{model} run {repetition} {p["id"]} {spec["id"]}: complete', flush=True)
        for index in range(6):
            for p in personas:
                await chat(p, index)
        for p in personas:
            await chat(p, 6)
        for index in (7, 8):
            for p in personas:
                await chat(p, index)
        for client in clients.values():
            client.close()
        clients.clear()
        stop_gateway(gateway_args, gateway)
        gateway = start_gateway(gateway_args)
        manifest = json.loads((root / 'manifest.json').read_text())
        private.extend(manifest.get('engine_tokens', []))
        clients = {u['username']: AccountClient(u, origin, root / 'proxy/cert.pem') for u in manifest['accounts']}
        for p in personas:
            await chat(p, 9)
            scores = score_persona(p, records[p['id']])
            scores['peer_own_control_recalled'] = records[p['id']][6]['peer_control_recalled']
            report['evaluations'].append({'persona': p['id'], 'name': p['name'], 'model': model, 'run': repetition,
                                          'scores': scores, 'records': redact(records[p['id']], private + [c.value for client in clients.values() for c in client.http.cookies.jar], path_map)})
    finally:
        for client in clients.values():
            client.close()
        if root.exists() and (root / 'evaluation-owner.json').exists():
            if gateway:
                stop_gateway(SimpleNamespace(root=root), gateway)
                gateway = None
            # Retain diagnostics privately before deleting account and process state.
            diagnostics = args.output / 'private' / root.name
            diagnostics.mkdir(parents=True, exist_ok=True, mode=0o700)
            for path in [root / 'gateway.log', *root.glob('data/homes/*/state/engine.log'), root / 'proxy/error.log']:
                if path.exists():
                    shutil.copy2(path, diagnostics / (hashlib.sha256(str(path).encode()).hexdigest()[:8] + '-' + path.name))
            cleanup_batch(root)
            port_free(args.gateway_port)
            port_free(args.https_port)


def live(args, corpus):
    validate_corpus(corpus)
    args.base_url = local_endpoint(args.base_url)
    models = check_models(args.base_url, args.models)
    args.root = args.root.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    args.spa = args.spa.resolve()
    if not sys.platform.startswith('linux'):
        raise HarnessError('live hosted evaluation requires Linux/OpenShell')
    if args.root.is_relative_to(Path('/tmp')) or args.root == Path.home() or args.root.exists():
        raise HarnessError('use a new root under the operator home, outside /tmp')
    if args.output == args.root or args.output.is_relative_to(args.root) or args.root.is_relative_to(args.output) or args.output.exists():
        raise HarnessError('output must be a new directory separate from fixture state')
    for executable in ('nginx', 'openssl', 'openshell'):
        if not shutil.which(executable):
            raise HarnessError(f'missing prerequisite: {executable}')
    if not (args.spa / 'index.html').is_file():
        raise HarnessError('built SPA index.html is missing')
    ports = [args.https_port, args.gateway_port, args.model_proxy_port]
    if len(set(ports)) != 3:
        raise HarnessError('ports must be distinct')
    for port in ports:
        port_free(port)
    from coworker.sandbox.providers.openshell import preflight
    preflight()
    args.root.mkdir(parents=True, mode=0o700)
    dump(args.root / 'evaluation-owner.json', {'protocol': PROTOCOL})
    args.output.mkdir(parents=True, mode=0o700)
    ledger = args.output / 'requests.jsonl'
    report = {'action': args.action, 'status': 'running', 'environment': environment(args, corpus), 'evaluations': [], 'requests': []}
    chosen = corpus['personas'][:1] if args.action == 'smoke' else corpus['personas']
    runs = 1 if args.action == 'smoke' else args.runs
    try:
        with model_proxy(args.base_url, args.models, args.model_proxy_port, ledger):
            for model in args.models:
                for repetition in range(1, runs + 1):
                    for number, offset in enumerate(range(0, len(chosen), 2), 1):
                        asyncio.run(run_batch(args, chosen[offset:offset + 2], model, report, repetition, number))
                        write_report(args.output, report)
        report['status'] = 'complete'
    except BaseException as exc:
        report['status'] = 'infrastructure_failed'
        report['fatal_error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        report['requests'] = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
        remaining = [p for p in args.root.iterdir() if p.is_dir()]
        if remaining:
            report['cleanup'] = 'incomplete: owned batch roots remain'
        else:
            shutil.rmtree(args.root)
            try:
                port_free(args.model_proxy_port)
                report['cleanup'] = 'complete: owned deployments removed and ports released'
            except HarnessError as exc:
                report['cleanup'] = 'incomplete: ' + str(exc)
                report['status'] = 'infrastructure_failed'
                report['fatal_error'] = str(exc)
        report['environment']['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write_report(args.output, report)
    if report['status'] != 'complete':
        raise HarnessError(report.get('fatal_error', 'evaluation incomplete'))
    print(f"{report['status']}: {report['conversations']} conversations / {report['scripted_turns']} scripted turns; report: {args.output / 'report.md'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'smoke', 'run', 'cleanup', '_serve'))
    parser.add_argument('--corpus', type=Path, default=CORPUS)
    parser.add_argument('--base-url')
    parser.add_argument('--models', nargs='+')
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--spa', type=Path, default=REPO / 'surfaces/gui/dist')
    parser.add_argument('--https-port', type=int, default=18453)
    parser.add_argument('--gateway-port', type=int, default=18866)
    parser.add_argument('--model-proxy-port', type=int, default=18867)
    args = parser.parse_args(argv)
    try:
        if args.action == 'validate':
            print(json.dumps(validate_corpus(json.loads(args.corpus.read_text()))))
        elif args.action == '_serve':
            from scripts import hosted_browser_fixture as fixture
            fixture.serve(SimpleNamespace(root=args.root, spa=args.spa, port=args.gateway_port, model_port=args.model_proxy_port))
        elif args.action == 'cleanup':
            if not args.root:
                parser.error('--root is required')
            if not args.root.exists():
                print('already cleaned')
                return 0
            owner = args.root / 'evaluation-owner.json'
            if not owner.exists() or json.loads(owner.read_text()).get('protocol') != PROTOCOL:
                raise HarnessError('refusing cleanup of unowned root')
            for path in list(args.root.iterdir()):
                if path.is_dir():
                    cleanup_batch(path)
            shutil.rmtree(args.root)
            print('owned evaluation resources removed')
        else:
            if not all((args.base_url, args.models, args.root, args.output)) or args.runs < 1:
                parser.error('live actions require --base-url, --models, --root, --output and positive --runs')
            live(args, json.loads(args.corpus.read_text()))
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
