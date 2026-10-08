#!/usr/bin/env python3
"""Read-only walk-forward validation of empirical subscription quota estimates."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services.codex_chat import _calibration_records_with_token_usage
from codex_agent.services.usage_prediction import fit_quota_relation, observation_groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-dir', type=Path, required=True)
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--effort', default='medium')
    args = parser.parse_args()
    ledger = json.loads((args.account_dir / 'codex_usage_calibration.json').read_text())
    records = _calibration_records_with_token_usage(
        ledger['records'], args.account_dir / 'codex_usage_events.jsonl')
    report = {'model': args.model, 'reasoning_effort': args.effort, 'limits': {}}
    for name in ('five_hour', 'weekly'):
        relation = fit_quota_relation(records, name, args.model, args.effort)
        groups = observation_groups(records, name, args.model, args.effort)
        validation = relation['validation']
        old, new = validation['baseline_mae_percent'], validation['candidate_mae_percent']
        relation['mae_reduction_percent'] = (100 * (1 - new / old) if old else None)
        relation['first_observed_at'] = groups[0]['observed_at'] if groups else None
        relation['last_observed_at'] = groups[-1]['observed_at'] if groups else None
        report['limits'][name] = relation
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
