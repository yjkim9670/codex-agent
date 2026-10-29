"""Cryptographic boundaries and encrypted HTTP/SSE integration."""
import base64
import json
import time
from urllib.parse import quote

import pytest
from _conversation_transport import EncryptedClient
from test_conversation_backend import create_test_app, FakeProvider, submit, wait_done


@pytest.fixture
def wire(tmp_path, monkeypatch):
    import test_conversation_backend as backend
    account = dict(id='personal', label='private-account', authenticated=True, provider_account_id='provider')
    monkeypatch.setattr(backend.server, 'accounts', lambda: [account])
    monkeypatch.setattr(backend.server, 'get_account', lambda _: account)
    provider = FakeProvider()
    app = create_test_app(tmp_path, provider)
    app.testing = True
    client = app.test_client()
    client.get('/')
    with client.session_transaction() as session:
        headers = {'X-Chat-CSRF': session['csrf']}
    _, channel = client.handshake(headers, {})
    yield app, client, headers, channel, provider
    provider.release.set()


def test_plain_apis_are_closed_and_spoofed_headers_do_not_bypass(wire):
    _, client, headers, _, _ = wire
    for path, method in [('/api/accounts', 'GET'), ('/api/conversations?q=secret', 'GET'),
                         ('/api/conversations', 'POST'), ('/api/settings', 'PATCH')]:
        response = client.raw_open(path, method=method, json={}, headers={**headers, 'Chat.Encrypted-Dispatch': 'true'})
        assert response.status_code == 428
        assert response.json['code'] == 'encrypted_transport_required'
    assert client.raw_open('/api/crypto-session', method='POST', json={}).status_code == 403
    assert client.get('/').headers['Cache-Control'] == 'no-store'
    assert client.get('/static/js/transport.js').headers['Cache-Control'] == 'private, max-age=86400'


def test_roundtrip_hides_prompts_search_history_titles_and_api_errors(wire):
    _, client, headers, channel, _ = wire
    private = '기밀 제목 / prompt 甲乙'
    cid = client.post('/api/conversations', headers=headers, json={}).json['id']
    client.patch('/api/conversations/' + cid, headers=headers, json={'title': private})
    for path in ['/api/accounts', '/api/conversations?q=' + quote(private), '/api/conversations/missing/messages']:
        envelope = client.seal(channel, dict(path=path, method='GET'))
        response = client.raw_open('/api/secure', method='POST', headers=headers, json=envelope)
        assert response.status_code == 200 and response.json['encrypted'] is True
        assert response.headers['Cache-Control'] == 'no-store'
        assert private.encode() not in response.data and b'private-account' not in response.data
        result = client.unseal(channel, envelope['iv'], response.json)
        assert result['status'] == (404 if 'missing' in path else 200)
        if '?q=' in path:
            assert result['body'][0]['title'] == private


def test_tamper_replay_expiry_and_other_browser_are_rejected(wire):
    app, client, headers, channel, _ = wire
    envelope = client.seal(channel, dict(path='/api/conversations', method='POST', body={}))
    altered = dict(envelope)
    cipher = bytearray(base64.b64decode(envelope['ciphertext']))
    cipher[-1] ^= 1
    altered['ciphertext'] = base64.b64encode(cipher).decode()
    assert client.raw_open('/api/secure', method='POST', headers=headers, json=altered).json['code'] == 'crypto_auth_failed'
    assert client.raw_open('/api/secure', method='POST', headers=headers, json=envelope).status_code == 200
    assert client.raw_open('/api/secure', method='POST', headers=headers, json=envelope).json['code'] == 'crypto_replay_rejected'
    assert len(app.extensions['chat_store'].conversations()) == 1
    other = app.test_client()
    other.get('/')
    with other.session_transaction() as session:
        other_headers = {'X-Chat-CSRF': session['csrf']}
    fresh = client.seal(channel, dict(path='/api/accounts'))
    assert other.raw_open('/api/secure', method='POST', headers=other_headers, json=fresh).json['code'] == 'crypto_session_owner_mismatch'
    app.extensions['chat_channels'].entries[channel['id']].expires = time.time() - 1
    assert client.raw_open('/api/secure', method='POST', headers=headers, json=fresh).json['code'] == 'crypto_session_expired'


