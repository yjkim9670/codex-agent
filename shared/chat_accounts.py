"""Read-only personal Workbench account discovery; no server imports."""
import json
import os
import pwd
from pathlib import Path


def login_home():
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def registry_path():
    root = os.environ.get('CODEX_WORKBENCH_SHARED_ACCOUNT_STATE_DIR')
    return (Path(root).expanduser() if root else login_home() / '.codex-workbench') / 'codex_accounts.json'


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def accounts():
    rows = read_json(registry_path()).get('accounts', [])
    if not rows:
        rows = [{'id': 'personal', 'label': 'Personal Codex', 'codex_home': str(login_home() / '.codex')}]
    result = []
    for row in rows:
        auth = read_json(Path(row['codex_home']) / 'auth.json')
        tokens = auth.get('tokens') or {}
        result.append({**row, 'authenticated': bool(tokens.get('access_token') and tokens.get('account_id')),
                       'provider_account_id': tokens.get('account_id', '')})
    return result


def get_account(account_id):
    for row in accounts():
        if row['id'] == account_id:
            if not row['authenticated']:
                raise ValueError('선택한 개인 Codex 계정에 먼저 로그인해 주세요.')
            return row
    raise ValueError('알 수 없는 계정입니다.')
