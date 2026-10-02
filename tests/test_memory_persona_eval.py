"""Offline corpus, scoring, routing and lifecycle checks; no live inference."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from scripts import eval_memory_personas as ev


@pytest.fixture
def corpus():
    return json.loads(ev.CORPUS.read_text())


def test_complete_expanded_corpus(corpus):
    assert ev.validate_corpus(corpus) == {'personas': 15, 'conversations': 150, 'scripted_turns': 195}


@pytest.mark.parametrize('change', ['duplicate', 'probe_answer', 'missing_message', 'scope', 'incidental'])
def test_corpus_rejects_invalid_controls(corpus, change):
    p = corpus['personas'][0]
    if change == 'duplicate':
        corpus['personas'][1]['facts']['A']['value'] = p['facts']['A']['value']
    elif change == 'probe_answer':
        p['conversations'][2]['messages'][0] = 'Grade 8 CBSE\n' + p['conversations'][2]['messages'][0]
    elif change == 'missing_message':
        p['conversations'][0]['messages'].pop()
    elif change == 'scope':
        p['facts']['A']['scope'] = 'other'
    else:
        p['conversations'][0]['messages'][0] = 'Always remember this. ' + p['conversations'][0]['messages'][0]
    with pytest.raises(ev.HarnessError):
        ev.validate_corpus(corpus)


@pytest.mark.parametrize('url', ['https://openrouter.ai/api/v1', 'https://api.openai.com/v1',
 'http://8.8.8.8/v1', 'http://10.1.1.1/v1?key=x', 'http://key@127.0.0.1/v1', 'ftp://127.0.0.1/v1'])
def test_cloud_and_ambiguous_endpoints_rejected(url):
    with pytest.raises(ev.HarnessError):
        ev.local_endpoint(url)


@pytest.mark.parametrize('url', ['http://10.42.0.202:8090/v1', 'http://127.0.0.1:1234/v1', 'http://localhost:1234/v1', 'http://[::1]:1234/v1'])
def test_local_endpoints_allowed(url):
    assert ev.local_endpoint(url) == url


def test_catalog_never_uses_environment_credentials(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'DO-NOT-USE')
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={'data': [{'id': 'local'}]}, request=httpx.Request('GET', url))
    monkeypatch.setattr(httpx, 'get', get)
    assert ev.check_models('http://127.0.0.1:1234/v1', ['local']) == ['local']
    assert calls == [('http://127.0.0.1:1234/v1/models', {'timeout': 15, 'follow_redirects': False, 'trust_env': False})]
    with pytest.raises(ev.HarnessError, match='lacks'):
        ev.check_models('http://127.0.0.1:1234/v1', ['missing'])
    with pytest.raises(ev.HarnessError):
        ev.check_models('http://127.0.0.1:1234/v1', ['openrouter:local'])


def test_catalog_rejects_redirect(monkeypatch):
    monkeypatch.setattr(httpx, 'get', lambda url, **kwargs: httpx.Response(302, headers={'location': 'https://openrouter.ai'}, request=httpx.Request('GET', url)))
    with pytest.raises(ev.HarnessError, match='redirect'):
        ev.check_models('http://127.0.0.1/v1', ['local'])


def test_fields_units_and_known_aliases(corpus):
    assert ev.parse_fields('**context:** Class 8 CBSE\n- notebook: UNKNOWN')['context'] == 'Class 8 CBSE'
    assert ev.matches('Class 8, Central Board of Secondary Education', corpus['personas'][0]['facts']['original'])
    assert ev.matches('I use 90 g/m² notebook paper', corpus['personas'][1]['facts']['original'])
    assert ev.matches('44100Hz', corpus['personas'][12]['facts']['original'])
    assert not ev.matches('Mira', corpus['personas'][0]['facts']['original'])


def test_prompt_scope_is_not_an_account_wide_read_boundary():
    rows = [{'id':1,'scope':'global','workspace':None}, {'id':2,'scope':'workspace','workspace':'/A'}, {'id':3,'scope':'workspace','workspace':'/B'}]
    ev.scope_check(rows, {1,2}, '/A')
    with pytest.raises(ev.HarnessError, match='scope'):
        ev.scope_check(rows, {1,2,3}, '/A')
    block, ids = ev.injected([{'role':'system','content':'Memory guidance\n\nKnown memories (from earlier sessions):\n- [#1] Global\n- [#2] A'}])
    assert ids == {1,2}


def records_for(p):
    facts, rows, records = p['facts'], [], []
    def add(key):
        rows.append({'id':len(rows)+1, 'content':facts[key]['value'], 'scope':facts[key]['scope'],
                     'workspace':'/A' if key=='A' else '/B' if key=='B' else None})
    for c in p['conversations']:
        before = copy.deepcopy(rows)
        if c['id']=='C4':
            for k in c['expected_saves']:
                add(k)
        elif c['id']=='C5':
            add('B')
        elif c['id']=='C8':
            rows = [r for r in rows if not ev.matches(r['content'],facts['original']) and not ev.matches(r['content'],facts['notebook'])]
            add('corrected')
        fields = {field: 'UNKNOWN' if key=='UNKNOWN' else 'Guard-P16' if key=='PEER' else facts[key]['value'] + (' because '+facts['reason']['value'] if key=='style' else '') for field,key in c['probe_expected'].items()}
        turns = [{'fields':fields, 'reply':'\n'.join(f'{k}: {v}' for k,v in fields.items()), 'before':before,
                  'after':copy.deepcopy(rows), 'events':[], 'messages':[], 'errors':[], 'permission_requests':0,
                  'visible_permission_request':False, 'unrelated_approvals':0} for _ in c['messages']]
        records.append({'chat':c['id'],'actor':c['actor'],'workspace_path':'/A' if c['workspace']=='A' else '/B',
                        'before':before,'after':copy.deepcopy(rows),'turns':turns,'injected_memory':'',
                        'infrastructure':{'cross_account':True}})
    return records


def test_scoring_keeps_automatic_and_explicit_separate(corpus):
    p=corpus['personas'][0]
    s=ev.score_persona(p,records_for(p))
    assert s['automatic_original_save'] is False
    # A lucky correct answer without persisted memory is not joint success.
    assert s['automatic_original_recall'] is True
    assert s['automatic_original_save_and_recall'] is False
    assert s['explicit_original_save'] is True
    assert s['correction_replaced_active_value'] is True
    assert s['forgetting_survives_restart'] is True
    assert s['explicit_A_scope'] is True and s['explicit_B_scope'] is True


def test_missing_controls_never_vacuously_pass(corpus):
    p=corpus['personas'][0]
    records=records_for(p)
    records[7]['before']=[]
    s=ev.score_persona(p,records)
    assert s['correction_exercised'] is False
    assert s['correction_replaced_active_value'] is None
    assert s['forgetting_deleted_value'] is None
    assert s['forgetting_survives_restart'] is None


def test_questions_are_not_automatic_saves_and_missing_fields_fail(corpus):
    p=corpus['personas'][0]
    records=records_for(p)
    records[2]['before']=copy.deepcopy(records[3]['after'])
    records[0]['turns'][0]['permission_requests']=1
    records[8]['turns'][0]['fields'].pop('notebook')
    s=ev.score_persona(p,records)
    assert s['automatic_original_save'] is False
    assert s['permission_requests']==1
    assert s['C9_notebook_recall'] is False
    assert s['format_errors']==1


def test_temporary_duplicates_errors_and_false_claims(corpus):
    p=corpus['personas'][0]
    records=records_for(p)
    temp={'id':99,'content':'Spark-P01','scope':'global','workspace':None}
    records[1]['turns'][1]['after'].append(temp)
    records[1]['turns'][1]['events']=[{'type':'tool_proposed','data':{'name':'remember','arguments':{'content':'Spark-P01'}}},
                                   {'type':'tool_started','data':{'name':'remember'}}]
    records[0]['turns'][0]['errors']=[{'type':'timeout'}]
    records[0]['turns'][0]['reply']="I'll remember that."
    records[0]['turns'][0]['messages']=[{'role':'tool','content':'invalid JSON _raw'}]
    records[9]['before'].append(copy.deepcopy(records[9]['before'][0]))
    s=ev.score_persona(p,records)
    assert s['temporary_saved_rows']==1 and s['temporary_save_attempts']==1
    assert s['turn_errors']==1 and s['malformed_tool_results']==1 and s['false_save_claims']==1
    assert s['duplicate_active_facts']>=1


def test_permission_group_encoding():
    assert ev.permission_answer({'question':'remember?'}) == ev.ANSWER
    assert json.loads(ev.permission_answer({'questions':[{'header':'a'},{'question':'b'}]})) == {'a':ev.ANSWER,'b':ev.ANSWER}


def test_stream_usage_can_cross_chunks_and_missing_is_null():
    assert ev.sse_usage(['data: {"us','age": {"prompt_tokens": 3}}\n\ndata: [DONE]\n']) == {'prompt_tokens':3}
    assert ev.sse_usage(['data: [DONE]\n']) is None
    report={'evaluations':[],'requests':[{'kind':'title','seconds':1,'queue_seconds':2,'status':200,'usage':None}]}
    ev.summarize(report)
    assert report['usage']['title']['input_tokens'] is None
    assert report['usage']['title']['missing_usage_requests']==1
    assert report['cost_usd'] is None


def test_proxy_unknown_routes_and_models_never_go_upstream(tmp_path):
    app=ev.recording_app('http://127.0.0.1:1234/v1',['local'],tmp_path/'requests.jsonl')
    with TestClient(app) as client:
        assert client.get('/v1/models').json()['data'][0]['id']=='local'
        assert client.post('/v1/chat/completions',json={'model':'openrouter:x'}).status_code==400
        assert client.get('/openrouter').status_code==404


def test_snapshot_reads_without_mutation(tmp_path):
    from coworker.memory import SQLiteMemoryStore,Scope
    state=tmp_path/'state'; state.mkdir()
    store=SQLiteMemoryStore(state/'coworker.db')
    store.add('synthetic',scope=Scope.GLOBAL)
    assert ev.snapshot(tmp_path)[0]['content']=='synthetic'
    store.close()


def test_cleanup_refuses_unowned_and_is_idempotent(tmp_path):
    with pytest.raises(ev.HarnessError,match='unowned'):
        ev.cleanup_batch(tmp_path)
    assert ev.main(['cleanup','--root',str(tmp_path/'missing')])==0


def test_pid_reuse_does_not_kill(monkeypatch):
    monkeypatch.setattr(ev,'process_stamp',lambda pid:'new')
    monkeypatch.setattr(ev.os,'kill',lambda *args: pytest.fail('must not kill reused PID'))
    ev.stop_process({'pid':1,'stamp':'old'})


def test_redaction_preserves_synthetic_facts():
    assert ev.redact({'cookie':'secret','content':'Grade 8 CBSE at /private/home/A'}, ['secret'], [('/private/home','<account:P01>')]) == {'cookie':'[REDACTED]','content':'Grade 8 CBSE at <account:P01>/A'}


def test_existing_fixture_defaults_and_owned_custom_workspaces(tmp_path):
    from scripts import hosted_browser_fixture as fixture
    args=SimpleNamespace(root=tmp_path/'batch',mode='fixture',model_port=18767,origin='https://127.0.0.1:18453',flows=False)
    fixture.prepare(args)
    manifest=json.loads((args.root/'manifest.json').read_text())
    assert [u['username'] for u in manifest['accounts']]==['alice','bob']
    with pytest.raises(FileExistsError):
        fixture.prepare(args)


def test_recording_proxy_forwarding_usage_errors_and_no_retry(tmp_path, monkeypatch):
    from coworker.server.manager import SessionManager
    original = httpx.AsyncClient
    calls=[]
    def upstream(request):
        body=json.loads(request.content)
        calls.append((str(request.url), body))
        if body.get('bad'):
            return httpx.Response(302,headers={'location':'https://openrouter.ai'})
        usage={'prompt_tokens':7,'completion_tokens':3}
        if body.get('stream'):
            return httpx.Response(200,text='data: '+json.dumps({'usage':usage})+'\n\ndata: [DONE]\n',headers={'content-type':'text/event-stream'})
        return httpx.Response(200,json={'choices':[],'usage':usage})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs: original(transport=httpx.MockTransport(upstream),**kwargs))
    ledger=tmp_path/'requests.jsonl'
    with TestClient(ev.recording_app('http://127.0.0.1:1234/v1',['local'],ledger)) as client:
        body={'model':'local','messages':[{'role':'system','content':SessionManager._AUTOTITLE_PROMPT}]}
        assert client.post('/v1/chat/completions',json=body).status_code==200
        assert client.post('/v1/chat/completions',json={'model':'local','messages':[],'stream':True}).status_code==200
        assert client.post('/v1/chat/completions',json={'model':'local','messages':[],'bad':True}).status_code==502
    records=[json.loads(line) for line in ledger.read_text().splitlines()]
    assert [r['kind'] for r in records]==['title','main','main']
    assert records[0]['usage']['prompt_tokens']==7
    assert records[1]['usage']['completion_tokens']==3
    assert records[2]['error']=='HarnessError'
    assert len(calls)==3
    assert all(url=='http://127.0.0.1:1234/v1/chat/completions' for url,body in calls)


def test_proxy_serializes_concurrent_requests(tmp_path, monkeypatch):
    import asyncio
    import concurrent.futures
    original=httpx.AsyncClient
    active=0; peak=0
    async def upstream(request):
        nonlocal active,peak
        active+=1; peak=max(peak,active)
        await asyncio.sleep(.03)
        active-=1
        return httpx.Response(200,json={'choices':[]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs: original(transport=httpx.MockTransport(upstream),**kwargs))
    with TestClient(ev.recording_app('http://127.0.0.1:1234/v1',['local'],tmp_path/'ledger')) as client:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(client.post,'/v1/chat/completions',json={'model':'local','messages':[]}) for _ in range(2)]
            assert all(f.result().status_code==200 for f in futures)
    assert peak==1


def test_custom_fixture_accounts_keep_model_configuration(tmp_path):
    from scripts import hosted_browser_fixture as fixture
    args=SimpleNamespace(root=tmp_path/'batch',mode='fixture',model_port=18767,origin='https://127.0.0.1:18453',flows=False)
    fixture.prepare(args,account_names=['p01','sentinel'],model_config=ev.MODEL_CONFIG)
    manifest=json.loads((args.root/'manifest.json').read_text())
    assert [u['username'] for u in manifest['accounts']]==['p01','sentinel']
    config=(Path(manifest['accounts'][0]['home'])/'state/config.toml').read_text()
    assert 'max_iterations = 6' in config and 'reasoning_effort = "low"' in config


def test_gateway_preserves_runtime_home_not_cloud_credentials(tmp_path, monkeypatch):
    import os
    captured={}
    class Process:
        pid=12345
        def poll(self): return None
    def popen(argv, **kwargs):
        captured.update(argv=argv,env=kwargs['env'])
        return Process()
    monkeypatch.setenv('OPENROUTER_API_KEY','must-not-cross')
    monkeypatch.setenv('OPENAI_API_KEY','must-not-cross')
    monkeypatch.setattr(ev.subprocess,'Popen',popen)
    monkeypatch.setattr(ev,'process_stamp',lambda pid:'stamp')
    monkeypatch.setattr(httpx,'get',lambda url,**kwargs: httpx.Response(401,request=httpx.Request('GET',url)))
    ev.dump(tmp_path/'manifest.json',{'engine_ports':[12346]})
    args=SimpleNamespace(root=tmp_path,spa=tmp_path/'spa',gateway_port=18866)
    process=ev.start_gateway(args)
    assert captured['env']['HOME']==os.environ['HOME']
    assert 'OPENROUTER_API_KEY' not in captured['env'] and 'OPENAI_API_KEY' not in captured['env']
    assert '_serve' in captured['argv'] and str(tmp_path) in captured['argv']
    # Restart uses the same root without provisioning/overwriting data.
    assert ev.start_gateway(args).pid==process.pid
    assert json.loads((tmp_path/'manifest.json').read_text())=={'engine_ports':[12346]}


def test_unknown_explanation_is_absence_but_control_mention_is_not(corpus):
    p=corpus['personas'][0]
    records=records_for(p)
    records[2]['turns'][0]['fields']['temporary_label']='UNKNOWN (no retained record of a previous draft label)'
    records[8]['turns'][0]['fields']['notebook']='UNKNOWN (the old label was Solace-P01)'
    s=ev.score_persona(p,records)
    assert s['C3_temporary_label_recall'] is True
    assert s['C9_notebook_recall'] is False


def test_free_port_guard_matches_server_reuse_semantics(monkeypatch):
    class Socket:
        reusable=False
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def setsockopt(self,level,key,value):
            assert key==ev.socket.SO_REUSEADDR and value==1
            self.reusable=True
        def bind(self,address):
            assert self.reusable, 'TIME_WAIT must not be confused with a listener'
    monkeypatch.setattr(ev.socket,'socket',Socket)
    ev.port_free(18867)


def test_correct_heading_does_not_hide_wrong_workspace_mentions(corpus):
    p=corpus['personas'][0]
    records=records_for(p)
    records[5]['turns'][0]['reply']+='\nAlso known: Harbor-P01'
    records[5]['injected_memory']='Anchor-P01 and Harbor-P01'
    scores=ev.score_persona(p,records)
    assert scores['C6_heading_recall'] is True
    assert scores['C6_B_absent_from_reply'] is False
    assert scores['C6_B_absent_from_prompt'] is False
    assert scores['wrong_workspace_reply_mentions']==1


def test_unknown_reply_does_not_prove_temporary_memory_was_removed(corpus):
    p=corpus['personas'][0]
    records=records_for(p)
    records[9]['before'].append({'id':99,'scope':'workspace','workspace':'/A','content':'Spark-P01'})
    scores=ev.score_persona(p,records)
    assert scores['C10_temporary_label_recall'] is True
    assert scores['C10_temporary_absent_from_active_memory'] is False