@pytest.mark.parametrize('payload', [dict(path='/'), dict(path='https://evil/api/accounts'),
                         dict(path='/api/secure'), dict(path='/api/crypto-session'),
                         dict(path='/api/accounts', method='TRACE'), dict(path='/api/accounts', body=[]),
                         dict(path=4), dict(path='/api/accounts', method=4)])
def test_tunnel_cannot_dispatch_outside_api(wire, payload):
    _, client, headers, channel, _ = wire
    response = client.raw_open('/api/secure', method='POST', headers=headers, json=client.seal(channel, payload))
    assert response.status_code == 400


def test_batched_encrypted_stream_resume_and_snapshot_cursor(wire):
    app, client, headers, channel, provider = wire
    cid = client.post('/api/conversations', headers=headers, json={}).json['id']
    aid = submit(client, headers, cid).json['attempt']['id']
    assert provider.enter.wait(2)
    store = app.extensions['chat_store']
    snapshot = store.messages(cid)[0]['attempts'][0]
    assert snapshot['text'] == 'Hello' and snapshot['event_cursor'] > 0
    for _ in range(260):
        store.emit(aid, 'delta', {'text': '기밀응답'})
    provider.release.set()
    wait_done(store, aid)
    path = f"/api/attempts/{aid}/events?after={snapshot['event_cursor']}"
    envelope = client.seal(channel, dict(path=path))
    response = client.raw_open('/api/secure', method='POST', headers=headers, json=envelope)
    raw = response.get_data(as_text=True)
    assert '기밀응답' not in raw and 'event: delta' not in raw and 'completed' not in raw
    frames = [json.loads(frame[6:]) for frame in raw.strip().split('\n\n')]
    assert len(frames) == 3  # At most 128 persisted events per encrypted frame.
    chunks = [client.unseal(channel, envelope['iv'], frame, seq)['chunk'] for seq, frame in enumerate(frames)]
    text = ''.join(chunks)
    assert text.count('event: delta') == 260 and 'Hello' not in text and 'completed' in text
    with pytest.raises(Exception):  # Bound to the originating request, direction and sequence.
        client.unseal(channel, 'different-request', frames[0])
    with pytest.raises(AssertionError):
        client.unseal(channel, envelope['iv'], frames[1], 0)


def test_crypto_memory_is_bounded_and_expired_channels_are_pruned(wire):
    app, client, headers, _, _ = wire
    for _ in range(15):
        assert client.handshake(headers, {})[0].status_code == 200
    assert client.handshake(headers, {})[0].status_code == 429
    for channel in app.extensions['chat_channels'].entries.values():
        channel.expires = time.time() - 1
    assert client.handshake(headers, {})[0].status_code == 200
    assert len(app.extensions['chat_channels'].entries) == 1


@pytest.mark.parametrize('origin,forwarding', [
    ('https://chat.example.ts.net:8443', {'X-Forwarded-Host': 'chat.example.ts.net:8443',
                                       'X-Forwarded-Proto': 'https'}),
    ('https://chat.example.com', {'X-Forwarded-Host': 'chat.example.com', 'X-Forwarded-Proto': 'https'}),
    ('https://chat.trycloudflare.com', {'X-Forwarded-Host': 'localhost:19443, chat.trycloudflare.com',
                                      'X-Forwarded-Proto': 'https, http'}),
    ('https://chat.example.ts.net', {}),
])
def test_proxy_checks_apply_to_real_encrypted_endpoints(wire, origin, forwarding):
    app, client, headers, _, provider = wire
    browser = {**headers, **forwarding, 'Origin': origin, 'Sec-Fetch-Site': 'same-origin'}
    response, channel = client.handshake(browser, {})
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'

    def request(payload, **overrides):
        envelope = client.seal(channel, payload)
        response = client.raw_open('/api/secure', method='POST', headers={**browser, **overrides}, json=envelope)
        return response, envelope

    response, envelope = request(dict(path='/api/conversations', method='POST', body={}))
    cid = client.unseal(channel, envelope['iv'], response.json)['body']['id']
    assert response.headers['Cache-Control'] == 'no-store'
    assert request(dict(path='/api/accounts'), **{'X-Chat-CSRF': ''})[0].json['code'] == 'csrf_mismatch'
    assert request(dict(path='/api/accounts'), Origin='https://evil.test',
                   **{'Sec-Fetch-Site': 'cross-site'})[0].json['code'] == 'origin_mismatch'

    aid = submit(client, browser, cid).json['attempt']['id']
    assert provider.enter.wait(2)
    # Read a live frame before completion: a fully buffered relay would stall.
    response, envelope = request(dict(path=f'/api/attempts/{aid}/events?after=0'))
    try:
        assert response.mimetype == 'text/event-stream'
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.headers['X-Accel-Buffering'] == 'no'
        frame = json.loads(next(iter(response.response)).decode().strip()[6:])
        assert 'event: ' in client.unseal(channel, envelope['iv'], frame)['chunk']
        assert app.extensions['chat_store'].attempt(aid)['status'] not in ('completed', 'cancelled')
    finally:
        provider.release.set()
        response.close()


