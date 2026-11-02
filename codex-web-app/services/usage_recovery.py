"""Conservative quota reconstruction from retained observations; no file writes."""
from copy import deepcopy
from datetime import datetime, timedelta
import math

WINDOWS = ('five_hour', 'weekly')


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result


def event_key(event):
    return event.get('calibration_id') or (event['event_id'] if event['event_id'].startswith('chat:') else event['event_id'].split(':', 1)[-1])


def same_reset(left, right):
    try:
        return stamp(left) == stamp(right)
    except ValueError:
        return False


def interval(event):
    finish = stamp(event['recorded_at'])
    begin = stamp(event['execution_started_at']) if event.get('execution_started_at') else (
        finish - timedelta(milliseconds=event['duration_ms']) if event.get('duration_ms') is not None else None)
    return begin, finish


def sample(snapshot):
    return {'limits_observed_at': snapshot['observed_at'], **{
        f'{window}_{field}': (snapshot.get(window) or {}).get(field)
        for window in WINDOWS for field in ('used_percent', 'resets_at')}}


def reconstruct(record, event, events, samples, window, *, baseline_at=None):
    """Return a direct outcome only when the entire measured interval is isolated."""
    def excluded(reason):
        return {'status': 'excluded', 'reason': reason}
    begin, finish = interval(event)
    if begin is None or finish < begin:
        return excluded('unverified_execution_timing')
    before = record.get('limits_before', {}).get(window) or {}
    used, reset = before.get('used_percent'), before.get('resets_at')
    if not isinstance(used, (int, float)) or not math.isfinite(used) or not reset:
        return excluded('missing_baseline')
    # Old records lack baseline timestamps. Require an independently retained,
    # matching observation at most 15 minutes before execution, not a guessed value.
    if baseline_at is None:
        prior = [s for s in samples if s.get('limits_observed_at') and
                 begin - timedelta(minutes=15) <= stamp(s['limits_observed_at']) <= begin]
        prior.sort(key=lambda s: stamp(s['limits_observed_at']))
        if not prior or prior[-1].get(window + '_used_percent') != used or not same_reset(prior[-1].get(window + '_resets_at'), reset):
            return excluded('unverified_baseline')
        baseline_at = prior[-1]['limits_observed_at']
    baseline = stamp(baseline_at)
    if baseline > begin or begin - baseline > timedelta(minutes=15):
        return excluded('unverified_baseline')
    following = sorted((s for s in samples if s.get('limits_observed_at') and
                        finish <= stamp(s['limits_observed_at']) <= finish + timedelta(hours=24)),
                       key=lambda s: stamp(s['limits_observed_at']))
    for observation in following:
        percent = observation.get(window + '_used_percent')
        if percent is None:
            continue
        if not isinstance(percent, (int, float)) or not math.isfinite(percent):
            continue
        if not same_reset(observation.get(window + '_resets_at'), reset) or percent < used:
            return excluded('unverified_or_changed_reset')
        if percent <= used:
            continue
        observed = stamp(observation['limits_observed_at'])
        # Also reject observations at/after the advertised reset boundary.
        try:
            if stamp(reset) <= observed:
                return excluded('unverified_or_changed_reset')
        except ValueError:
            return excluded('unverified_or_changed_reset')
        for other in events:
            if other['event_id'] == event['event_id']:
                continue
            if other.get('application') == 'workbench-chat' and other.get('status') in ('queued', 'streaming'):
                other_begin, _ = interval(other)
                if other_begin is None or other_begin < observed:
                    return excluded('overlapping_local_execution')
            if other.get('total_tokens', 0) <= 0:
                continue
            other_begin, other_finish = interval(other)
            if other_begin is None:
                if baseline <= other_finish <= observed:
                    return excluded('unverified_execution_timing')
            elif other_finish > baseline and other_begin < observed:
                return excluded('overlapping_local_execution')
        delta = round(percent - used, 6)
        return {'status': 'observed', 'actual_percent': delta, 'group_actual_percent': delta,
                'group_id': f'{window}:{record["id"]}:{observation["limits_observed_at"]}',
                'group_size': 1, 'quality': 'isolated_retained_observation',
                'observed_at': observation['limits_observed_at']}
    return excluded('awaiting_quota_observation')


def recover_timeouts(records, events, samples, *, model=None, effort=None):
    """Produce a separate candidate ledger; never relax existing exclusion checks."""
    result, audit = deepcopy(records), []
    for record in result:
        if model and record.get('model') != model or effort and record.get('reasoning_effort') != effort:
            continue
        matched = [e for e in events if event_key(e) == record['id']]
        for window in WINDOWS:
            if record.get('outcomes', {}).get(window, {}).get('reason') != 'observation_timeout':
                continue
            if len(matched) != 1:
                outcome = {'status': 'excluded', 'reason': 'missing_or_ambiguous_event'}
            elif not record.get('learning_eligible'):
                outcome = {'status': 'excluded', 'reason': 'concurrent_flag'}
            elif matched[0].get('model') != record['model'] or matched[0].get('total_tokens') != record['raw_tokens']:
                outcome = {'status': 'excluded', 'reason': 'event_mismatch'}
            else:
                outcome = reconstruct(record, matched[0], events, samples, window)
            audit.append({'id': record['id'], 'created_at': record['created_at'], 'window': window, **outcome})
            if outcome['status'] == 'observed':
                record['outcomes'][window] = outcome
    return result, audit


def chat_calibration(outbox, events, historical_samples, *, now=None):
    records, retained = [], []
    for entry in outbox:
        quota = entry.get('quota_observations') or {}
        retained.extend(sample(q) for q in quota.values() if q.get('observed_at'))
    observations = [*historical_samples, *retained]
    for entry in outbox:
        if entry.get('status') not in ('completed', 'failed', 'cancelled', 'interrupted') or entry.get('usage_pending'):
            continue
        quota = entry.get('quota_observations') or {}
        if not quota:
            continue  # Legacy Chat use stays explicitly unlinked.
        matched = [e for e in events if event_key(e) == entry['event_id']]
        if len(matched) != 1 or matched[0].get('total_tokens', 0) <= 0:
            continue
        event = matched[0]
        before = quota.get('before') or {}
        record = {'id': entry['event_id'], 'created_at': entry['execution_completed_at'],
                  'application': 'workbench-chat', 'status': entry['status'],
                  'model': event.get('model'), 'reasoning_effort': event.get('reasoning_effort'),
                  'raw_tokens': event['total_tokens'], 'limits_before': {w: before.get(w) or {} for w in WINDOWS},
                  'token_usage': {k: event.get(k, 0) for k in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens')},
                  'outcomes': {}, 'learning_eligible': True, 'service_tier': 'standard',
                  'calculation_version': 'chat_isolated_observation_v1'}
        for window in WINDOWS:
            record['outcomes'][window] = reconstruct(record, event, events, observations, window,
                                                   baseline_at=before.get('observed_at'))
            if record['outcomes'][window].get('reason') == 'awaiting_quota_observation':
                record['outcomes'][window]['status'] = 'pending'
                if now is not None and now - interval(event)[1] > timedelta(hours=24):
                    record['outcomes'][window] = {'status': 'excluded', 'reason': 'observation_timeout'}
        observed_times = {o.get('observed_at') for o in record['outcomes'].values()}
        record['quota_samples'] = [s for s in observations if s.get('limits_observed_at') in observed_times]
        records.append(record)
    return records, retained
