"""Black-box coverage for the opt-in internal multi-user deployment mode."""

import json
import os
from pathlib import Path
import subprocess
import sys
import hashlib
from io import BytesIO

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _storage_key(ip):
    return 'ip-' + hashlib.sha256(ip.encode('utf-8')).hexdigest()[:24]


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
    assert (data_dir / 'users' / _storage_key('10.20.0.11') / '.agent_state' / 'codex_chat_sessions.json').is_file()
    assert not (data_dir / 'users' / _storage_key('10.20.0.12') / '.agent_state' / 'codex_chat_sessions.json').exists()


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


def test_internal_admin_receives_member_view_switch_but_member_does_not(tmp_path):
    data_dir = tmp_path / 'internal-state'
    map_path = data_dir / 'user_map.json'
    map_path.parent.mkdir(parents=True)
    map_path.write_text(json.dumps({'users': [
        {'ip': '10.20.0.11', 'username': 'admin', 'role': 'admin'},
        {'ip': '10.20.0.12', 'username': 'member', 'role': 'member'},
    ]}), encoding='utf-8')
    script = r'''
from codex_agent.codex_app import create_codex_app
app = create_codex_app(); app.config['TESTING'] = True
with app.test_client() as client:
    admin = client.get('/', environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).get_data(as_text=True)
    member = client.get('/', environ_overrides={'REMOTE_ADDR': '10.20.0.12'}).get_data(as_text=True)
print('admin-switch=' + str('data-internal-view="member"' in admin))
print('admin-role=' + str('data-internal-role="admin"' in admin))
print('member-switch=' + str('data-internal-view="member"' in member))
print('member-role=' + str('data-internal-role="member"' in member))
'''
    env = os.environ.copy()
    env.update({
        'CODEX_WORKBENCH_MODE': 'internal-multiuser', 'CODEX_INTERNAL_DATA_DIR': str(data_dir),
        'CODEX_INTERNAL_USER_MAP_PATH': str(map_path), 'CODEX_REQUIRE_ACCOUNT_LOGIN': '0',
        'CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS': '0', 'CODEX_REQUIRE_ENCRYPTED_FILE_WRITES': '0',
    })
    result = subprocess.run([sys.executable, '-c', script], cwd=PROJECT_ROOT, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-4:] == [
        'admin-switch=True', 'admin-role=True', 'member-switch=False', 'member-role=True',
    ]


def test_internal_model_settings_are_admin_only_and_organization_wide(tmp_path):
    data_dir = tmp_path / 'internal-state'
    map_path = data_dir / 'user_map.json'
    map_path.parent.mkdir(parents=True)
    map_path.write_text(json.dumps({'users': [
        {'ip': '10.20.0.11', 'username': 'admin', 'role': 'admin'},
        {'ip': '10.20.0.12', 'username': 'member', 'role': 'member'},
    ]}), encoding='utf-8')
    script = r'''
import json
from codex_agent.codex_app import create_codex_app
app = create_codex_app(); app.config['TESTING'] = True
out = {}
with app.test_client() as client:
    out['member_write'] = client.patch('/api/codex/settings', json={'agent_backend': 'dtgpt'}, environ_overrides={'REMOTE_ADDR': '10.20.0.12'}).status_code
    out['admin_write'] = client.patch('/api/codex/settings', json={'agent_backend': 'dtgpt', 'model': 'gpt-5'}, environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).status_code
    out['member_settings'] = client.get('/api/codex/settings', environ_overrides={'REMOTE_ADDR': '10.20.0.12'}).get_json()['settings']
    admin_html = client.get('/', environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).get_data(as_text=True)
print(json.dumps({'member_write': out['member_write'], 'admin_write': out['admin_write'], 'model': out['member_settings']['model'], 'overlay': 'codex-internal-api-key-pool-overlay' in admin_html, 'admin_only': 'data-internal-admin-only' in admin_html}))
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
    assert outcome == {'member_write': 403, 'admin_write': 200, 'model': 'gpt-5', 'overlay': True, 'admin_only': True}
    assert (data_dir / 'organization' / 'codex_settings.json').is_file()


def test_internal_shared_rtl_knowledge_is_versioned_readonly_and_imported(tmp_path):
    data_dir = tmp_path / 'internal-state'
    map_path = data_dir / 'user_map.json'
    map_path.parent.mkdir(parents=True)
    map_path.write_text(json.dumps({'users': [
        {'ip': '10.20.0.11', 'username': 'admin', 'role': 'admin'},
        {'ip': '10.20.0.12', 'username': 'member', 'role': 'member'},
    ]}), encoding='utf-8')
    script = r'''
