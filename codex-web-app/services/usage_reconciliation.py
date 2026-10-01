"""Compare account API observations with the Workbench ledger without rewriting it."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')


def build_usage_reconciliation(snapshot, ledger, *, days=30, now=None):
    current = (now or datetime.now(KST)).astimezone(KST)
    today = current.date()
    days = max(1, min(90, int(days)))
    start = today - timedelta(days=days - 1)
    api = snapshot.get('account_usage') or {}
    api_days = {}
    for bucket in api.get('daily_usage') or []:
        try:
            day = datetime.strptime(bucket['date'], '%Y-%m-%d').date()
            tokens = int(bucket['tokens'])
        except (KeyError, TypeError, ValueError):
            continue
        if tokens >= 0:
            api_days[day.isoformat()] = tokens
    local_days = ledger.get('by_day') or {}
    rows = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        api_tokens = api_days.get(day)
        local_tokens = int((local_days.get(day) or {}).get('total_tokens') or 0)
        rows.append({
            'date': day,
            'account_tokens': api_tokens,
            'local_tokens': local_tokens,
            'local_record_present': day in local_days,
            'difference_tokens': None if api_tokens is None else api_tokens - local_tokens,
            'status': 'account_data_missing' if api_tokens is None else (
                'equal' if api_tokens == local_tokens else 'different'
            ),
            'is_partial_day': day == today.isoformat(),
        })
    comparable = [row for row in rows if row['account_tokens'] is not None]
    account_total = api.get('total_tokens')
    local_total = int((ledger.get('all_time') or {}).get('total_tokens') or 0)
    return {
        'observed_at': snapshot.get('last_success_at'),
        'evaluated_at': current.isoformat(),
        'local_updated_at': ledger.get('updated_at'),
        'refresh_error': snapshot.get('error') or '',
        'window_start': start.isoformat(),
        'window_end': today.isoformat(),
        'days': days,
        'timezone': 'Asia/Seoul',
        'date_alignment': 'API date labels compared with KST ledger dates; API timezone unverified',
        'scope_note': 'Account API covers the account; local ledger covers recorded Workbench activity. Differences do not prove missing records.',
        'account_lifetime_tokens': account_total,
        'local_lifetime_tokens': local_total,
        'lifetime_difference_tokens': None if account_total is None else int(account_total) - local_total,
        'local_window_tokens': sum(row['local_tokens'] for row in rows),
        'account_reported_window_tokens': sum(row['account_tokens'] for row in comparable),
        'comparable_local_tokens': sum(row['local_tokens'] for row in comparable),
        'comparable_difference_tokens': sum(row['difference_tokens'] for row in comparable),
        'comparable_days': len(comparable),
        'account_missing_days': days - len(comparable),
        'daily': rows,
    }