def test_encrypted_poll_is_immediate_bounded_and_resumes_without_duplicates(wire):
    app, client, headers, channel, provider = wire
    cid = client.post('/api/conversations', headers=headers, json={}).json['id']
    aid = submit(client, headers, cid).json['attempt']['id']
    assert provider.enter.wait(2)
    store = app.extensions['chat_store']
    cursor = store.messages(cid)[0]['attempts'][0]['event_cursor']
    path = f'/api/attempts/{aid}/poll?after='
    # A queued/running provider does not hold the response open.
    assert client.get(path + str(cursor)).json == dict(events=[], cursor=cursor, has_more=False)
    for _ in range(260):
        store.emit(aid, 'delta', {'text': '기밀응답'})
    provider.release.set()
    wait_done(store, aid)
    seen = []
    while True:
        envelope = client.seal(channel, dict(path=path + str(cursor)))
        response = client.raw_open('/api/secure', method='POST', headers=headers, json=envelope)
        assert response.mimetype == 'application/json'
        assert response.headers['Cache-Control'] == 'no-store'
        assert '기밀응답'.encode() not in response.data
        result = client.unseal(channel, envelope['iv'], response.json)['body']
        assert 0 < len(result['events']) <= 128
        assert all(row['id'] > cursor for row in result['events'])
        seen.extend(result['events'])
        cursor = result['cursor']
        if not result['has_more']:
            break
    assert len({row['id'] for row in seen}) == len(seen)
    assert sum(row['type'] == 'delta' for row in seen) == 260
    assert seen[-1]['type'] == 'done' and seen[-1]['data']['status'] == 'completed'
    assert client.get(path + str(cursor)).json['events'] == []
    assert client.raw_open(path + '0', method='GET').status_code == 428
    for invalid in ('bad', str(2**63)):
        assert client.get(path + invalid).status_code == 400
    assert client.get('/api/attempts/missing/poll').status_code == 404


def test_poll_reports_cancellation_and_recovery(wire):
    app, client, headers, _, provider = wire
    cid = client.post('/api/conversations', headers=headers, json={}).json['id']
    aid = submit(client, headers, cid).json['attempt']['id']
    assert provider.enter.wait(2)
    assert client.post(f'/api/attempts/{aid}/cancel', headers=headers, json={}).status_code == 200
    wait_done(app.extensions['chat_store'], aid)
    rows = client.get(f'/api/attempts/{aid}/poll').json['events']
    assert rows[-1]['data']['status'] == 'cancelled'
    # Store startup persists recovery in the same event log read by polling.
    store = app.extensions['chat_store']
    attempt, _ = store.enqueue(cid, 'recovery', 'request-recovery', {'model': 'test'}, None)
    from services.conversations import Store
    Store(store.path.parent)
    rows = client.get(f"/api/attempts/{attempt['id']}/poll").json['events']
    assert rows[-1]['type'] == 'done' and rows[-1]['data']['status'] == 'interrupted'
