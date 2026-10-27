from copy import deepcopy
import importlib
from pathlib import Path
import sys

from flask import Flask
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
api = importlib.import_module('codex_agent.blueprints.codex_chat')


@pytest.fixture
def usage_client(monkeypatch):
    usage = {
        'five_hour': {'used_percent': 12},
        'token_usage': {'today': {'total_tokens': 100}},
        'usage_reconciliation': {'trend': [{'tokens': 100}], 'observation_count': 1},
        'usage_events': {'recent': [{'tokens': 100}], 'by_model': {'model': 100}},
        'usage_keepalive': {'history': [{'status': 'completed'}]},
    }
    history = {
        'count': 2, 'items': [{'tokens': 100}], 'chart_items': [{'tokens': 100}],
        'relation': {'weekly': {'tokens_per_percent': 1000}},
        'calibration': {'recent': [{'id': 'sample'}], 'models': {'model': {}}},
    }
    originals = deepcopy((usage, history))
    monkeypatch.setattr(api, 'ensure_usage_snapshot_background_worker', lambda: None)
    monkeypatch.setattr(api, 'record_usage_snapshot_if_due', lambda: {'usage': usage})
    monkeypatch.setattr(api, 'get_usage_summary', lambda **kw: usage)
    calls = []
    def get_history(**kwargs):
        calls.append(kwargs)
        return history
    monkeypatch.setattr(api, 'get_usage_history_summary', get_history)
    monkeypatch.setattr(api, 'get_codex_accounts_summary', lambda: {})
    monkeypatch.setattr(api, 'get_session_storage_summary', lambda: {})
    monkeypatch.setattr(api, 'get_active_account_id', lambda: 'account')
    monkeypatch.setattr(api, 'refresh_account_usage_snapshot_if_due', lambda **kw: {'refreshed': True})
    app = Flask(__name__)
    app.register_blueprint(api.bp)
    yield app.test_client(), usage, history, calls
    assert (usage, history) == originals  # Shared snapshot/cache must remain intact.


@pytest.mark.parametrize('force', [False, True])
def test_compact_usage_retains_totals_and_prediction_but_defers_chart(usage_client, force):
    client, usage, history, calls = usage_client
    if force:
        response = client.post('/api/codex/usage/refresh?compact=1',
                               json={'hours': 24, 'scope': 'workspace'})
    else:
        response = client.get('/api/codex/usage?compact=1&hours=24&scope=workspace')
    assert response.status_code == 200
    payload = response.json
    assert 'trend' not in payload['usage']['usage_reconciliation']
    assert 'recent' not in payload['usage']['usage_events']
    assert payload['usage']['token_usage'] == usage['token_usage']
    assert payload['usage']['usage_keepalive'] == usage['usage_keepalive']
    assert payload['usage_history']['relation'] == history['relation']
    assert payload['usage_history']['calibration']['models'] == history['calibration']['models']
    assert payload['usage_history']['is_summary'] is True
    assert 'items' not in payload['usage_history']
    assert 'chart_items' not in payload['usage_history']
    assert 'recent' not in payload['usage_history']['calibration']
    assert str(calls[-1]['hours']) == '24'
    assert calls[-1]['scope'] == 'workspace'


def test_legacy_and_history_requests_keep_details(usage_client):
    client, usage, history, _ = usage_client
    payload = client.get('/api/codex/usage').json
    assert payload['usage'] == usage
    assert payload['usage_history'] == history
    assert client.get('/api/codex/usage/history?hours=24').json['usage_history'] == history


def test_settings_uses_same_compact_projection(usage_client, monkeypatch):
    client, usage, _, _ = usage_client
    monkeypatch.setattr(api, 'get_settings', lambda: {})
    monkeypatch.setattr(api, 'get_codex_app_server_status', lambda: {})
    payload = client.get('/api/codex/settings?compact=1').json
    assert payload['usage']['five_hour'] == usage['five_hour']
    assert 'trend' not in payload['usage']['usage_reconciliation']
    assert 'usage_history' not in payload


def test_failed_live_refresh_also_returns_compact_fallback(usage_client, monkeypatch):
    client, _, _, _ = usage_client
    monkeypatch.setattr(api, 'refresh_account_usage_snapshot_if_due',
                        lambda **kw: {'refreshed': False, 'error': 'offline'})
    response = client.post('/api/codex/usage/refresh?compact=1', json={})
    assert response.status_code == 502
    assert response.json['error'] == 'offline'
    assert response.json['usage_history']['is_summary']
    assert 'trend' not in response.json['usage']['usage_reconciliation']
