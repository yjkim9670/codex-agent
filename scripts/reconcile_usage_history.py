#!/usr/bin/env python3
"""Analyze cached account usage; never requests API usage or restarts servers."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codex_agent.services.usage_reconciliation import build_usage_reconciliation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-root', type=Path, required=True)
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--record', action='store_true', help='Seed the shared observation tracker from cached data')
    args = parser.parse_args()
    root = args.account_root.expanduser().resolve()
    snapshot = json.loads((root / 'codex_account_usage_snapshot.json').read_text(encoding='utf-8'))
    ledger = json.loads((root / 'codex_account_token_usage.json').read_text(encoding='utf-8'))
    report = build_usage_reconciliation(snapshot, ledger, days=args.days)
    if args.record:
        from codex_agent.services.codex_chat import _record_account_usage_reconciliation
        recorded = _record_account_usage_reconciliation(
            {'account_token_usage_path': root / 'codex_account_token_usage.json'},
            snapshot, capture_source='cached_seed',
        )
        if not recorded:
            raise RuntimeError('Observation was not recorded; check freshness and the diagnostic log')
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding='utf-8')
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