import base64
import json
import os
from io import BytesIO
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from codex_agent.codex_app import create_codex_app

def encrypted_payload(client, payload, remote):
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    handshake = client.post('/api/codex/files/crypto-session', json={
        'client_public_key': base64.b64encode(public).decode('ascii'),
    }, environ_overrides=remote)
    assert handshake.status_code == 200
    session = handshake.get_json()
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), base64.b64decode(session['server_public_key']))
    key = HKDF(algorithm=hashes.SHA256(), length=64, salt=base64.b64decode(session['salt']),
               info=b'codex-workbench-file-browser-v1').derive(private.exchange(ec.ECDH(), peer))[:32]
    iv = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(iv, json.dumps(payload).encode('utf-8'), session['crypto_session_id'].encode('ascii'))
    return {'encrypted': True, 'crypto_session_id': session['crypto_session_id'],
            'iv': base64.b64encode(iv).decode('ascii'), 'ciphertext': base64.b64encode(ciphertext).decode('ascii')}

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
    remote = {'REMOTE_ADDR': '10.20.0.12'}
    write = {'root': 'shared', 'path': 'revisions/uart-r1/source/rtl/uart_tx.sv', 'content': 'x'}
    plain = member.post('/api/codex/files/write', json=write, environ_overrides=remote)
    out['plain_write'] = [plain.status_code, plain.get_json()['error_code']]
    out['shared_writes'] = []
    for mutation in (write, dict(write, mode='patch', patch={'start': 0, 'delete_count': 1, 'insert': 'x'})):
        response = member.post('/api/codex/files/write', json=encrypted_payload(member, mutation, remote), environ_overrides=remote)
        out['shared_writes'].append([response.status_code, response.get_json()['error_code']])
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
    assert outcome['plain_write'] == [400, 'encrypted_file_write_required']
    assert outcome['shared_writes'] == [[403, 'read_only_root'], [403, 'read_only_root']]
    assert outcome['import']['workspace_path'] == '.codex-knowledge/uart-r1'
    assert (data_dir / 'users' / _storage_key('10.20.0.12') / 'workspace' / '.codex-knowledge' / 'uart-r1' / 'rtl' / 'uart_tx.sv').is_file()
    assert (data_dir / 'organization' / 'shared-knowledge' / 'revisions' / 'uart-r1' / 'source' / 'rtl' / 'uart_tx.sv').read_bytes() == b'module uart_tx(input clk, output tx); endmodule\n'


