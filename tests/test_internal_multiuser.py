"""Black-box coverage for the opt-in internal multi-user deployment mode."""

import json
import os
from pathlib import Path
import subprocess
import sys
from io import BytesIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_internal_mode_isolates_ip_users_and_file_roots(tmp_path):
    data_dir = tmp_path / 'internal-state'
    map_path = data_dir / 'user_map.json'
    map_path.parent.mkdir(parents=True)
    map_path.write_text(json.dumps({
        'users': [
            {'ip': '10.20.0.11', 'username': 'alice', 'role': 'admin'},
            {'ip': '10.20.0.12', 'username': 'bob', 'role': 'member'},
        ],
    }), encoding='utf-8')
    script = r'''
import json
from codex_agent.codex_app import create_codex_app
app = create_codex_app()
app.config['TESTING'] = True
out = {}
with app.test_client() as alice:
    out['unknown'] = alice.get('/health', environ_overrides={'REMOTE_ADDR': '10.20.0.99'}).status_code
    out['alice_create'] = alice.post('/api/codex/sessions', json={'title': 'alice'}, environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).status_code
    out['alice_files'] = alice.post('/api/codex/files/list', json={'root': 'workspace', 'path': ''}, environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).status_code
    out['server_blocked'] = alice.post('/api/codex/files/list', json={'root': 'server', 'path': ''}, environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).status_code
with app.test_client() as bob:
    bob_response = bob.get('/api/codex/sessions', environ_overrides={'REMOTE_ADDR': '10.20.0.12'})
    out['bob_status'] = bob_response.status_code
    out['bob_payload'] = bob_response.get_json()
print(json.dumps(out))
'''
    env = os.environ.copy()
    env.update({
        'CODEX_WORKBENCH_MODE': 'internal-multiuser',
        'CODEX_INTERNAL_DATA_DIR': str(data_dir),
        'CODEX_INTERNAL_USER_MAP_PATH': str(map_path),
        'CODEX_REQUIRE_ACCOUNT_LOGIN': '0',
        'CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS': '0',
        'CODEX_REQUIRE_ENCRYPTED_FILE_WRITES': '0',
    })
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=PROJECT_ROOT, env=env,
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    assert outcome['unknown'] == 403
    assert outcome['alice_create'] == 200
    assert outcome['alice_files'] == 200
    assert outcome['server_blocked'] == 400
    assert outcome['bob_status'] == 200
    assert outcome['bob_payload']['sessions'] == []
    assert (data_dir / 'users' / 'alice' / '.agent_state' / 'codex_chat_sessions.json').is_file()
    assert not (data_dir / 'users' / 'bob' / '.agent_state' / 'codex_chat_sessions.json').exists()


def test_internal_mode_accepts_windows_powershell_utf8_bom_user_map(tmp_path):
    data_dir = tmp_path / 'internal-state'
    map_path = data_dir / 'user_map.json'
    map_path.parent.mkdir(parents=True)
    # Windows PowerShell 5.1's `Set-Content -Encoding UTF8` writes this BOM.
    map_path.write_text(json.dumps({'users': [
        {'ip': '12.80.214.204', 'username': 'dinya', 'role': 'admin'},
    ]}), encoding='utf-8-sig')
    script = r'''
from codex_agent.codex_app import create_codex_app
app = create_codex_app(); app.config['TESTING'] = True
with app.test_client() as client:
    response = client.get('/health', environ_overrides={'REMOTE_ADDR': '12.80.214.204'})
print(response.status_code)
'''
    env = os.environ.copy()
    env.update({
        'CODEX_WORKBENCH_MODE': 'internal-multiuser',
        'CODEX_INTERNAL_DATA_DIR': str(data_dir),
        'CODEX_INTERNAL_USER_MAP_PATH': str(map_path),
        'CODEX_REQUIRE_ACCOUNT_LOGIN': '0',
        'CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS': '0',
        'CODEX_REQUIRE_ENCRYPTED_FILE_WRITES': '0',
    })
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=PROJECT_ROOT, env=env,
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == '200'


def test_internal_shared_rtl_knowledge_is_versioned_readonly_and_imported(tmp_path):
    data_dir = tmp_path / 'internal-state'
    map_path = data_dir / 'user_map.json'
    map_path.parent.mkdir(parents=True)
    map_path.write_text(json.dumps({'users': [
        {'ip': '10.20.0.11', 'username': 'admin', 'role': 'admin'},
        {'ip': '10.20.0.12', 'username': 'member', 'role': 'member'},
    ]}), encoding='utf-8')
    script = r'''
import json
from io import BytesIO
from codex_agent.codex_app import create_codex_app
app = create_codex_app(); app.config['TESTING'] = True
out = {}
with app.test_client() as admin:
    response = admin.post('/api/codex/shared-knowledge/revisions', data={
        'revision_id': 'uart-r1', 'title': 'UART r1', 'files': [
            (BytesIO(b'module uart_tx(input clk, output tx); endmodule\n'), 'rtl/uart_tx.sv'),
            (BytesIO(b'# UART\n'), 'docs/uart.md'),
        ],
    }, content_type='multipart/form-data', environ_overrides={'REMOTE_ADDR': '10.20.0.11'})
    out['create'] = response.status_code
with app.test_client() as member:
    response = member.get('/api/codex/shared-knowledge/revisions', environ_overrides={'REMOTE_ADDR': '10.20.0.12'})
    out['list'] = response.get_json()
    out['shared_list'] = member.post('/api/codex/files/list', json={'root': 'shared', 'path': ''}, environ_overrides={'REMOTE_ADDR': '10.20.0.12'}).status_code
    out['shared_write'] = member.post('/api/codex/files/write', json={'root': 'shared', 'path': 'revisions/uart-r1/source/rtl/uart_tx.sv', 'content': 'x'}, environ_overrides={'REMOTE_ADDR': '10.20.0.12'}).status_code
    response = member.post('/api/codex/shared-knowledge/revisions/uart-r1/import', environ_overrides={'REMOTE_ADDR': '10.20.0.12'})
    out['import'] = response.get_json()
print(json.dumps(out))
'''
    env = os.environ.copy()
    env.update({
        'CODEX_WORKBENCH_MODE': 'internal-multiuser', 'CODEX_INTERNAL_DATA_DIR': str(data_dir),
        'CODEX_INTERNAL_USER_MAP_PATH': str(map_path), 'CODEX_REQUIRE_ACCOUNT_LOGIN': '0',
        'CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS': '0', 'CODEX_REQUIRE_ENCRYPTED_FILE_WRITES': '0',
    })
    result = subprocess.run([sys.executable, '-c', script], cwd=PROJECT_ROOT, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    assert outcome['create'] == 201
    assert outcome['list']['revisions'][0]['revision_id'] == 'uart-r1'
    assert outcome['shared_list'] == 200
    assert outcome['shared_write'] == 403
    assert outcome['import']['workspace_path'] == '.codex-knowledge/uart-r1'
    assert (data_dir / 'users' / 'member' / 'workspace' / '.codex-knowledge' / 'uart-r1' / 'rtl' / 'uart_tx.sv').is_file()
