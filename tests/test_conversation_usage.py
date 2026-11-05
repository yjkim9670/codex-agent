from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'conversation-app'))
from services.conversations import Store
from codex_agent.services.usage_dashboard import merge_events
from codex_agent.services.conversation_usage import read_chat_outbox
from codex_agent.services.model_usage_analysis import analyze


def test_outbox_account_boundary_and_deletion_retention(tmp_path, monkeypatch):
    monkeypatch.setenv('CHAT_DATA_DIR', str(tmp_path))
    store = Store(tmp_path)
    cid = store.create()['id']
    attempt, _ = store.enqueue(cid, 'hello', 'request-usage', {'account_id': 'a', 'provider_account_id': 'p', 'model': 'm', 'search': 'off'})
    store.emit(attempt['id'], 'provider', {'thread_id': 't', 'turn_id': 'u'})
    store.emit(attempt['id'], 'usage', {'total': {'inputTokens': 50, 'outputTokens': 10, 'totalTokens': 60}})
    store.emit(attempt['id'], 'done', {'status': 'completed'})
    assert read_chat_outbox('other') == []
    assert len(read_chat_outbox('p')) == 1
    store.change(cid, delete=True)
    assert read_chat_outbox('p')[0]['total_tokens'] == 60
    assert 'hello' not in json.dumps(read_chat_outbox('p'))


def test_rollout_corrects_provisional_values_and_app_filter():
    at = datetime.now(timezone.utc)
    provisional = {'event_id': 'chat:a', 'application': 'workbench-chat', 'thread_id': 't', 'turn_id': 'u', 'total_tokens': 150, 'input_tokens': 140, 'output_tokens': 10, 'recorded_at': at.isoformat(), 'model': 'm'}
    final = {**provisional, 'event_id': 'rollout:t:u:m', 'source': 'rollout', 'total_tokens': 100, 'input_tokens': 80, 'output_tokens': 20}
    work = {**final, 'event_id': 'work', 'application': 'workbench', 'thread_id': 'w', 'total_tokens': 70, 'input_tokens': 60, 'output_tokens': 10}
    merged, _ = merge_events([provisional, work], [{'id': 't', 'events': [final], 'db_tokens': 100}])
    assert sum(r['total_tokens'] for r in merged) == 170
    assert {r['event_id'] for r in merged} == {'rollout:t:u:m', 'work'}
    assert analyze(Path('.'), data={'events': merged}, now=at, application='workbench-chat')['total_tokens'] == 100
    assert analyze(Path('.'), data={'events': merged}, now=at)['total_tokens'] == 170


def test_quota_observations_survive_completion_deletion_and_do_not_move_usage_time(tmp_path, monkeypatch):
    monkeypatch.setenv('CHAT_DATA_DIR', str(tmp_path))
    store = Store(tmp_path)
    cid = store.create()['id']
    attempt, _ = store.enqueue(cid, 'hello', 'quota-request', {'account_id': 'a', 'provider_account_id': 'p', 'search': 'off'})
    aid = attempt['id']
    before = {'observed_at': datetime.now(timezone.utc).isoformat(), 'five_hour': {'used_percent': 20}}
    store.emit(aid, 'limits', {'before': before})
    store.emit(aid, 'provider', {'thread_id': 'thread', 'turn_id': 'turn', 'model': 'gpt-6-luna'})
    store.emit(aid, 'usage', {'total': {'inputTokens': 90, 'outputTokens': 10, 'totalTokens': 100}})
    store.emit(aid, 'done', {'status': 'completed'})
    original = read_chat_outbox('p')[0]
    store.emit(aid, 'limits', {'after': {'observed_at': 'later'}, 'delayed': {'observed_at': 'latest'}})
    updated = read_chat_outbox('p')[0]
    observations = updated['quota_observations']
    assert store.attempt(aid)['quota_observations'] == observations
    assert store.messages(cid)[0]['attempts'][0]['quota_observations'] == observations
    assert updated['recorded_at'] == original['recorded_at']
    assert updated['execution_completed_at'] == original['execution_completed_at']
    assert updated['execution_started_at'] == before['observed_at']
    assert updated['duration_ms'] >= 0
    assert set(updated['quota_observations']) == {'before', 'after', 'delayed'}
    assert store.attempt(aid)['status'] == 'completed'
    store.change(cid, delete=True)
    assert read_chat_outbox('p')[0] == updated
    store.emit(aid, 'limits', {'delayed': {'observed_at': 'after deletion'}})
    assert read_chat_outbox('p')[0]['quota_observations']['delayed']['observed_at'] == 'after deletion'


def test_registered_sources_are_shared_across_checkouts_and_account_scoped(tmp_path, monkeypatch):
    import sqlite3
    from shared.chat_usage_sources import register_chat_root
    from codex_agent.services import conversation_usage as usage
    monkeypatch.setenv('CODEX_WORKBENCH_SHARED_ACCOUNT_STATE_DIR', str(tmp_path / 'shared'))
    root = tmp_path / 'canonical-chat'
    root.mkdir()
    with sqlite3.connect(root / 'conversations.sqlite3') as db:
        db.execute('create table usage_outbox (event text)')
        for account in ('ours', 'other'):
            db.execute('insert into usage_outbox values (?)', (json.dumps({
                'event_id': 'chat:' + account, 'provider_account_id': account}),))
    register_chat_root(root)
    register_chat_root(root)
    signatures = []
    for checkout in ('checkout-a', 'checkout-b'):
        monkeypatch.delenv('CHAT_DATA_DIR', raising=False)
        monkeypatch.setattr(usage, 'chat_root', lambda: tmp_path / checkout)
        assert usage.read_chat_outbox('ours') == [{'event_id': 'chat:ours', 'provider_account_id': 'ours'}]
        signatures.append(usage.chat_source_signature())
    assert signatures[0] == signatures[1]
    assert len(list((tmp_path / 'shared/chat_usage_sources').glob('*.json'))) == 1
    assert all(any(s['root'] == str(root) for s in signature) for signature in signatures)
    (root / 'conversations.sqlite3').unlink()
    import pytest
    with pytest.raises(FileNotFoundError):
        usage.read_chat_outbox('ours')


def test_source_signature_changes_when_wal_receives_delayed_observations(tmp_path, monkeypatch):
    import sqlite3
    from codex_agent.services import conversation_usage as usage
    monkeypatch.setenv('CHAT_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('CODEX_WORKBENCH_SHARED_ACCOUNT_STATE_DIR', str(tmp_path / 'shared'))
    with sqlite3.connect(tmp_path / 'conversations.sqlite3') as db:
        db.execute('pragma journal_mode=WAL')
        db.execute('create table usage_outbox (event text)')
        db.commit()
        before = usage.chat_source_signature()
        db.execute('insert into usage_outbox values (?)', ('{}',))
        db.commit()
        assert usage.chat_source_signature() != before
