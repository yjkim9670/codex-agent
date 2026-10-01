#!/usr/bin/env python3
"""Compare local model tokens and observed quota deductions without API calls."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services.model_usage_analysis import analyze

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-root', type=Path, required=True)
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--effort', default='all')
    parser.add_argument('--environment', default='all')
    args = parser.parse_args()
    if args.days < 1:
        parser.error('--days must be positive')
    report = analyze(args.account_root.expanduser(), args.days, args.effort, args.environment)
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(output, encoding='utf-8')
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
