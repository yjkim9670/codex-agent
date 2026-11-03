# Subscription usage prediction

The `observed_token_mix_v2` predictor estimates subscription percentage points from
actual account-limit observations. API price ratios remain the legacy fallback;
they are not used to choose the new cached-input or output coefficients.

The backend ledger retains normalized input, cached-input and output tokens for
new runs. Older records are enriched in memory from uniquely matching stream
usage events (ID, model, effort and total must agree). Historical observations,
predictions and event files are preserved.

## Selection and validation

- Prefer validated model/effort token-mix fitting, then model token-mix fitting.
  Otherwise use validated effort, model, global and history scales in that order.
- Use whole observation batches. Fit only homogeneous model/effort groups; any
  excluded concurrent stream or missing batch member excludes the entire batch.
  The measured batch total is used, rather than treating allocated shares as
  separate actual measurements. Model-wide fallback can combine efforts.
- Require valid token components and standard service tier. Pending/reset-excluded
  observations cannot train the predictor. Reject observations before completion
  or delayed more than two hours for 5h and 24 hours for weekly.
- Fit the most recent 40 eligible groups using an empirical grid of positive
  cached-input and output weights, normalized to uncached input. Coefficients are
  bounded and are not evidence of an official quota formula or causal effect.
- Walk forward through those groups, fitting each prediction from earlier groups
  only. Require six initial training groups, at least four held-out groups, at
  least five total observed percentage points, and at least 5% lower mean absolute
  error than the prior estimator before applying the candidate.
- After rollout, groups predicted using token-mix fitting compare against a
  raw-token counterfactual fitted from prior observations. This prevents a useful
  predictor from disabling itself merely because its own earlier predictions
  were equally accurate.

The message footer and backend finalization both select this calibrated estimator.
Incomplete/estimated token data use the previous fallback. Session aggregates
without model metadata continue to use the account history scale.

Account percentages are rounded and include external activity. Eligible groups
reduce known contamination; these remain estimates, not exact per-task billing.
Changing predictions does not change actual subscription usage.

## Sub-percentage-point Chat observations

Fractional positive quota changes (for example 0.125 percentage points) remain
valid measurements; there is no one-percentage-point minimum. Sequential Chat
executions of the same model and effort continue to accumulate until a positive
change is observed, subject to the existing account, reset and isolation checks.

An unchanged integer reading now retains a separate `resolution_observation`
with the complete group and its last verified observation. The dashboard's
“1%p 미만 차감 관측” disclosure shows a conditional reference range:
`reported_pp_per_million_upper = 1,000,000 / group_tokens`. For example, five
million tokens within one unchanged integer bin gives less than 0.2 pp per
million, assuming one-pp reporting bins and up-to-date observations. Quota update
delays can invalidate this interpretation. It is not a measured fractional
deduction, an unconditional billing bound, or evidence of zero usage.

The whole group is retained once per window, including after observation timeout;
it is never summed into positive measurements, ranked in the comparison chart,
or used to train predictions. A later verified positive delta supersedes it on
ordinary re-collection. Saturated 100% readings, noninteger unchanged baselines,
changed resets, mixed or overlapping executions and incomplete groups cannot
create a one-pp reference. Existing period, app, environment and effort filters
also apply to these groups. Historical records without verified before/after
observations remain unlinked; no missing deductions are reconstructed.

## Pending observation recovery and freshness

Reconciliation excludes each pending entry with a missing baseline, invalid
creation timestamp, or observation age over eight days independently. These
entries cannot block newer valid entries or receive part of their observed
delta. Entries newer than the account snapshot remain pending. Cleanup still
runs when the snapshot's percentage is unavailable; valid entries wait for a
usable observation. Repeated reconciliation of the same snapshot is idempotent.
Exclusions keep their reason and timestamp in the existing ledger; no historical
quota deductions are fabricated. Recovery runs on the next ordinary account
usage refresh after the updated server is loaded.

The usage dashboard separates collection/limit-query times from each window's
last accepted observation under the selected filters. It shows pending counts
within the selected period and flags accepted observations older than 24 hours.
This freshness indicator refers to validated comparison groups, not the ledger's
last write or proof that a prediction model has been retrained.

## Reproduce validation

```sh
python scripts/validate_usage_prediction.py --account-dir /path/to/account \
  --model gpt-6.1-sol --effort medium
python -m pytest -q tests/test_usage_prediction.py
node tests/test_usage_prediction.cjs
```

The validator reads the account ledger and event log without rewriting them. It
reports eligibility, weights, held-out errors and observation dates. After Git
synchronization, restart the relevant Workbench server and refresh the app to load
the backend and browser changes. Older recorded predictions remain available for
comparison; the footer is recalculated using the latest validated summary.
