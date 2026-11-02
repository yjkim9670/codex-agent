#!/usr/bin/env python3
"""Write a recovery audit and candidate ledger, leaving account originals intact."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services.usage_recovery import recover_timeouts
from codex_agent.services.model_usage_analysis import analyze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--model', default='gpt-6-luna')
    parser.add_argument('--effort', default='xhigh')
    args = parser.parse_args()
    root, output = args.account_root.resolve(), args.output_dir.resolve()
    canonical = Path(__file__).resolve().parents[1]
    if not output.is_relative_to(canonical) or output.is_relative_to(root):
        parser.error('output must be in the canonical checkout and outside the account source')
    names = ('codex_usage_calibration.json', 'codex_usage_history.json', 'codex_usage_collection.json')
    raw = {name: (root / name).read_bytes() for name in names}
    data = {name: json.loads(value) for name, value in raw.items()}
    records, audit = recover_timeouts(data[names[0]]['records'], data[names[2]]['events'],
                                     data[names[1]]['account_limit_samples'], model=args.model, effort=args.effort)
    candidate = {**data[names[0]], 'records': records}
    report = analyze(root, data={'events': data[names[2]]['events'], names[0]: candidate, names[1]: data[names[1]]})
    result = {'source_sha256': {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()},
              'source_unchanged': all((root / name).read_bytes() == value for name, value in raw.items()),
              'model': args.model, 'effort': args.effort,
              'records_checked': len({r['id'] for r in audit}),
              'outcomes': dict(Counter(f"{r['window']}:{r.get('reason', r['status'])}" for r in audit)),
              'audit': audit, 'candidate_analysis': report}
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('recovery-audit.json', result), ('candidate-calibration.json', candidate)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('audit', 'candidate_analysis')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
