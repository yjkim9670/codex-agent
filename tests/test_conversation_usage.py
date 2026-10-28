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
