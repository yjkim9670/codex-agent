import importlib.util
import json
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    'model_usage_analysis', Path(__file__).parents[1] / 'scripts/analyze_model_usage.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(root, mixed=False, overlap=False, reset=False):
    events, records = [], []
    for i in range(2):
        model = 'other' if mixed and i else 'model'
        events.append({'event_id': f'workspace:stream:{i}', 'model': model,
                       'recorded_at': f'2026-10-01T10:0{i + 1}:00+09:00',
                       'duration_ms': 10000, 'total_tokens': 1000000,
                       'input_tokens': 900000, 'output_tokens': 100000})
        records.append({'id': f'stream:{i}', 'model': model, 'raw_tokens': 1000000,
                        'created_at': f'2026-10-01T10:0{i + 1}:00+09:00',
                        'learning_eligible': True,
                        'limits_before': {w: {'resets_at': 'reset'} for w in ('five_hour', 'weekly')},
                        'outcomes': {w: {'status': 'observed', 'group_id': w,
                                        'group_size': 2, 'group_actual_percent': 2,
                                        'actual_percent': 999,  # Allocated values must be ignored.
                                        'observed_at': '2026-10-01T10:03:00+09:00'}
                                     for w in ('five_hour', 'weekly')}})
    if overlap:
        events.append({**events[0], 'event_id': 'workspace:external',
                       'model': 'other', 'duration_ms': 60000})
    data = {
        'codex_usage_calibration.json': {'records': records},
        'codex_usage_history.json': {'account_limit_samples': [{
            'limits_observed_at': '2026-10-01T10:03:00+09:00',
            'five_hour_resets_at': 'changed' if reset else 'reset',
            'weekly_resets_at': 'reset'}]},
        'codex_account_usage_snapshot.json': {'last_success_at': '2026-10-01T11:00:00+09:00',
                                            'five_hour': {}, 'weekly': {}},
    }
    for name, value in data.items():
        (root / name).write_text(json.dumps(value))
    (root / 'codex_usage_events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
    return module.analyze(root)


def test_group_deduction_counted_once(tmp_path):
    report = fixture(tmp_path)
    for window in report['windows'].values():
        row = window['models']['model']
        assert row['deduction_pp'] == 2
        assert row['pp_per_million_tokens'] == 1
        assert row['groups'] == 1


def test_mixed_models_not_attributed(tmp_path):
    report = fixture(tmp_path, mixed=True)
    assert all(not w['models'] for w in report['windows'].values())


def test_cross_workspace_overlap_not_attributed(tmp_path):
    report = fixture(tmp_path, overlap=True)
    assert all(w['excluded']['overlapping_local_execution'] == 1
               for w in report['windows'].values())


def test_reset_invalidates_only_affected_window(tmp_path):
    report = fixture(tmp_path, reset=True)
    assert not report['windows']['five_hour']['models']
    assert report['windows']['weekly']['models']['model']['deduction_pp'] == 2
