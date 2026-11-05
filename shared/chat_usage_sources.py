"""Personal Chat source registration shared by all Workbench checkouts."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .chat_accounts import registry_path


def register_chat_root(root):
    root = Path(root).expanduser().resolve()
    directory = registry_path().parent / 'chat_usage_sources'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(str(root).encode()).hexdigest()
    target = directory / (key + '.json')
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix='.source-')
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump({'version': 1, 'root': str(root)}, stream)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def chat_roots(default):
    # CHAT_DATA_DIR remains a source even before its server has registered it.
    local = Path(os.environ.get('CHAT_DATA_DIR') or default).expanduser().resolve()
    roots = {local} if os.environ.get('CHAT_DATA_DIR') or (local / 'conversations.sqlite3').is_file() else set()
    directory = registry_path().parent / 'chat_usage_sources'
    for path in sorted(directory.glob('*.json')):
        row = json.loads(path.read_text(encoding='utf-8'))
        if row.get('version') != 1 or not Path(row['root']).is_absolute():
            raise ValueError('Invalid Chat usage source: ' + str(path))
        roots.add(Path(row['root']).resolve())
    return sorted(roots, key=str)
