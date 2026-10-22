"""Company pool persistence, rotation, and administrator access regressions."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services import company_credentials as credentials
from codex_agent.services import codex_chat as chat
from codex_agent import codex_app
from codex_agent.blueprints import codex_chat as routes


@pytest.fixture
def pool(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setenv('CODEX_COMPANY_MODE', '1')
    monkeypatch.setattr(credentials, 'CODEX_STORAGE_DIR', tmp_path)
    monkeypatch.setattr(credentials, 'is_internal_multiuser_mode', lambda: False)
    monkeypatch.setattr(credentials, '_credential_path', lambda: tmp_path / 'legacy.dpapi')
    monkeypatch.setattr(credentials, '_session_api_key', '')
    monkeypatch.setattr(credentials, '_session_api_keys', {})
    return credentials.update_internal_api_key_allocation({'keys': [
        {'label': 'first', 'api_key': 'private-key-alpha'},
        {'label': 'second', 'api_key': 'private-key-beta'},
    ]})


def test_linux_pool_encrypted_persistent_and_status_does_not_rotate(pool):
    path = credentials._internal_pool_path()
    assert b'private-key' not in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.with_suffix('.key').stat().st_mode & 0o777 == 0o600
    assert 'private-key' not in json.dumps(pool)
    for _ in range(3):
        assert credentials.get_company_credential_status()['source'] == 'internal_pool'
    selected = [credentials.reserve_internal_api_key()['label'] for _ in range(3)]
    assert selected == ['first', 'second', 'first']
    # A new read uses disk state; editing labels with omitted secrets retains keys.
    pool['keys'][0]['label'] = 'renamed'
    credentials.update_internal_api_key_allocation(pool)
    assert credentials.reserve_internal_api_key()['secret'] == 'private-key-beta'


def test_pool_concurrent_reservations_and_execution_reuses_reserved_key(pool):
    with ThreadPoolExecutor(max_workers=8) as executor:
        selected = list(executor.map(lambda _: credentials.reserve_internal_api_key(), range(20)))
    assert sum(key['label'] == 'first' for key in selected) == 10
    assert sum(key['label'] == 'second' for key in selected) == 10
    before = credentials.get_internal_api_key_allocation()
    env = {'ANTHROPIC_API_KEY': 'stale'}
    assert credentials.apply_company_api_key(env, internal_key=selected[0])
    assert env['DTGPT_API_KEY'] == selected[0]['secret']
    assert 'ANTHROPIC_API_KEY' not in env
    assert credentials.get_internal_api_key_allocation() == before


def test_empty_pool_falls_back_to_single_key_and_macos_does_not_use_pool(pool, monkeypatch):
    monkeypatch.setenv('DTGPT_API_KEY', 'fallback')
    credentials.update_internal_api_key_allocation({'keys': []})
    env = {}
    assert credentials.apply_company_api_key(env)
    assert env['DTGPT_API_KEY'] == 'fallback'
    monkeypatch.setattr(credentials, 'sys', SimpleNamespace(platform='darwin'))
    assert not credentials.company_key_pool_supported()
    assert credentials.resolve_company_api_key() == ('fallback', 'environment')


def test_linux_pool_fails_closed_when_encryption_key_missing(pool, monkeypatch):
    monkeypatch.setenv('DTGPT_API_KEY', 'must-not-bypass-broken-pool')
    credentials._internal_pool_path().with_suffix('.key').unlink()
    assert credentials.get_company_credential_status()['error'] == 'pool_encryption_key_unavailable'
    assert not credentials.apply_company_api_key({})


def test_company_pool_requires_admin_and_csrf(pool, monkeypatch):
    monkeypatch.setenv('CODEX_COMPANY_ADMIN_PASSWORD', 'test-admin')
    monkeypatch.setattr(codex_app, 'ensure_usage_snapshot_background_worker', lambda: None)
    monkeypatch.setattr(codex_app, 'ensure_pending_queue_background_worker', lambda: None)
    from codex_agent.services import usage_dashboard
    monkeypatch.setattr(usage_dashboard, 'ensure_collection_worker', lambda: None)
    app = codex_app.create_codex_app()
    app.config['TESTING'] = True
    client = app.test_client()
    endpoint = '/api/codex/company-credentials/key-pool'
    assert client.get(endpoint).status_code == 401
    with client.session_transaction() as session:
        session['company_admin_authenticated_at'] = time.time()
        session['company_admin_csrf'] = 'test-csrf'
    response = client.get(endpoint)
    assert response.status_code == 200
    assert 'private-key' not in response.get_data(as_text=True)
    assert client.put(endpoint, json={}).status_code == 403
    monkeypatch.setattr(routes, 'decrypt_credential_payload', lambda value: (value, 'test'))
    assert client.put(endpoint, json={'keys': []}, headers={
        'X-Codex-CSRF-Token': 'test-csrf', 'Origin': 'https://other.invalid',
    }).status_code == 403
    assert client.put(endpoint, json={'keys': []}, headers={
        'X-Codex-CSRF-Token': 'test-csrf', 'Origin': 'http://localhost',
    }).status_code == 200


def test_windows_company_pool_uses_dpapi_and_rotates(pool, monkeypatch):
    monkeypatch.setattr(credentials, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(credentials, '_protect_windows', lambda value: b'protected:' + value)
    monkeypatch.setattr(credentials, '_unprotect_windows', lambda value: value.removeprefix(b'protected:'))
    assert credentials.company_key_pool_supported()
    credentials.update_internal_api_key_allocation({'keys': [
        {'label': 'windows-a', 'api_key': 'windows-secret-a'},
        {'label': 'windows-b', 'api_key': 'windows-secret-b'},
    ]})
    assert credentials._internal_pool_path().suffix == '.dpapi'
    assert credentials._internal_pool_path().read_bytes().startswith(b'protected:')
    envs = [{}, {}, {}]
    for env in envs:
        assert credentials.apply_company_api_key(env)
    assert [env['DTGPT_API_KEY'] for env in envs] == [
        'windows-secret-a', 'windows-secret-b', 'windows-secret-a',
    ]
