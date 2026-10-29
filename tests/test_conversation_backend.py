"""Real Flask/SQLite integration without starting an operational server."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
import pytest
from _conversation_transport import EncryptedClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'conversation-app'))
spec = importlib.util.spec_from_file_location('conversation_server_test', ROOT / 'conversation-app/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
_create_app = server.create_app
def create_test_app(*args, **kwargs):
    app = _create_app(*args, **kwargs)
    app.test_client_class = EncryptedClient
    return app
from services.conversations import Store


class FakeProvider:
    def __init__(self):
        self.calls = 0
        self.enter = threading.Event()
        self.release = threading.Event()

    def models(self, account, force=False):
        return [{'model': 'test', 'displayName': 'Test', 'defaultReasoningEffort': 'low',
                 'supportedReasoningEfforts': [{'reasoningEffort': 'low'}]}]

    def run(self, account, settings, history, emit, cancel):
        self.calls += 1
        emit('provider', {'thread_id': 'thread-' + str(self.calls), 'turn_id': 'turn', 'model': 'test', 'reasoning_effort': 'low'})
        emit('delta', {'text': 'Hello'})
        emit('usage', {'total': {'inputTokens': 100, 'cachedInputTokens': 50, 'outputTokens': 10, 'totalTokens': 110}})
        self.enter.set()
        while not self.release.wait(.01):
            if cancel.is_set():
                emit('done', {'status': 'cancelled'})
                return
        emit('usage', {'total': {'inputTokens': 100, 'cachedInputTokens': 50, 'outputTokens': 15, 'totalTokens': 115}})
        emit('done', {'status': 'completed'})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    account = {'id': 'personal', 'label': 'Personal', 'authenticated': True, 'provider_account_id': 'provider-id'}
    monkeypatch.setattr(server, 'accounts', lambda: [account])
    monkeypatch.setattr(server, 'get_account', lambda _: account)
    provider = FakeProvider()
    app = create_test_app(tmp_path, provider)
    app.testing = True
    client = app.test_client()
    client.get('/')
    with client.session_transaction() as sess:
        csrf = sess['csrf']
    headers = {'X-Chat-CSRF': csrf}
    yield app, client, headers, provider
    provider.release.set()


def post(client, headers, path, value):
    return client.post(path, json=value, headers=headers)


def submit(client, headers, cid, rid='request-12345', **extra):
    return post(client, headers, f'/api/conversations/{cid}/messages', {
        'content': '안녕하세요', 'request_id': rid,
        'settings': {'account_id': 'personal', 'model': 'test', 'effort': 'low', 'search': 'off'}, **extra})


def wait_done(store, aid):
    end = time.monotonic() + 3
    while time.monotonic() < end:
        row = store.attempt(aid)
        if row['status'] in ('completed', 'cancelled', 'failed'):
            return row
        time.sleep(.01)
    raise AssertionError('worker did not complete')


def test_duplicate_sse_cancel_retry_delete_and_usage_survives(setup):
    app, client, headers, provider = setup
    store = app.extensions['chat_store']
    cid = post(client, headers, '/api/conversations', {}).json['id']
    first = submit(client, headers, cid)
    assert first.status_code == 202
    aid = first.json['attempt']['id']
    assert provider.enter.wait(2)
    assert submit(client, headers, cid).json['attempt']['id'] == aid
    assert provider.calls == 1
    assert submit(client, headers, cid, 'different-request').status_code == 400
    assert client.delete('/api/conversations/' + cid, headers=headers).status_code == 400
    post(client, headers, f'/api/attempts/{aid}/cancel', {})
    assert wait_done(store, aid)['status'] == 'cancelled'
    assert store.usage()['total_tokens'] == 110
    events = client.get(f'/api/attempts/{aid}/events').data.decode()
    assert 'event: delta' in events and 'cancelled' in events
    last = store.events(aid, 0)[-2]['id']
    resumed = client.get(f'/api/attempts/{aid}/events', headers={'Last-Event-ID': str(last)}).data.decode()
    assert 'event: delta' not in resumed and 'cancelled' in resumed
    provider.release.set()
    again = submit(client, headers, cid, 'request-retry', retry_attempt_id=aid).json['attempt']['id']
    assert wait_done(store, again)['status'] == 'completed'
    assert len(store.messages(cid)) == 1
    assert len(store.messages(cid)[0]['attempts']) == 2
    assert store.usage()['total_tokens'] == 225
    assert client.delete('/api/conversations/' + cid, headers=headers).status_code == 200
    assert store.usage()['total_tokens'] == 225
    assert client.get(f'/api/attempts/{aid}/events').status_code == 404


def test_origin_host_csrf_and_settings_assets(setup):
    app, client, headers, _ = setup
    assert client.get('/health').status_code == 200
    assert client.post('/api/conversations', json={}).status_code == 403
    assert client.post('/api/conversations', json={}, headers={**headers, 'Origin': 'http://evil.test'}).status_code == 403
    assert client.get('/api/conversations', headers={'Host': 'evil.test'}).status_code == 403
    assert client.get('/api/conversations', environ_overrides={'REMOTE_ADDR': '192.168.1.2'}).status_code == 403
    assert client.get('/static/vendor/marked-18.0.6.umd.js').status_code == 200
    assert client.get('/static/vendor/xterm-5.5.0.js').status_code == 404
    assert client.get('/static/fonts/suit/SUIT-Variable.woff2').status_code == 200
    assert client.patch('/api/settings', json={'model': 'test'}, headers=headers).status_code == 200
    assert client.get('/api/settings').json['model'] == 'test'
    assert 'frame-ancestors' in client.get('/').headers['Content-Security-Policy']


def test_recovery_idempotent_usage_and_actual_search_sources(tmp_path):
    store = Store(tmp_path)
    cid = store.create()['id']
    opts = {'account_id': 'a', 'provider_account_id': 'p', 'model': 'test', 'effort': 'low', 'search': 'on'}
    row, _ = store.enqueue(cid, 'question', 'request-unique', opts)
    aid = row['id']
    store.emit(aid, 'provider', {'thread_id': 't', 'turn_id': 'u', 'model': 'test'})
    usage = {'total': {'inputTokens': 90, 'outputTokens': 10, 'totalTokens': 100}}
    store.emit(aid, 'usage', usage)
    store.emit(aid, 'usage', usage)
    store.emit(aid, 'search', {'status': '자료 확인 중', 'item': {'results': [{'url': 'https://example.com/research', 'title': 'Research'}, {'url': 'javascript:bad'}]}})
    assert store.usage()['total_tokens'] == 100
    recovered = Store(tmp_path)
    assert recovered.attempt(aid)['status'] == 'interrupted'
    assert recovered.attempt(aid)['citations'][0]['searched_at']
    assert len(recovered.attempt(aid)['citations']) == 1
    assert recovered.events(aid, 0)[-1]['type'] == 'done'
    assert recovered.usage()['total_tokens'] == 100


def test_search_on_without_search_is_failed(tmp_path):
    store = Store(tmp_path)
    row, _ = store.enqueue(store.create()['id'], 'question', 'request-search', {'search': 'on'})
    store.emit(row['id'], 'done', {'status': 'completed'})
    assert store.attempt(row['id'])['status'] == 'failed'


def test_cancel_before_usage_is_pending_not_confirmed_zero(tmp_path):
    store = Store(tmp_path)
    row, _ = store.enqueue(store.create()['id'], 'hello', 'request-pending', {
        'account_id': 'a', 'provider_account_id': 'p', 'model': 'm', 'search': 'off'})
    store.emit(row['id'], 'provider', {'thread_id': 't', 'turn_id': 'u'})
    store.emit(row['id'], 'delta', {'text': 'partial'})
    store.emit(row['id'], 'done', {'status': 'cancelled'})
    assert store.attempt(row['id'])['usage'] is None
    assert store.usage()['pending_attempts'] == 1
    with store.db() as db:
        event = json.loads(db.execute('SELECT event FROM usage_outbox').fetchone()[0])
    assert event['usage_pending'] is True
    assert event['status'] == 'cancelled'


def test_entrypoint_uses_loopback_without_host_flag(tmp_path, monkeypatch):
    from flask import Flask
    spec = importlib.util.spec_from_file_location('chat_entrypoint_test', ROOT / 'run_conversation_server.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    called = []
    monkeypatch.setenv('CHAT_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(sys, 'argv', ['run_conversation_server.py', '--port', '3101'])
    monkeypatch.setattr(Flask, 'run', lambda self, **kwargs: called.append(kwargs))
    entry.main()
    assert len(called) == 1
    assert called[0]['host'] == '127.0.0.1'
    assert called[0]['port'] == 3101
    assert not called[0]['debug'] and not called[0]['use_reloader']


def test_explicit_tailnet_access_preserves_host_origin_and_csrf(tmp_path, monkeypatch):
    monkeypatch.setenv('CHAT_ALLOWED_HOSTS', 'chat.example.ts.net')
    monkeypatch.setenv('CHAT_ALLOWED_NETWORKS', '100.64.0.0/10')
    app = create_test_app(tmp_path, FakeProvider())
    client = app.test_client()
    base = 'http://chat.example.ts.net:3101'
    peer = {'REMOTE_ADDR': '100.80.1.2'}
    assert client.get('/', base_url=base, environ_overrides=peer).status_code == 200
    with client.session_transaction(base_url=base) as session:
        csrf = session['csrf']
    headers = {'X-Chat-CSRF': csrf, 'Origin': base}
    assert client.post('/api/conversations', base_url=base, environ_overrides=peer,
                       json={}, headers=headers).status_code == 200
    assert client.get('/health', base_url='http://100.80.1.1:3101', environ_overrides=peer).status_code == 200
    assert client.get('/health', base_url='http://192.168.1.1:3101', environ_overrides=peer).status_code == 403
    for bad_peer in ('192.168.1.2', '203.0.113.2'):
        assert client.get('/health', base_url=base,
                          environ_overrides={'REMOTE_ADDR': bad_peer}).status_code == 403
    assert client.get('/health', base_url='http://evil.test:3101', environ_overrides=peer).status_code == 403
    assert client.get('/health', base_url=base, environ_overrides={'REMOTE_ADDR': '203.0.113.2'},
                      headers={'X-Forwarded-For': '100.80.1.2'}).status_code == 403
    assert client.post('/api/conversations', base_url=base, environ_overrides=peer,
                       json={}, headers={**headers, 'Origin': 'http://evil.test'}).status_code == 403
    assert client.post('/api/conversations', base_url=base, environ_overrides=peer,
                       json={}, headers={'Origin': base}).status_code == 403
    assert client.get('/health').status_code == 200


def test_entrypoint_accepts_explicit_external_access(tmp_path, monkeypatch):
    from flask import Flask
    spec = importlib.util.spec_from_file_location('chat_external_entrypoint', ROOT / 'run_conversation_server.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    called = []
    monkeypatch.setenv('CHAT_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('CHAT_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('CHAT_ALLOWED_NETWORKS', raising=False)
    monkeypatch.setattr(sys, 'argv', ['run_conversation_server.py', '--host', '0.0.0.0',
                                    '--allowed-host', 'chat.example.ts.net',
                                    '--allowed-network', '100.64.0.0/10'])
    monkeypatch.setattr(Flask, 'run', lambda self, **kwargs: called.append(kwargs))
    entry.main()
    assert called[0]['host'] == '0.0.0.0'
    assert entry.os.environ['CHAT_ALLOWED_HOSTS'] == 'chat.example.ts.net'
    assert entry.os.environ['CHAT_ALLOWED_NETWORKS'] == '100.64.0.0/10'


@pytest.mark.parametrize('external_origin', ['https://chat.example.ts.net:8443',
                                           'https://chat.trycloudflare.com'])
def test_local_https_gateway_origin_requires_csrf(setup, external_origin):
    app, client, headers, provider = setup
    forwarded = {**headers, 'Origin': external_origin,
                 'X-Forwarded-Host': external_origin.split('://', 1)[1],
                 'X-Forwarded-Proto': 'https', 'X-Forwarded-Prefix': '/apps/chat'}
    assert client.get('/api/accounts', headers=forwarded).json['accounts'][0]['id'] == 'personal'
    assert client.get('/api/models?account_id=personal', headers=forwarded).json['models'][0]['model'] == 'test'
    assert client.patch('/api/settings', headers=forwarded,
                        json={'model': 'test'}).status_code == 200
    assert client.post('/api/conversations', headers=forwarded, json={}).status_code == 200
    assert client.post('/api/conversations', headers={**forwarded, 'X-Chat-CSRF': ''},
                       json={}).status_code == 403
    assert client.post('/api/conversations', headers={**forwarded, 'Origin': 'https://evil.test'},
                       json={}).status_code == 403


def test_remote_peer_cannot_forward_origin_or_bypass_access(tmp_path, monkeypatch):
    monkeypatch.setenv('CHAT_ALLOWED_NETWORKS', '100.64.0.0/10')
    app = create_test_app(tmp_path, FakeProvider())
    client = app.test_client()
    client.get('/')
    with client.session_transaction() as sess:
        csrf = sess['csrf']
    headers = {'X-Chat-CSRF': csrf, 'Origin': 'https://evil.test',
               'X-Forwarded-Host': 'evil.test', 'X-Forwarded-Proto': 'https'}
    for peer in ('100.80.1.2', '203.0.113.2'):
        assert client.post('/api/conversations', headers=headers, json={},
                           environ_overrides={'REMOTE_ADDR': peer}).status_code == 403
    for host in ('evil.test,other.test', 'evil.test/path', 'user@evil.test', 'evil.test?x=1'):
        assert client.post('/api/conversations', headers={**headers, 'X-Forwarded-Host': host},
                           json={}).status_code == 403


def test_cloudflare_duplicate_forwarding_headers(setup):
    _, client, headers, _ = setup
    external = 'https://painted-slideshow-hampshire-main.trycloudflare.com'
    forwarded = {**headers, 'Origin': external, 'Sec-Fetch-Site': 'same-origin',
                 'X-Forwarded-Host': 'localhost:19443, painted-slideshow-hampshire-main.trycloudflare.com',
                 'X-Forwarded-Proto': 'https, http'}
    assert client.post('/api/conversations', json={}, headers=forwarded).status_code == 200
    assert client.post('/api/conversations', json={}, headers={**forwarded, 'Origin': 'https://evil.test', 'Sec-Fetch-Site': 'cross-site'}).json['code'] == 'origin_mismatch'
    assert client.post('/api/conversations', json={}, headers={**forwarded, 'X-Chat-CSRF': ''}).json['code'] == 'csrf_mismatch'


def test_local_proxy_same_origin_fetch_with_replaced_host(setup):
    _, client, headers, _ = setup
    browser = {**headers, 'Origin': 'https://public.example.com', 'Sec-Fetch-Site': 'same-origin'}
    assert client.post('/api/conversations', json={}, headers=browser).status_code == 200
    assert client.post('/api/conversations', json={}, headers={**browser, 'X-Chat-CSRF': ''}).json['code'] == 'csrf_mismatch'
    assert client.post('/api/conversations', json={}, headers={**browser, 'Sec-Fetch-Site': 'cross-site'}).json['code'] == 'origin_mismatch'
    assert client.post('/api/conversations', json={}, headers={**browser, 'Host': 'public.example.com'}).json['code'] == 'host_not_allowed'
    assert client.post('/api/conversations', json={}, headers=browser, environ_overrides={'REMOTE_ADDR': '203.0.113.1'}).json['code'] == 'network_not_allowed'


def test_cloudflare_browser_can_send_prompt_without_repository_scope(setup):
    _, client, headers, provider = setup
    browser = {**headers, 'Origin': 'https://public.trycloudflare.com',
               'Sec-Fetch-Site': 'same-origin', 'X-Forwarded-Proto': 'https, http'}
    cid = client.post('/api/conversations', headers=browser, json={}).json['id']
    response = client.post(f'/api/conversations/{cid}/messages', headers=browser, json={
        'content': 'hello', 'request_id': 'cloudflare-request-123',
        'settings': {'account_id': 'personal', 'model': 'test', 'effort': 'low', 'search': 'off',
                     'artifact_scope': '/Users/dinya/works/dev_workspace'}})
    assert response.status_code == 202
    assert response.json['attempt']['settings']['artifact_scope'] == cid
    assert provider.enter.wait(2)
    assert provider.calls == 1


def test_auto_title_is_first_turn_only_and_respects_manual_rename(tmp_path):
    store = Store(tmp_path)
    settings = {'account_id': 'a', 'provider_account_id': 'p', 'model': 'test', 'search': 'off'}
    cid = store.create()['id']
    attempt, _ = store.enqueue(cid, 'first prompt', 'title-request-one', settings)
    assert attempt['settings']['generate_title'] is True
    store.emit(attempt['id'], 'title', {'title': 'LLM title'})
    assert store.conversations()[0]['title'] == 'LLM title'
    store.emit(attempt['id'], 'delta', {'text': 'answer'})
    store.emit(attempt['id'], 'done', {'status': 'completed'})
    assert store.attempt(attempt['id'])['text'] == 'answer'
    second, _ = store.enqueue(cid, 'second prompt', 'title-request-two', settings)
    assert second['settings']['generate_title'] is False
    store.emit(second['id'], 'title', {'title': 'wrong title'})
    assert store.conversations()[0]['title'] == 'LLM title'
    other = store.create()['id']
    pending, _ = store.enqueue(other, 'prompt', 'title-request-three', settings)
    store.change(other, 'My chosen title')
    store.emit(pending['id'], 'title', {'title': 'Late LLM title'})
    assert next(row for row in store.conversations() if row['id'] == other)['title'] == 'My chosen title'


def test_limit_endpoint_uses_selected_account(setup, monkeypatch):
    _, client, _, provider = setup
    calls = []
    def limits(account, force=False):
        calls.append((account['id'], force))
        return {'five_hour': {'used_percent': 12, 'remaining_percent': 88}, 'weekly': None}
    monkeypatch.setattr(provider, 'limits', limits, raising=False)
    response = client.get('/api/usage/limits?account_id=personal&refresh=1')
    assert response.status_code == 200
    assert response.json['five_hour']['remaining_percent'] == 88
    assert calls == [('personal', True)]


def test_legacy_title_is_preserved_when_retrying_first_message(tmp_path):
    store = Store(tmp_path)
    settings = {'account_id': 'a', 'provider_account_id': 'p', 'model': 'test', 'search': 'off'}
    cid = store.create()['id']
    attempt, _ = store.enqueue(cid, 'original prompt', 'legacy-first-request', settings)
    store.emit(attempt['id'], 'done', {'status': 'completed'})
    with store.db() as db:
        db.execute('DELETE FROM conversation_titles WHERE conversation_id=?', (cid,))
        db.execute('UPDATE conversations SET title=? WHERE id=?', ('기존 대화 제목', cid))
    retried, _ = store.enqueue(cid, '', 'legacy-retry-request', settings, retry=attempt['id'])
    assert retried['settings']['generate_title'] is False
    store.emit(retried['id'], 'title', {'title': '덮어쓰면 안 되는 제목'})
    assert store.conversations()[0]['title'] == '기존 대화 제목'
