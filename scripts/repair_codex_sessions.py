#!/usr/bin/env python3
"""Repair and consolidate duplicated Codex session stores."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent.config import (  # noqa: E402
    CODEX_CHAT_STORE_PATH,
    LEGACY_CODEX_CHAT_STORE_PATH,
    REPO_ROOT,
    WORKSPACE_DIR,
)
from codex_agent.services import codex_chat  # noqa: E402


def _paths_match(path_a: Path, path_b: Path) -> bool:
    try:
        return path_a.resolve() == path_b.resolve()
    except Exception:
        return str(path_a) == str(path_b)


def _append_unique_path(paths: list[Path], candidate: Path | None) -> None:
    if candidate is None:
        return
    try:
        candidate_path = Path(candidate)
    except Exception:
        return
    for existing in paths:
        if _paths_match(existing, candidate_path):
            return
    paths.append(candidate_path)


def _iter_candidate_paths() -> list[Path]:
    primary = Path(CODEX_CHAT_STORE_PATH)
    candidates: list[Path] = []
    repo_parent = REPO_ROOT.parent
    _append_unique_path(candidates, primary)
    _append_unique_path(candidates, Path(LEGACY_CODEX_CHAT_STORE_PATH))
    _append_unique_path(candidates, WORKSPACE_DIR / '.agent_state' / primary.name)
    _append_unique_path(candidates, repo_parent / 'codex_chat_sessions.json')
    _append_unique_path(candidates, repo_parent / '.agent_state' / primary.name)
    try:
        uses_parent_layout = WORKSPACE_DIR.resolve() == repo_parent.resolve()
    except Exception:
        uses_parent_layout = False
    if uses_parent_layout:
        _append_unique_path(candidates, WORKSPACE_DIR / REPO_ROOT.name / 'workspace' / '.agent_state' / primary.name)
    return candidates


def _safe_read_payload(path: Path) -> dict:
    payload = codex_chat._read_json_object_from_path(path)
    if not isinstance(payload, dict):
        return {'sessions': []}
    sessions = payload.get('sessions')
    if not isinstance(sessions, list):
        sessions = []
    return {'sessions': sessions}


def _nested_message_depth(message) -> int:
    depth = 0
    current = message
    while isinstance(current, dict):
        nested = current.get('message')
        if not isinstance(nested, dict):
            break
        depth += 1
        current = nested
        if depth >= 4096:
            break
    return depth


def _build_nested_depth_report(payload: dict) -> dict:
    sessions = payload.get('sessions', []) if isinstance(payload, dict) else []
    if not isinstance(sessions, list):
        sessions = []
    max_depth = 0
    nested_messages = 0
    for session in sessions:
        messages = session.get('messages', []) if isinstance(session, dict) else []
        if not isinstance(messages, list):
            continue
        for message in messages:
            depth = _nested_message_depth(message)
            if depth > 0:
                nested_messages += 1
            if depth > max_depth:
                max_depth = depth
    return {
        'nested_message_count': nested_messages,
        'max_nested_depth': max_depth,
    }


def _backup_file(path: Path, timestamp: str) -> Path | None:
    if not path.exists():
        return None
    backup_path = path.with_name(f'{path.name}.bak.{timestamp}')
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def _archive_legacy_sources(paths: list[Path], primary: Path, timestamp: str) -> list[tuple[Path, Path]]:
    archived: list[tuple[Path, Path]] = []
    for path in paths:
        if _paths_match(path, primary):
            continue
        if not path.exists():
            continue
        target = path.with_name(f'{path.name}.legacy.{timestamp}')
        path.replace(target)
        archived.append((path, target))
    return archived


def main() -> int:
    parser = argparse.ArgumentParser(description='Repair and consolidate duplicated Codex session stores.')
    parser.add_argument('--apply', action='store_true', help='Write merged result to the primary store path.')
    parser.add_argument(
        '--archive-legacy',
        action='store_true',
        help='Rename duplicate legacy stores after merge (best used with --apply).',
    )
    args = parser.parse_args()

    candidate_paths = _iter_candidate_paths()
    existing_paths = [path for path in candidate_paths if path.exists()]
    print('Primary store:', CODEX_CHAT_STORE_PATH)
    print('Candidate stores:')
    for path in candidate_paths:
        marker = ' (exists)' if path.exists() else ''
        print(f'  - {path}{marker}')

    payloads = []
    for path in existing_paths:
        payload = _safe_read_payload(path)
        sessions = payload.get('sessions', [])
        print(f'Loaded {len(sessions)} sessions from {path}')
        payloads.append(codex_chat._load_session_store_payload_from_path(path))

    if not payloads:
        print('No existing session stores found.')
        return 0

    merged = codex_chat._merge_session_store_payloads(payloads)
    merged_sessions = merged.get('sessions', []) if isinstance(merged, dict) else []
    report = _build_nested_depth_report(merged)
    print(f'Merged sessions: {len(merged_sessions)}')
    print('Nested message report:', json.dumps(report, ensure_ascii=False))

    if not args.apply:
        print('Dry-run complete. Use --apply to write merged data.')
        return 0

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    primary_path = Path(CODEX_CHAT_STORE_PATH)
    primary_path.parent.mkdir(parents=True, exist_ok=True)

    backup_targets = [path for path in existing_paths if path.exists()]
    if primary_path not in backup_targets and primary_path.exists():
        backup_targets.append(primary_path)
    backups = []
    for path in backup_targets:
        backup_path = _backup_file(path, timestamp)
        if backup_path:
            backups.append((path, backup_path))
    if backups:
        print('Backups:')
        for src, dst in backups:
            print(f'  - {src} -> {dst}')

    codex_chat._write_json_atomic(primary_path, {'sessions': merged_sessions})
    print(f'Wrote merged sessions to {primary_path}')

    if args.archive_legacy:
        archived = _archive_legacy_sources(existing_paths, primary_path, timestamp)
        if archived:
            print('Archived legacy stores:')
            for src, dst in archived:
                print(f'  - {src} -> {dst}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
