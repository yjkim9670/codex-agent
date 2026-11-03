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


def consecutive_chat():
    first, before, after = fixture()
    first.update(account_id='personal', provider_account_id='provider')
    first['quota_observations'] = {'before': before}
    second = deepcopy(first)
    second.update(event_id='chat:second', execution_started_at='2026-10-14T10:02:00+09:00',
                  execution_completed_at='2026-10-14T10:03:00+09:00',
                  recorded_at='2026-10-14T10:03:00+09:00', total_tokens=200,
                  input_tokens=180, output_tokens=20)
    second['quota_observations'] = {
        'before': {**deepcopy(before), 'observed_at': second['execution_started_at']},
        'after': {**deepcopy(after), 'observed_at': '2026-10-14T10:04:00+09:00'}}
    return first, second


def test_consecutive_chat_groups_delayed_delta_once_and_is_order_independent():
    first, second = consecutive_chat()
    records, _ = chat_calibration([second, first], [second, first], [])
    assert records == chat_calibration([first, second], [first, second], [])[0]
    for window in ('five_hour', 'weekly'):
        outcomes = [r['outcomes'][window] for r in records]
        assert {o['group_size'] for o in outcomes} == {2}
        assert len({o['group_id'] for o in outcomes}) == 1
        assert {o['group_actual_percent'] for o in outcomes} == {1}
        assert sum(o['actual_percent'] for o in outcomes) == 1
    report = analyze(Path('.'), data={'events': [first, second],
                     'codex_usage_calibration.json': {'records': records}},
                     now=datetime.fromisoformat('2026-10-14T11:00:00+09:00'))
    result = report['windows']['five_hour']['models']['gpt-6-luna']
    assert result['tokens'] == 300
    assert result['deduction_pp'] == 1
    assert result['groups'] == 1


def test_consecutive_chat_rejects_mixed_or_unverified_members():
    for change in ('model', 'reasoning_effort', 'account_id', 'provider_account_id',
                   'application', 'usage_pending', 'reset', 'missing_baseline', 'concurrent'):
        first, second = consecutive_chat()
        if change in ('model', 'reasoning_effort', 'account_id', 'provider_account_id', 'application'):
            second[change] = 'different'
        elif change == 'usage_pending':
            second[change] = True
        elif change == 'reset':
            second['quota_observations']['before']['five_hour']['resets_at'] = '2026-10-16T00:00:00+09:00'
        elif change == 'missing_baseline':
            second['quota_observations'].pop('before')
        else:
            second['execution_started_at'] = '2026-10-14T10:00:30+09:00'
            second['quota_observations']['before']['observed_at'] = second['execution_started_at']
        entries = [first, second] if change != 'application' else [first]
        records, _ = chat_calibration(entries, [first, second], [])
        assert records[0]['outcomes']['five_hour']['status'] != 'observed', change


def test_chat_windows_form_independent_groups_and_do_not_reuse_members():
    first, second = consecutive_chat()
    after_first = deepcopy(first['quota_observations']['before'])
    after_first['observed_at'] = '2026-10-14T10:01:30+09:00'
    after_first['five_hour']['used_percent'] = 21
    first['quota_observations']['after'] = after_first
    second['quota_observations']['before']['five_hour']['used_percent'] = 21
    second['quota_observations']['after']['five_hour']['used_percent'] = 22
    records, _ = chat_calibration([first, second], [first, second], [])
    assert [r['outcomes']['five_hour']['group_size'] for r in records] == [1, 1]
    assert len({r['outcomes']['five_hour']['group_id'] for r in records}) == 2
    assert [r['outcomes']['weekly']['group_size'] for r in records] == [2, 2]


def test_chat_group_waits_for_complete_execution_and_times_out_without_delta():
    first, second = consecutive_chat()
    second['quota_observations']['after']['observed_at'] = '2026-10-14T10:02:30+09:00'
    records, _ = chat_calibration([first, second], [first, second], [])
    assert records[0]['outcomes']['five_hour']['status'] == 'excluded'
    second['quota_observations'].pop('after')
    records, _ = chat_calibration([first, second], [first, second], [],
                                 now=datetime.fromisoformat('2026-10-16T11:00:00+09:00'))
    assert all(r['outcomes']['five_hour']['reason'] == 'observation_timeout' for r in records)


def test_chat_does_not_reuse_stale_baseline_after_a_measured_group():
    first, second = consecutive_chat()
    first['quota_observations']['after'] = {
        **deepcopy(second['quota_observations']['after']),
        'observed_at': '2026-10-14T10:01:30+09:00'}
    second['execution_started_at'] = '2026-10-14T10:02:00+09:00'
    second['quota_observations']['before']['observed_at'] = '2026-10-14T10:01:00+09:00'
    records, _ = chat_calibration([first, second], [first, second], [])
    assert records[0]['outcomes']['five_hour']['status'] == 'observed'
    assert records[1]['outcomes']['five_hour']['reason'] == 'unverified_baseline'


def test_grouped_chat_ledger_reimport_is_idempotent_after_rollout_corrections(tmp_path):
    first, second = consecutive_chat()
    for i, entry in enumerate((first, second)):
        entry.update(thread_id='thread', turn_id=f'turn-{i}')
    rollout = [{**e, 'event_id': f'rollout:{i}', 'source': 'rollout',
                'total_tokens': 400, 'input_tokens': 360, 'output_tokens': 40}
               for i, e in enumerate((first, second))]
    events, _ = merge_events([first, second], [{'db_tokens': 800, 'events': rollout}])
    sync_chat_calibration({'root': tmp_path}, [first, second], events)
    path = tmp_path / 'codex_usage_calibration.json'
    saved = path.read_bytes()
    sync_chat_calibration({'root': tmp_path}, [first, second], events)
    assert path.read_bytes() == saved
    report = analyze(Path('.'), data={'events': events, 'codex_usage_calibration.json': json.loads(saved)},
                     now=datetime.fromisoformat('2026-10-14T11:00:00+09:00'))
    result = report['windows']['five_hour']['models']['gpt-6-luna']
    assert (result['groups'], result['tokens'], result['deduction_pp']) == (1, 800, 1)
