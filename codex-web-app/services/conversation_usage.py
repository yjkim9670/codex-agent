"""Read Chat's durable outbox. The Workbench collector is the only cache writer."""
import json
import os
from pathlib import Path
import sqlite3

from shared.chat_usage_sources import chat_roots


def chat_root():
    return Path(os.environ.get('CHAT_DATA_DIR') or Path(__file__).resolve().parents[2] / '.agent_state/conversation').resolve()


def usage_chat_roots():
    return chat_roots(chat_root())


def chat_source_signature():
    result = []
    for root in usage_chat_roots():
        path = root / 'conversations.sqlite3'
        # Include WAL changes: delayed quota observations can update an existing row.
        files = []
        for source in (path, Path(str(path) + '-wal')):
            try:
                stat = source.stat()
                files.append([str(source), stat.st_ino, stat.st_size, stat.st_mtime_ns])
            except FileNotFoundError:
                files.append([str(source), None])
        result.append({'root': str(root), 'files': files})
    return result


def read_chat_outbox(provider_identity):
    if not provider_identity:
        return []
    events = {}
    for root in usage_chat_roots():
        path = root / 'conversations.sqlite3'
        if not path.is_file():
            # A registered source must not disappear silently from a shared cache.
            raise FileNotFoundError('Configured Chat DB unavailable: ' + str(path))
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2) as db:
            rows = [json.loads(row[0]) for row in db.execute('SELECT event FROM usage_outbox')]
        for event in rows:
            if event.get('provider_account_id') != provider_identity:
                continue
            key = event['event_id']
            if key in events and events[key] != event:
                raise ValueError('Conflicting Chat usage event: ' + key)
            events[key] = event
    return list(events.values())


def application_of(event):
    if event.get('application'):
        return event['application']
    workspace = str(event.get('workspace_path') or '').replace('\\', '/')
    if workspace.rstrip('/').endswith('/conversation/empty_workspace') or workspace == str(chat_root() / 'empty_workspace'):
        return 'workbench-chat'
    return 'workbench' if event.get('source') != 'rollout' else 'unknown'