def test_internal_profile_uses_ip_hash_storage_and_preserves_legacy_data(tmp_path):
    data_dir = tmp_path / 'internal-state'
    map_path = data_dir / 'user_map.json'
    legacy_workspace = data_dir / 'users' / 'alice' / 'workspace'
    legacy_workspace.mkdir(parents=True)
    (legacy_workspace / 'keep.txt').write_text('keep', encoding='utf-8')
    map_path.write_text(json.dumps({'users': [
        {'ip': '10.20.0.11', 'username': 'alice', 'role': 'member'},
    ]}), encoding='utf-8')
    script = r'''
import json
from threading import Event
from codex_agent.codex_app import create_codex_app
from codex_agent.services import usage_dashboard
# Force the collector to finish before the first HTTP request. Previously it
# created the hash root first, which made request-time migration skip all data.
collected = Event()
collect = usage_dashboard.collect
def collect_before_http(*args, **kwargs):
    result = collect(*args, **kwargs)
    collected.set()
    return result
usage_dashboard.collect = collect_before_http
app = create_codex_app(); app.config['TESTING'] = True
assert collected.wait(5), 'usage collector did not complete before HTTP access'
with app.test_client() as client:
    root = client.get('/', environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).get_data(as_text=True)
    profile = client.put('/api/codex/internal/profile', json={'username': 'alice-new'}, environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).get_json()
    listing = client.post('/api/codex/files/list', json={'root': 'workspace', 'path': ''}, environ_overrides={'REMOTE_ADDR': '10.20.0.11'}).get_json()
print(json.dumps({'prompt': 'data-internal-profile-configured="false"' in root, 'profile': profile, 'files': listing['entries']}))
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
    assert outcome['prompt'] is True
    assert outcome['profile']['username'] == 'alice-new'
    assert any(item['name'] == 'keep.txt' for item in outcome['files'])
    assert (data_dir / 'users' / _storage_key('10.20.0.11') / 'workspace' / 'keep.txt').is_file()
    assert not legacy_workspace.exists()


@pytest.mark.parametrize('existing_hash', [False, True])
def test_internal_storage_migration_preserves_data_with_concurrent_callers(tmp_path, existing_hash):
    from concurrent.futures import ThreadPoolExecutor
    from codex_agent.services.multiuser import InternalUser, prepare_user_storage

    user = InternalUser('alice', 'member', '10.20.0.11', _storage_key('10.20.0.11'))
    legacy = tmp_path / user.username
    hashed = tmp_path / user.storage_key
    for subpath, content in [('workspace/keep.txt', 'legacy'), ('.agent_state/chat.json', 'chat'),
                             ('.agent_state/accounts/key.bin', 'credential')]:
        path = legacy / subpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    if existing_hash:
        (hashed / 'workspace').mkdir(parents=True)
        (hashed / 'workspace/keep.txt').write_text('current', encoding='utf-8')

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: prepare_user_storage(tmp_path, user), range(16)))

    assert (hashed / 'workspace/keep.txt').read_text(encoding='utf-8') == ('current' if existing_hash else 'legacy')
    if existing_hash:
        assert (legacy / 'workspace/keep.txt').read_text(encoding='utf-8') == 'legacy'
    else:
        assert not legacy.exists()
        assert (hashed / '.agent_state/chat.json').read_text(encoding='utf-8') == 'chat'
        assert (hashed / '.agent_state/accounts/key.bin').read_text(encoding='utf-8') == 'credential'


def test_internal_usage_scheduler_migrates_before_reading_accounts(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from codex_agent.services import codex_chat
    from codex_agent.services.multiuser import get_active_user

    legacy = tmp_path / 'users/alice/workspace'
    legacy.mkdir(parents=True)
    (legacy / 'keep.txt').write_text('keep', encoding='utf-8')
    hashed = tmp_path / 'users' / _storage_key('10.20.0.11')
    monkeypatch.setattr(codex_chat, 'CODEX_INTERNAL_DATA_DIR', tmp_path)
    monkeypatch.setattr(codex_chat, 'load_ip_user_map', lambda _: {
        '10.20.0.11': {'username': 'alice', 'role': 'member'},
    })
    observed = []
    def read_accounts():
        assert (hashed / 'workspace/keep.txt').read_text(encoding='utf-8') == 'keep'
        assert not legacy.exists()
        observed.append(get_active_user().username)
        return None
    def stop_after_cycle(_seconds):
        raise StopIteration
    monkeypatch.setattr(codex_chat, 'get_active_account_id', read_accounts)
    monkeypatch.setattr(codex_chat, 'time', SimpleNamespace(sleep=stop_after_cycle))

    previous = get_active_user()
    with pytest.raises(StopIteration):
        codex_chat._internal_usage_snapshot_worker_loop()
    assert observed == ['alice']
    assert get_active_user() is previous


def test_internal_api_keys_rotate_per_request_and_never_fall_back_to_user_keys(tmp_path):
    data_dir = tmp_path / 'internal-state'
    map_path = data_dir / 'user_map.json'
    map_path.parent.mkdir(parents=True)
    map_path.write_text(json.dumps({'users': [
        {'ip': '10.20.0.11', 'username': 'admin', 'role': 'admin'},
        {'ip': '10.20.0.12', 'username': 'member', 'role': 'member'},
    ]}), encoding='utf-8')
    script = r'''
