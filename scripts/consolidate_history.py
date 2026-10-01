#!/usr/bin/env python3
"""Export/import histories without modifying original stores or execution DBs."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent.services.history_library import (
    HistoryLibraryError, build_source, collect_source, import_sources, library_path,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', default=[], metavar='WORKBENCH_DIR')
    parser.add_argument('--workspace', help='Explicit project path (with one --source, or --store)')
    parser.add_argument('--store', action='append', default=[], help='Explicit JSON store; requires --workspace')
    parser.add_argument('--library', type=Path, default=library_path())
    parser.add_argument('--apply', action='store_true', help='Write library with backup; default is dry-run')
    args = parser.parse_args()
    if not args.source and not args.store:
        parser.error('at least one --source or --store is required')
    if args.store and (not args.workspace or args.source):
        parser.error('--store requires --workspace and cannot be combined with --source')
    if args.workspace and len(args.source) > 1:
        parser.error('--workspace can only be used with one --source')
    try:
        sources = ([build_source(args.workspace, args.store)] if args.store else
                   [collect_source(root, args.workspace) for root in args.source])
        payload = import_sources(sources, args.library, apply=args.apply)
    except (HistoryLibraryError, OSError) as exc:
        parser.exit(1, f'Import aborted: {exc}\n')
    print(json.dumps({'applied': args.apply, 'library': str(args.library),
                      'projects': [{'workspace': s['workspace_path'], 'sessions': len(s['sessions']),
                                    'stores': s['store_paths']} for s in payload['sources'].values()]},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
