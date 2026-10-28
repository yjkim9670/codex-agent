"""Read Chat's durable outbox. The Workbench collector is the only cache writer."""
import json
import os
from pathlib import Path
import sqlite3


def chat_root():
    return Path(os.environ.get('CHAT_DATA_DIR') or Path(__file__).resolve().parents[2] / '.agent_state/conversation').resolve()


def read_chat_outbox(provider_identity):
    if not provider_identity:
        return []
    path = chat_root() / 'conversations.sqlite3'
    if not path.is_file():
        return []
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2) as db:
        events = [json.loads(row[0]) for row in db.execute('SELECT event FROM usage_outbox')]
    return [e for e in events if e.get('provider_account_id') == provider_identity]


def application_of(event):
    if event.get('application'):
        return event['application']
    workspace = str(event.get('workspace_path') or '').replace('\\', '/')
    if workspace.rstrip('/').endswith('/conversation/empty_workspace') or workspace == str(chat_root() / 'empty_workspace'):
        return 'workbench-chat'
    return 'workbench' if event.get('source') != 'rollout' else 'unknown'
