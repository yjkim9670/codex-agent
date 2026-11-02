from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services.usage_recovery import chat_calibration, recover_timeouts, sample
from codex_agent.services.model_usage_analysis import analyze
from codex_agent.services.usage_dashboard import merge_events, sync_chat_calibration
from codex_agent.services import codex_chat as chat


def fixture():
    before = {'observed_at': '2026-10-14T10:00:00+09:00', **{
        w: {'used_percent': 20, 'resets_at': '2026-10-15T00:00:00+09:00'} for w in ('five_hour', 'weekly')}}
    after = deepcopy(before)
    after['observed_at'] = '2026-10-14T10:02:00+09:00'
    for w in ('five_hour', 'weekly'):
        after[w]['used_percent'] = 21
    entry = {'event_id': 'chat:attempt', 'thread_id': 'thread', 'turn_id': 'turn',
             'application': 'workbench-chat', 'status': 'completed', 'usage_pending': False,
             'model': 'gpt-6-luna', 'reasoning_effort': 'xhigh',
             'recorded_at': '2026-10-14T10:01:00+09:00',
             'execution_started_at': before['observed_at'],
             'execution_completed_at': '2026-10-14T10:01:00+09:00',
             'duration_ms': 60000, 'input_tokens': 90, 'output_tokens': 10, 'total_tokens': 100,
             'quota_observations': {'before': before, 'after': after}}
    return entry, before, after


def test_chat_import_is_accepted_after_rollout_replaces_outbox_id():
    entry, _, _ = fixture()
    rollout = {**entry, 'event_id': 'rollout:thread:turn:luna:xhigh', 'source': 'rollout',
               'input_tokens': 180, 'output_tokens': 20, 'total_tokens': 200}
    events, _ = merge_events([entry], [{'db_tokens': 200, 'events': [rollout]}])
    records, _ = chat_calibration([entry], events, [])
    report = analyze(Path('.'), data={'events': events, 'codex_usage_calibration.json': {'records': records}},
                     now=datetime.fromisoformat('2026-10-14T11:00:00+09:00'))
    assert report['windows']['five_hour']['models']['gpt-6-luna']['tokens'] == 200
    assert report['windows']['five_hour']['models']['gpt-6-luna']['deduction_pp'] == 1
    assert report['calibration_coverage']['models']['gpt-6-luna']['linked_tokens'] == 200


def test_delayed_observation_and_overlap_are_not_misattributed():
    entry, before, after = fixture()
    entry['quota_observations']['after'] = {**before, 'observed_at': after['observed_at']}
    entry['quota_observations']['delayed'] = {**after, 'observed_at': '2026-10-14T10:03:00+09:00'}
    other = {**entry, 'event_id': 'other:run', 'execution_started_at': '2026-10-14T10:02:30+09:00',
             'recorded_at': '2026-10-14T10:10:00+09:00'}
    records, _ = chat_calibration([entry], [entry], [])
    assert records[0]['outcomes']['five_hour']['observed_at'] == '2026-10-14T10:03:00+09:00'
    records, _ = chat_calibration([entry], [entry, other], [])
    assert records[0]['outcomes']['five_hour']['reason'] == 'overlapping_local_execution'


def test_recovery_keeps_original_and_rejects_missing_baseline_and_changed_reset():
    entry, before, after = fixture()
    records, samples = chat_calibration([entry], [entry], [])
    for outcome in records[0]['outcomes'].values():
        outcome.clear()
        outcome.update(status='excluded', reason='observation_timeout')
    original = deepcopy(records)
    recovered, audit = recover_timeouts(records, [entry], samples)
    assert all(row['status'] == 'observed' for row in audit)
    assert records == original
    recovered, audit = recover_timeouts(records, [entry], [sample(after)])
    assert {row['reason'] for row in audit} == {'unverified_baseline'}
    changed = sample(after)
    changed['five_hour_resets_at'] = '2026-10-16T00:00:00+09:00'
    recovered, audit = recover_timeouts(records, [entry], [sample(before), changed])
    assert audit[0]['reason'] == 'unverified_or_changed_reset'
    assert audit[1]['status'] == 'observed'


def test_common_ledger_import_is_idempotent_and_history_is_untouched(tmp_path):
    entry, _, _ = fixture()
    path = tmp_path / 'codex_usage_calibration.json'
    history = tmp_path / 'codex_usage_history.json'
    history.write_text('{"account_limit_samples": []}')
    original = history.read_bytes()
    sync_chat_calibration({'root': tmp_path}, [entry], [entry])
    first = path.read_bytes()
    sync_chat_calibration({'root': tmp_path}, [entry], [entry])
    assert first == path.read_bytes()
    assert history.read_bytes() == original
    ledger = chat._load_usage_calibration_ledger(path)
    assert len(ledger['records']) == 1
    assert ledger['records'][0]['weighted_tokens'] > 0


def test_legacy_unlinked_usage_and_filter_diagnostics():
    entry, _, _ = fixture()
    entry.pop('quota_observations')
    records, _ = chat_calibration([entry], [entry], [])
    assert records == []
    report = analyze(Path('.'), data={'events': [entry]}, now=datetime.fromisoformat('2026-10-14T11:00:00+09:00'))
    assert report['calibration_coverage']['models']['gpt-6-luna']['unlinked_tokens'] == 100


def test_active_chat_without_tokens_blocks_quota_attribution():
    entry, _, _ = fixture()
    active = {**entry, 'event_id': 'chat:active', 'status': 'streaming', 'total_tokens': 0,
              'execution_started_at': '2026-10-14T09:00:00+09:00', 'recorded_at': '2026-10-14T09:00:01+09:00'}
    records, _ = chat_calibration([entry], [entry, active], [])
    assert records[0]['outcomes']['five_hour']['reason'] == 'overlapping_local_execution'


def test_chat_pending_is_not_batched_with_job_mode(tmp_path, monkeypatch):
    entry, before, _ = fixture()
    entry['quota_observations'] = {'before': before}
    records, _ = chat_calibration([entry], [entry], [])
    assert records[0]['outcomes']['five_hour']['status'] == 'pending'
    path = tmp_path / 'calibration.json'
    path.write_text(json.dumps({'records': records}))
    original = path.read_bytes()
    monkeypatch.setattr(chat, '_account_storage_context', lambda _: {'usage_calibration_path': path})
    assert not chat._reconcile_usage_calibration('test', {
        'limits_observed_at': '2026-10-14T10:02:00+09:00',
        'five_hour': {'used_percent': 25}, 'weekly': {'used_percent': 25}})
    assert path.read_bytes() == original