import json
from codex_agent.services import company_credentials
from codex_agent.services.multiuser import InternalUser, activate_user, deactivate_user, storage_key_for_ip
company_credentials.sys.platform = 'win32'
company_credentials._protect_windows = lambda value: b'P' + value
company_credentials._unprotect_windows = lambda value: value[1:]
admin_ip, member_ip = '10.20.0.11', '10.20.0.12'
admin = InternalUser('admin', 'admin', admin_ip, storage_key_for_ip(admin_ip))
member = InternalUser('member', 'member', member_ip, storage_key_for_ip(member_ip))
token = activate_user(admin)
try:
    result = company_credentials.update_internal_api_key_allocation({
        'keys': [
            {'label': 'team-a', 'api_key': 'central-secret-a'},
            {'label': 'team-b', 'api_key': 'central-secret-b'},
        ],
    })
finally:
    deactivate_user(token)
token = activate_user(member)
try:
    envs = [{}, {}, {}]
    applied = [company_credentials.apply_company_api_key(env) for env in envs]
    metadata = company_credentials.get_internal_api_key_allocation()
finally:
    deactivate_user(token)
print(json.dumps({'applied': applied, 'secrets': [env['DTGPT_API_KEY'] for env in envs], 'ids': [env['CODEX_WORKBENCH_INTERNAL_API_KEY_ID'] for env in envs], 'labels': [env['CODEX_WORKBENCH_INTERNAL_API_KEY_LABEL'] for env in envs], 'keys': metadata['keys']}))
'''
    env = os.environ.copy()
    env.update({
        'CODEX_WORKBENCH_MODE': 'internal-multiuser', 'CODEX_INTERNAL_DATA_DIR': str(data_dir),
        'CODEX_INTERNAL_USER_MAP_PATH': str(map_path), 'DTGPT_API_KEY': 'environment-must-not-bypass',
    })
    result = subprocess.run([sys.executable, '-c', script], cwd=PROJECT_ROOT, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    assert outcome['applied'] == [True, True, True]
    assert outcome['secrets'] == ['central-secret-a', 'central-secret-b', 'central-secret-a']
    assert outcome['ids'][0] == outcome['ids'][2] != outcome['ids'][1]
    assert outcome['labels'] == ['team-a', 'team-b', 'team-a']
    assert [item['selection_count'] for item in outcome['keys']] == [2, 1]
    assert [item['today_selection_count'] for item in outcome['keys']] == [2, 1]
    assert all('…' in item['secret_preview'] for item in outcome['keys'])
    assert 'central-secret' not in json.dumps({'keys': outcome['keys']})


def test_internal_api_key_pool_reports_token_usage_per_key(tmp_path):
    data_dir = tmp_path / 'internal-state'
    script = r'''
import json
from codex_agent.services import company_credentials
company_credentials.sys.platform = 'win32'
company_credentials._protect_windows = lambda value: b'P' + value
company_credentials._unprotect_windows = lambda value: value[1:]
created = company_credentials.update_internal_api_key_allocation({
    'keys': [{'label': 'team-a', 'api_key': 'central-secret-a'}],
})
key_id = created['keys'][0]['id']
first = company_credentials.record_internal_api_key_token_usage(key_id, {
    'input_tokens': 12, 'cached_input_tokens': 3, 'output_tokens': 8,
    'reasoning_output_tokens': 2, 'total_tokens': 20,
}, event_id='stream:one')
duplicate = company_credentials.record_internal_api_key_token_usage(key_id, {
    'total_tokens': 20,
}, event_id='stream:one')
second = company_credentials.record_internal_api_key_token_usage(key_id, {
    'input_tokens': 5, 'output_tokens': 6, 'total_tokens': 11,
}, event_id='stream:two')
key = company_credentials.get_internal_api_key_allocation()['keys'][0]
print(json.dumps({'first': first, 'duplicate': duplicate, 'second': second, 'key': key}))
'''
    env = os.environ.copy()
    env.update({
        'CODEX_WORKBENCH_MODE': 'internal-multiuser',
        'CODEX_INTERNAL_DATA_DIR': str(data_dir),
    })
    result = subprocess.run([sys.executable, '-c', script], cwd=PROJECT_ROOT, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    assert outcome['first'] is True
    assert outcome['duplicate'] is False
    assert outcome['second'] is True
    assert outcome['key']['token_usage'] == {
        'input_tokens': 17, 'cached_input_tokens': 3, 'output_tokens': 14,
        'reasoning_output_tokens': 2, 'total_tokens': 31,
    }
    assert outcome['key']['today_token_usage'] == outcome['key']['token_usage']
