"""Subscription quota estimates learned from complete observation groups.

Weights are empirical quota coefficients, never API prices. Validation fits each
held-out observation using earlier groups only; historical predictions stay intact.
"""
from datetime import datetime
import math


TOKEN_KEYS = ('input_tokens', 'cached_input_tokens', 'output_tokens')


def token_components(usage):
    if not isinstance(usage, dict) or usage.get('estimated') or not all(key in usage for key in TOKEN_KEYS):
        return None
    try:
        values = [float(usage[key]) for key in TOKEN_KEYS]
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(value) or value < 0 for value in values):
        return None
    inputs, cached, outputs = values
    if cached > inputs or inputs + outputs <= 0:
        return None
    total = usage.get('total_tokens')
    try:
        if total is not None and not math.isclose(float(total), inputs + outputs, abs_tol=1):
            return None
    except (TypeError, ValueError):
        return None
    return (inputs - cached, cached, outputs)


def observation_groups(records, limit_name, model, effort=None):
    """Select whole, homogeneous groups, including every rounding-batch member."""
    grouped = {}
    for record in records:
        outcome = (record.get('outcomes') or {}).get(limit_name, {})
        if outcome.get('status') == 'observed':
            key = outcome.get('group_id') or record.get('id')
            grouped.setdefault(key, []).append((record, outcome))
    result = []
    for members in grouped.values():
        if any(
            str(record.get('model', '')).lower() != model.lower()
            or (effort is not None and record.get('reasoning_effort', '') != effort)
            or record.get('service_tier', 'standard') != 'standard'
            or record.get('learning_eligible') is False
            or record.get('status') not in {'completed', 'failed'}
            or outcome.get('group_size', 1) != len(members)
            for record, outcome in members
        ):
            continue
        components = [token_components(record.get('token_usage')) for record, _ in members]
        if any(value is None for value in components):
            continue
        try:
            observed = max(outcome['observed_at'] for _, outcome in members)
            observed_time = datetime.fromisoformat(observed)
            delays = [(observed_time - datetime.fromisoformat(record['created_at'])).total_seconds()
                      for record, _ in members]
            # Long-delayed account snapshots cannot safely identify task consumption.
            if min(delays) < 0 or max(delays) > (7200 if limit_name == 'five_hour' else 86400):
                continue
            actuals = [float(outcome.get('group_actual_percent', 0)) for _, outcome in members]
            if not actuals[0]:
                actuals = [sum(float(outcome['actual_percent']) for _, outcome in members)] * len(members)
            if actuals[0] <= 0 or any(value != actuals[0] for value in actuals):
                continue
            baseline = sum(float(record['predictions'][limit_name]) for record, _ in members)
            if not math.isfinite(actuals[0]) or not math.isfinite(baseline) or baseline < 0:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        result.append({'observed_at': observed, 'actual': actuals[0], 'baseline': baseline,
                       'components': tuple(sum(value[i] for value in components) for i in range(3)),
                       'baseline_is_mix': any((record.get('prediction_sources') or {}).get(limit_name)
                                              in {'effort_token_mix', 'model_token_mix'}
                                              for record, _ in members)})
    return sorted(result, key=lambda group: group['observed_at'])[-40:]


def _load(group, weights):
    return sum(value * weight for value, weight in zip(group['components'], weights))


def _fit(groups):
    actual = sum(group['actual'] for group in groups)
    best = None
    # Prefer equal weights on ties, requiring evidence for token-mix complexity.
    for cached in (1, .75, .5, .35, .2, .1, .05):
        for output in (1, 2, 4, 8, 16, 32):
            weights = (1, cached, output)
            scale = sum(_load(group, weights) for group in groups) / actual
            error = sum(abs(_load(group, weights) / scale - group['actual']) for group in groups)
            if best is None or error < best[0] - 1e-9:
                best = (error, weights, scale)
    return best[1], best[2]


def fit_quota_relation(records, limit_name, model, effort=None):
    groups = observation_groups(records, limit_name, model, effort)
    errors, baselines = [], []
    for index in range(6, len(groups)):
        weights, scale = _fit(groups[:index])
        group = groups[index]
        errors.append(abs(_load(group, weights) / scale - group['actual']))
        baseline_prediction = group['baseline']
        if group['baseline_is_mix']:
            # After rollout, compare to the previous raw-token estimator rather
            # than requiring another 5% improvement over our own predictions.
            raw_scale = sum(sum(item['components']) for item in groups[:index]) / sum(
                item['actual'] for item in groups[:index])
            baseline_prediction = sum(group['components']) / raw_scale
        baselines.append(abs(baseline_prediction - group['actual']))
    candidate = sum(errors) / len(errors) if errors else None
    baseline = sum(baselines) / len(baselines) if baselines else None
    applied = bool(len(errors) >= 4 and sum(group['actual'] for group in groups) >= 5
                   and candidate < baseline * .95)
    weights, scale = _fit(groups) if groups else ((1, 1, 1), None)
    return {'is_applied': applied, 'observation_group_count': len(groups),
            'weights': dict(zip(('uncached_input', 'cached_input', 'output'), weights)),
            'tokens_per_percent': scale, 'weighting_basis': 'observed_subscription_quota',
            'validation': {'method': 'walk_forward', 'sample_count': len(errors),
                           'candidate_mae_percent': candidate, 'baseline_mae_percent': baseline,
                           'baseline_method': 'recorded_or_prior_raw_token_counterfactual',
                           'improved': applied}}


def predict_percent(relation, usage):
    components = token_components(usage)
    if not relation.get('is_applied') or components is None:
        return None
    weights = relation['weights']
    return sum(value * weights[key] for value, key in
               zip(components, ('uncached_input', 'cached_input', 'output'))) / relation['tokens_per_percent']
