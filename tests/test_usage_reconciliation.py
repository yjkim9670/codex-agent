from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services.usage_reconciliation import KST, build_usage_reconciliation


def test_missing_api_dates_are_unknown_and_signed_differences_are_preserved():
    report = build_usage_reconciliation({
        'last_success_at': '2026-10-01T12:00:00+09:00',
        'account_usage': {'total_tokens': 1000, 'daily_usage': [
            {'date': '2026-09-30', 'tokens': 40},
            {'date': '2026-10-01', 'tokens': 100},
        ]},
    }, {'all_time': {'total_tokens': 900}, 'by_day': {
        '2026-09-29': {'total_tokens': 30},
        '2026-09-30': {'total_tokens': 50},
    }}, days=3, now=datetime(2026, 10, 1, 12, tzinfo=KST))
    assert report['comparable_difference_tokens'] == 90
    assert report['local_window_tokens'] == 80
    assert report['account_missing_days'] == 1
    assert report['daily'][0]['difference_tokens'] is None
    assert report['daily'][1]['difference_tokens'] == -10
    assert report['daily'][2]['is_partial_day']
    assert not report['daily'][2]['local_record_present']


def test_missing_lifetime_is_not_zero_and_invalid_api_buckets_are_ignored():
    report = build_usage_reconciliation({'account_usage': {'daily_usage': [
        {'date': 'invalid', 'tokens': 100}, {'date': '2026-10-01', 'tokens': -1},
    ]}}, {}, days=1, now=datetime(2026, 10, 1, tzinfo=KST))
    assert report['lifetime_difference_tokens'] is None
    assert report['account_missing_days'] == 1
