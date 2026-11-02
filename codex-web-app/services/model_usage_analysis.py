#!/usr/bin/env python3
"""Compare local model tokens and observed quota deductions without API calls."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from .usage_recovery import event_key, same_reset


def analyze(root, days=30, effort="all", environment="all", *, data=None, now=None, application="all"):
    def read(name):
        if data is not None:
            return data.get(name, {})
        path = root / name
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    events = data.get('events', []) if data is not None else [json.loads(line) for line in
              (root / 'codex_usage_events.jsonl').read_text(encoding='utf-8').splitlines()
              if line.strip()] if (root / 'codex_usage_events.jsonl').exists() else []
    calibration = read('codex_usage_calibration.json')
    history = read('codex_usage_history.json')
    snapshot = read('codex_account_usage_snapshot.json')
    end = now or datetime.now(ZoneInfo('Asia/Seoul'))
    start = end.astimezone(ZoneInfo('Asia/Seoul')).replace(
        hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    def matches(e):
        return (effort == 'all' or (e.get('reasoning_effort') or 'unknown') == effort) and (
            environment == 'all' or e.get('workspace_path') == environment) and (
            application == 'all' or e.get('application', 'unknown') == application)

    selected = [e for e in events if start <= datetime.fromisoformat(e['recorded_at']) <= end and matches(e)]
    if len({e['event_id'] for e in selected}) != len(selected):
        raise ValueError('Duplicate event IDs: deduplicate before analysis')
    models = defaultdict(Counter)
    model_efforts = defaultdict(Counter)
    for event in selected:
        row = models[event.get('model') or 'unknown']
        row['events'] += 1
        for key in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens'):
            row[key] += event.get(key, 0)
        if event.get('total_tokens', 0) != event.get('input_tokens', 0) + event.get('output_tokens', 0):
            row['token_component_mismatches'] += 1

    for event in selected:
        model = event.get('model') or 'unknown'
        effort_name = event.get('reasoning_effort') or 'unknown'
        row = model_efforts[f'{model}/{effort_name}']
        row['model'] = model
        row['reasoning_effort'] = effort_name
        row['total_tokens'] += event.get('total_tokens', 0)

    # Calibration IDs omit the workspace prefix. Reject ambiguous matches.
    event_index = defaultdict(list)
    intervals = []
    for event in events:
        event_index[event_key(event)].append(event)
        if event.get('total_tokens', 0) > 0 and event.get('duration_ms') is not None:
            finish = datetime.fromisoformat(event['recorded_at'])
            intervals.append((finish - timedelta(milliseconds=event['duration_ms']), finish, event))
    samples = defaultdict(list)
    all_samples = [*history.get('account_limit_samples', []),
                   *(s for r in calibration.get('records', []) for s in r.get('quota_samples', []))]
    for sample in all_samples:
        if sample.get('limits_observed_at'):
            samples[datetime.fromisoformat(sample['limits_observed_at'])].append(sample)

    record_ids = {r['id'] for r in calibration.get('records', [])}
    coverage = defaultdict(Counter)
    coverage_efforts = defaultdict(Counter)
    for event in selected:
        key = event_key(event)
        field = 'linked_tokens' if key in record_ids and len(event_index[key]) == 1 else 'unlinked_tokens'
        coverage[event.get('model') or 'unknown'][field] += event.get('total_tokens', 0)
        coverage_efforts[f"{event.get('model') or 'unknown'}/{event.get('reasoning_effort') or 'unknown'}"][field] += event.get('total_tokens', 0)

    windows = {}
    for window in ('five_hour', 'weekly'):
        groups = defaultdict(list)
        exclusions = Counter()
        excluded_models = defaultdict(Counter)
        excluded_efforts = defaultdict(Counter)

        def exclude(reason, records):
            exclusions[reason] += 1
            # Count each rejected group once per model/effort it contains.
            for model in {r.get('model') or 'unknown' for r in records}:
                excluded_models[model][reason] += 1
            for model, level in {(r.get('model') or 'unknown', r.get('reasoning_effort') or 'unknown') for r in records}:
                excluded_efforts[f'{model}/{level}'][reason] += 1
        for record in calibration.get('records', []):
            if not start <= datetime.fromisoformat(record['created_at']) <= end:
                continue
            outcome = record.get('outcomes', {}).get(window, {})
            if outcome.get('status') != 'observed':
                linked = event_index[record['id']]
                if linked and not any(matches(e) for e in linked):
                    continue
                if not linked and (effort != 'all' and record.get('reasoning_effort') != effort or
                                   environment != 'all' or application != 'all'):
                    continue
                reason = 'record_' + outcome.get('status', 'missing')
                if outcome.get('reason'):
                    reason += ':' + outcome['reason']
                exclude(reason, [record])
                continue
            groups[outcome['group_id']].append(record)
        accepted = []
        for group_id, records in groups.items():
            outcome = records[0]['outcomes'][window]
            if len(records) != outcome['group_size']:
                exclude('incomplete_group', records)
                continue
            if len({r['model'] for r in records}) != 1:
                exclude('mixed_model_group', records)
                continue
            if any(not r.get('learning_eligible') for r in records):
                exclude('concurrent_flag', records)
                continue
            matched = [event_index[r['id']] for r in records]
            if any(len(matches) != 1 or matches[0].get('duration_ms') is None for matches in matched):
                exclude('missing_or_ambiguous_event', records)
                continue
            members = [matches[0] for matches in matched]
            if any(e.get('model') != r['model'] or e.get('total_tokens') != r['raw_tokens']
                   for e, r in zip(members, records)):
                exclude('event_mismatch', records)
                continue
            if len({e.get('reasoning_effort') or 'unknown' for e in members}) != 1:
                exclude('mixed_effort_group', records)
                continue
            if not all(matches(e) for e in members):
                exclude('filter_mismatch', records)
                continue
            observed = datetime.fromisoformat(outcome['observed_at'])
            earliest = min(datetime.fromisoformat(e['recorded_at']) -
                           timedelta(milliseconds=e['duration_ms']) for e in members)
            if earliest < start or observed > end:
                exclude('period_boundary', records)
                continue
            member_ids = {e['event_id'] for e in members}
            if any(finish > earliest and begin < observed and e['event_id'] not in member_ids
                   for begin, finish, e in intervals):
                exclude('overlapping_local_execution', records)
                continue
            if any(e.get('total_tokens', 0) > 0 and e.get('duration_ms') is None
                   and e['event_id'] not in member_ids
                   and earliest <= datetime.fromisoformat(e['recorded_at']) <= observed
                   for e in events):
                exclude('unverified_execution_timing', records)
                continue
            after = samples.get(observed, [])
            reset_key = window + '_resets_at'
            if not after or any(not r.get('limits_before', {}).get(window, {}).get('resets_at')
                                or any(not (s.get(reset_key) == r['limits_before'][window]['resets_at'] or
                                            same_reset(s.get(reset_key), r['limits_before'][window]['resets_at']))
                                       for s in after) for r in records):
                exclude('unverified_or_changed_reset', records)
                continue
            actual = outcome['group_actual_percent']
            if actual <= 0 or any(r['outcomes'][window]['group_actual_percent'] != actual for r in records):
                exclude('invalid_delta', records)
                continue
            accepted.append({'group_id': group_id, 'model': records[0]['model'],
                             'reasoning_effort': members[0].get('reasoning_effort') or 'unknown',
                             'observed_at': outcome['observed_at'], 'records': len(records),
                             'tokens': sum(r['raw_tokens'] for r in records),
                             'deduction_pp': actual})
        totals = defaultdict(Counter)
        for group in accepted:
            row = totals[group['model']]
            row['groups'] += 1
            for key in ('records', 'tokens', 'deduction_pp'):
                row[key] += group[key]
        for row in totals.values():
            row['pp_per_million_tokens'] = row['deduction_pp'] * 1_000_000 / row['tokens']
            row['tokens_per_one_pp'] = row['tokens'] / row['deduction_pp']
        effort_totals = defaultdict(Counter)
        for group in accepted:
            row = effort_totals[f"{group['model']}/{group['reasoning_effort']}"]
            row['groups'] += 1
            row['tokens'] += group['tokens']
            row['deduction_pp'] += group['deduction_pp']
        for row in effort_totals.values():
            row['pp_per_million_tokens'] = row['deduction_pp'] * 1_000_000 / row['tokens']
        windows[window] = {'model_efforts': dict(effort_totals), 'models': dict(totals), 'excluded': dict(exclusions), 'groups': accepted,
                           'last_valid_observed_at': max((g['observed_at'] for g in accepted), default=None),
                           'excluded_models': dict(excluded_models), 'excluded_model_efforts': dict(excluded_efforts)}

    daily = defaultdict(Counter)
    for event in selected:
        day = datetime.fromisoformat(event['recorded_at']).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
        daily[day][event.get('model') or 'unknown'] += event.get('total_tokens', 0)
    total = sum(row['total_tokens'] for row in models.values())
    for row in models.values():
        row['share_percent'] = row['total_tokens'] * 100 / total if total else 0
        row['input_cache_percent'] = (row['cached_input_tokens'] * 100 / row['input_tokens']
                                      if row['input_tokens'] else None)
    return {'application': application, 'model_efforts': dict(model_efforts), 'daily': dict(sorted(daily.items())), 'effort': effort, 'environment': environment, 'start': start.isoformat(), 'end': end.isoformat(), 'total_tokens': total,
            'events': len(selected), 'calibration_first_at': min(
                (r['created_at'] for r in calibration.get('records', [])), default=None),
            'models': dict(models), 'windows': windows,
            'calibration_coverage': {'models': dict(coverage), 'model_efforts': dict(coverage_efforts)},
            'quota_sample_count': len(history.get('account_limit_samples', [])),
            'current_limits': {w: snapshot.get(w) for w in ('five_hour', 'weekly')},
            'method': 'Sum same-model complete observed groups; exclude local overlapping '
                      'executions, ineligible records and unverified/reset-changing windows. '
                      'Use group_actual_percent once per group, never allocated actual_percent '
                      'or predicted/weighted tokens. Percent values are percentage points.',
            'limitations': ['Local logs cannot rule out untracked CLI/cloud/account activity.',
                            'Positive-delta groups omit unresolved zero changes; integer '
                            'quota reporting and delayed updates can bias estimates.',
                            'Observed token mixes and historical periods differ by model; '
                            'these are not intrinsic model multipliers or official rates.',
                            'Missing quota observations are excluded, not reconstructed.']}
