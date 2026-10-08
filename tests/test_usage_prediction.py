from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from codex_agent.services import codex_chat
from codex_agent.services.usage_prediction import (
    fit_quota_relation, observation_groups, predict_percent, token_components,
)


def records(count=16):
    result = []
    for i in range(count):
        at = (datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(minutes=i * 10)).isoformat()
        uncached = 1000 + (i % 4) * 1000
        cached = 10000 + (i % 5) * 20000
        output = 100 + (i % 3) * 100
        actual = (uncached + cached * .1 + output * 4) / 1000
        result.append({
            'id': f'stream:{i}', 'model': 'gpt-6.1-sol', 'reasoning_effort': 'medium',
            'status': 'completed', 'created_at': at, 'weighted_tokens': uncached + cached + output,
            'raw_tokens': uncached + cached + output,
            'token_usage': {'input_tokens': uncached + cached, 'cached_input_tokens': cached,
                            'output_tokens': output, 'total_tokens': uncached + cached + output},
            'predictions': {'five_hour': (uncached + cached + output) / 1000},
            'outcomes': {'five_hour': {'status': 'observed', 'actual_percent': actual,
                                       'group_actual_percent': actual, 'group_id': str(i),
                                       'group_size': 1, 'observed_at': at}},
        })
    return result


def test_empirical_mix_predicts_unseen_cache_heavy_request():
    relation = fit_quota_relation(records(), 'five_hour', 'gpt-6.1-sol', 'medium')
    assert relation['is_applied']
    assert relation['validation']['candidate_mae_percent'] < 1e-8
    assert predict_percent(relation, {'input_tokens': 203000, 'cached_input_tokens': 200000,
                                     'output_tokens': 500}) == pytest.approx(25)
    assert not fit_quota_relation(records(9), 'five_hour', 'gpt-6.1-sol', 'medium')['is_applied']


def test_no_application_when_baseline_is_already_accurate():
    data = records()
    for record in data:
        record['predictions']['five_hour'] = record['outcomes']['five_hour']['actual_percent']
    assert not fit_quota_relation(data, 'five_hour', 'gpt-6.1-sol', 'medium')['is_applied']


def test_validation_does_not_fit_held_out_outcomes():
    data = records(7)
    relation = fit_quota_relation(data, 'five_hour', 'gpt-6.1-sol', 'medium')
    data[-1]['outcomes']['five_hour']['actual_percent'] += 100
    data[-1]['outcomes']['five_hour']['group_actual_percent'] += 100
    changed = fit_quota_relation(data, 'five_hour', 'gpt-6.1-sol', 'medium')
    assert changed['validation']['candidate_mae_percent'] == pytest.approx(
        relation['validation']['candidate_mae_percent'] + 100)


@pytest.mark.parametrize('change', ['model', 'effort', 'excluded', 'missing', 'delayed'])
def test_complete_batch_required_for_condition_learning(change):
    data = records(2)
    for record in data:
        record['outcomes']['five_hour'].update(group_id='batch', group_size=2,
                                               group_actual_percent=10,
                                               observed_at=data[-1]['created_at'])
    if change == 'model':
        data[1]['model'] = 'gpt-5.6-terra'
    elif change == 'effort':
        data[1]['reasoning_effort'] = 'low'
    elif change == 'excluded':
        data[1]['learning_eligible'] = False
    elif change == 'missing':
        data.pop()
    else:
        for record in data:
            record['outcomes']['five_hour']['observed_at'] = '2026-10-02T00:00:00+00:00'
    assert observation_groups(data, 'five_hour', 'gpt-6.1-sol', 'medium') == []
    if change != 'delayed' and change != 'missing':
        relation = codex_chat._calibration_relation_from_records(data, 'five_hour', 'gpt-6.1-sol', 'medium')
        assert relation['record_count'] == 0


def test_rounding_batch_uses_observed_total():
    data = records(2)
    for record in data:
        record['outcomes']['five_hour'].update(group_id='batch', group_size=2,
                                               group_actual_percent=3,
                                               actual_percent=.123,
                                               observed_at=data[-1]['created_at'])
    groups = observation_groups(data, 'five_hour', 'gpt-6.1-sol', 'medium')
    assert len(groups) == 1
    assert groups[0]['actual'] == 3


def test_old_token_components_restored_without_mutating_history(tmp_path):
    data = records(1)
    event = {**data[0]['token_usage'], 'event_id': 'workspace:stream:0',
             'model': 'gpt-6.1-sol', 'reasoning_effort': 'medium'}
    del data[0]['token_usage']
    original = deepcopy(data)
    path = tmp_path / 'events.jsonl'
    path.write_text(json.dumps(event) + '\n')
    enriched = codex_chat._calibration_records_with_token_usage(data, path)
    assert token_components(enriched[0]['token_usage'])
    assert data == original
    # An ambiguous duplicate must never be attributed to a calibration record.
    path.write_text((json.dumps(event) + '\n') * 2)
    assert 'token_usage' not in codex_chat._calibration_records_with_token_usage(data, path)[0]


def test_prediction_resolver_prefers_validated_effort_mix_and_falls_back(monkeypatch):
    relation = fit_quota_relation(records(), 'five_hour', 'gpt-6.1-sol', 'medium')
    summary = {'calibration': {
        'token_mix': {'gpt-6.1-sol': {'efforts': {'medium': {'five_hour': relation}}}},
        'models': {'gpt-6.1-sol': {'weekly': {'is_applied': True, 'tokens_per_percent': 10000}}},
    }, 'relation': {'five_hour': {'raw_tokens_per_percent': 5000}}}
    monkeypatch.setattr(codex_chat, 'get_usage_history_summary', lambda **_: summary)
    usage = records(1)[0]['token_usage']
    scales, sources = codex_chat._resolve_usage_prediction_scales(
        model='gpt-6.1-sol', reasoning_effort='medium', usage=usage)
    assert sources == {'five_hour': 'effort_token_mix', 'weekly': 'model_calibration'}
    assert codex_chat._calculate_sol_weighted_tokens('gpt-6.1-sol', usage) / scales['five_hour'] == pytest.approx(2.4)
    _, sources = codex_chat._resolve_usage_prediction_scales(
        model='gpt-6.1-sol', reasoning_effort='low', usage=usage)
    assert sources['five_hour'] == 'weighted_history_provisional'


@pytest.mark.parametrize('usage', [None, {}, {'input_tokens': 10, 'cached_input_tokens': 20, 'output_tokens': 1},
    {'input_tokens': 10, 'cached_input_tokens': 0, 'output_tokens': 1, 'total_tokens': 100},
    {'input_tokens': float('nan'), 'cached_input_tokens': 0, 'output_tokens': 1}])
def test_incomplete_or_invalid_token_components_do_not_train(usage):
    assert token_components(usage) is None


def test_successful_rollout_keeps_comparing_to_legacy_estimator():
    data = records()
    for record in data:
        record['predictions']['five_hour'] = record['outcomes']['five_hour']['actual_percent']
        record['prediction_sources'] = {'five_hour': 'effort_token_mix'}
    relation = fit_quota_relation(data, 'five_hour', 'gpt-6.1-sol', 'medium')
    assert relation['is_applied']
    assert relation['validation']['baseline_mae_percent'] > 0


def test_persisted_record_and_summary_support_new_prediction_end_to_end(tmp_path, monkeypatch):
    path = tmp_path / 'calibration.json'
    path.write_text(json.dumps({'records': records()}))
    context = {'account': {'id': 'test'}, 'usage_calibration_path': path,
               'usage_events_path': tmp_path / 'events.jsonl'}
    monkeypatch.setattr(codex_chat, '_account_storage_context', lambda *_: context)
    monkeypatch.setattr(codex_chat, '_account_has_active_codex_stream', lambda *_: False)
    summary = codex_chat._build_usage_calibration_summary('test')
    monkeypatch.setattr(codex_chat, 'get_usage_history_summary', lambda **_: {'calibration': summary})
    usage = {'input_tokens': 203000, 'cached_input_tokens': 200000,
             'output_tokens': 500, 'total_tokens': 203500}
    scales, sources = codex_chat._resolve_usage_prediction_scales('test', 'gpt-6.1-sol', 'medium', usage)
    record = codex_chat._create_usage_calibration_record(
        'test', 'stream:held-out', 'gpt-6.1-sol', 'medium', 'standard', usage,
        {'five_hour': {'used_percent': 10}}, prediction_scales=scales, prediction_sources=sources)
    assert record['predictions']['five_hour'] == pytest.approx(25)
    assert record['token_usage']['cached_input_tokens'] == 200000
    assert record['prediction_sources']['five_hour'] == 'effort_token_mix'
    assert json.loads(path.read_text())['records'][-1]['predictions']['five_hour'] == pytest.approx(25)
