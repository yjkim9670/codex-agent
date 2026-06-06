from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent import codex_app
from codex_agent import config as codex_config
from codex_agent import state
from codex_agent.blueprints import codex_chat as codex_chat_blueprint
from codex_agent.services import codex_chat

CHAT_CRYPTO_INFO = b'codex-workbench-chat-prompt-v1'


def _write_test_models_cache(codex_home, slug='gpt-5.5'):
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / 'models_cache.json').write_text(json.dumps({
        'models': [
            {
                'slug': slug,
                'display_name': slug,
                'visibility': 'list',
                'default_reasoning_level': 'xhigh',
                'supported_reasoning_levels': [
                    {'effort': 'low'},
                    {'effort': 'xhigh'},
                ],
            },
            {
                'slug': 'hidden-model',
                'visibility': 'hidden',
            },
        ],
    }), encoding='utf-8')


@pytest.fixture(autouse=True)
def _reset_stream_state():
    with state.codex_streams_lock:
        state.codex_streams.clear()
    yield
    with state.codex_streams_lock:
        state.codex_streams.clear()


@pytest.fixture
def isolated_codex_workspace(tmp_path, monkeypatch):
    store_path = tmp_path / 'codex_chat_sessions.json'
    token_usage_path = tmp_path / 'codex_token_usage.json'
    account_token_usage_path = tmp_path / 'codex_account_token_usage.json'
    usage_history_path = tmp_path / 'codex_usage_history.json'
    workspace_dir = tmp_path / 'workspace'
    workspace_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(codex_chat, 'CODEX_CHAT_STORE_PATH', store_path)
    monkeypatch.setattr(codex_chat, 'CODEX_TOKEN_USAGE_PATH', token_usage_path)
    monkeypatch.setattr(codex_chat, 'CODEX_ACCOUNT_TOKEN_USAGE_PATH', account_token_usage_path)
    monkeypatch.setattr(codex_chat, 'CODEX_USAGE_HISTORY_PATH', usage_history_path)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', workspace_dir)
    monkeypatch.setattr(
        codex_chat,
        '_WORKSPACE_SCOPE_ID',
        hashlib.sha1(str(workspace_dir).encode('utf-8')).hexdigest()[:12],
    )
    monkeypatch.setattr(codex_chat, 'CODEX_SKIP_GIT_REPO_CHECK', True)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SANDBOX', 'workspace-write')
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_READ_ONLY_SANDBOX', 'read-only')
    monkeypatch.delenv('CODEX_CLI_BIN', raising=False)

    return {
        'store_path': store_path,
        'token_usage_path': token_usage_path,
        'usage_history_path': usage_history_path,
        'workspace_dir': workspace_dir,
    }


@pytest.fixture
def chat_route_client(isolated_codex_workspace, monkeypatch):
    monkeypatch.setattr(codex_app, 'ensure_usage_snapshot_background_worker', lambda: None)
    monkeypatch.setattr(codex_app, 'ensure_pending_queue_background_worker', lambda: None)
    monkeypatch.setattr(codex_chat_blueprint, 'CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS', True)
    app = codex_app.create_codex_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def _b64decode(text: str) -> bytes:
    return base64.b64decode(text.encode('ascii'), validate=True)


def test_model_catalog_reads_workbench_auth_home_cache(monkeypatch, tmp_path):
    stale_home = tmp_path / 'works' / '.codex'
    auth_home = tmp_path / 'home' / '.codex'
    _write_test_models_cache(auth_home)

    monkeypatch.setattr(codex_config, 'CODEX_HOME', stale_home)
    monkeypatch.setenv('HOME', str(tmp_path / 'shifted-home'))
    monkeypatch.setenv('CODEX_WORKBENCH_AUTH_HOME', str(auth_home))
    monkeypatch.delenv('CODEX_HOME', raising=False)
    monkeypatch.delenv('CODEX_MODEL_OPTIONS', raising=False)
    monkeypatch.delenv('CODEX_MODEL_CACHE_PATH', raising=False)

    assert codex_config.get_codex_model_options() == ['gpt-5.5']
    assert codex_config.get_codex_model_catalog_source() == {
        'type': 'models_cache',
        'models_cache_path': str(auth_home / 'models_cache.json'),
    }


def test_model_catalog_falls_back_to_login_home_cache(monkeypatch, tmp_path):
    stale_home = tmp_path / 'works' / '.codex'
    login_home = tmp_path / 'login' / '.codex'
    _write_test_models_cache(login_home)

    monkeypatch.setattr(codex_config, 'CODEX_HOME', stale_home)
    monkeypatch.setattr(codex_config, '_get_login_codex_home', lambda: login_home)
    monkeypatch.setenv('HOME', str(tmp_path / 'shifted-home'))
    monkeypatch.delenv('CODEX_HOME', raising=False)
    monkeypatch.delenv('CODEX_WORKBENCH_AUTH_HOME', raising=False)
    monkeypatch.delenv('CODEX_MODEL_OPTIONS', raising=False)
    monkeypatch.delenv('CODEX_MODEL_CACHE_PATH', raising=False)

    assert codex_config.get_codex_model_options() == ['gpt-5.5']


def _open_test_chat_crypto_session(client):
    client_private = ec.generate_private_key(ec.SECP256R1())
    client_public_key = client_private.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    response = client.post(
        '/api/codex/chat/crypto-session',
        json={'client_public_key': _b64encode(client_public_key)},
    )
    assert response.status_code == 200
    handshake = response.get_json()
    server_public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(),
        _b64decode(handshake['server_public_key']),
    )
    shared_secret = client_private.exchange(ec.ECDH(), server_public)
    key_material = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=_b64decode(handshake['salt']),
        info=CHAT_CRYPTO_INFO,
    ).derive(shared_secret)
    return {
        'id': handshake['crypto_session_id'],
        'request_key': key_material[:32],
        'response_key': key_material[32:],
    }


def _encrypt_test_chat_payload(session, payload):
    iv = os.urandom(12)
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    ciphertext = AESGCM(session['request_key']).encrypt(
        iv,
        raw,
        session['id'].encode('ascii'),
    )
    return {
        'encrypted': True,
        'crypto_session_id': session['id'],
        'iv': _b64encode(iv),
        'ciphertext': _b64encode(ciphertext),
    }


def _decrypt_test_chat_payload(session, envelope):
    assert envelope['encrypted'] is True
    raw = AESGCM(session['response_key']).decrypt(
        _b64decode(envelope['iv']),
        _b64decode(envelope['ciphertext']),
        session['id'].encode('ascii'),
    )
    return json.loads(raw.decode('utf-8'))


def _build_stream_state(stream_id, session_id, started_at, output_path):
    return {
        'id': stream_id,
        'session_id': session_id,
        'output': '',
        'error': '',
        'done': False,
        'saved': False,
        'exit_code': None,
        'cancelled': False,
        'process': None,
        'started_at': started_at,
        'last_output_at': started_at,
        'process_exited_at': None,
        'completed_at': None,
        'saved_at': None,
        'finalize_reason': None,
        'output_path': str(output_path),
        'output_last_message': '',
        'token_usage': {
            'input_tokens': 0,
            'cached_input_tokens': 0,
            'output_tokens': 0,
            'reasoning_output_tokens': 0,
            'total_tokens': 0,
        },
        'json_output': True,
        'codex_error_seen': False,
        'mcp_tool_call_cancel_error_seen': False,
        'output_length': 0,
        'error_length': 0,
        'created_at': started_at,
        'updated_at': started_at,
    }


def test_append_message_preserves_created_at(isolated_codex_workspace):
    session = codex_chat.create_session('append-message-created-at')

    created_at = '2026-03-19T10:20:30+09:00'
    message = codex_chat.append_message(
        session['id'],
        'assistant',
        'hello',
        created_at=created_at,
    )

    assert message is not None
    assert message['created_at'] == created_at


def test_delete_session_message_removes_message_from_context(isolated_codex_workspace):
    session = codex_chat.create_session('delete-message')
    first = codex_chat.append_message(session['id'], 'user', 'remove me')
    second = codex_chat.append_message(session['id'], 'assistant', 'keep me')

    updated = codex_chat.delete_session_message(session['id'], first['id'])

    assert updated is not None
    assert updated['message_count'] == 1
    assert [message['id'] for message in updated['messages']] == [second['id']]
    assert updated['messages'][0]['content'] == 'keep me'

    reloaded = codex_chat.get_session(session['id'])
    assert reloaded['message_count'] == 1
    assert reloaded['messages'][0]['id'] == second['id']


def test_branch_session_from_message_copies_history_through_target(isolated_codex_workspace):
    session = codex_chat.create_session('source-session')
    first = codex_chat.append_message(session['id'], 'user', 'first prompt')
    second = codex_chat.append_message(session['id'], 'assistant', 'first answer')
    third = codex_chat.append_message(session['id'], 'user', 'later prompt')

    branched = codex_chat.branch_session_from_message(session['id'], second['id'])

    assert branched is not None
    assert branched['id'] != session['id']
    assert branched['parent_session_id'] == session['id']
    assert branched['branch_source_message_id'] == second['id']
    assert branched['message_count'] == 2
    assert [message['content'] for message in branched['messages']] == ['first prompt', 'first answer']
    assert branched['messages'][0]['id'] != first['id']
    assert branched['messages'][1]['id'] != second['id']
    assert branched['messages'][0]['branched_from_message_id'] == first['id']
    assert branched['messages'][1]['branched_from_message_id'] == second['id']

    source = codex_chat.get_session(session['id'])
    assert source['message_count'] == 3
    assert source['messages'][-1]['id'] == third['id']


def test_merge_message_lists_does_not_wrap_message_payload():
    existing = [{
        'id': 'message-1',
        'role': 'assistant',
        'content': 'hello',
        'created_at': '2026-04-16T10:00:00+09:00',
    }]
    incoming = [{
        'id': 'message-1',
        'role': 'assistant',
        'content': 'hello',
        'created_at': '2026-04-16T10:00:00+09:00',
    }]

    merged = codex_chat._merge_message_lists(existing, incoming)

    assert len(merged) == 1
    assert merged[0]['id'] == 'message-1'
    assert merged[0]['content'] == 'hello'
    assert 'sort_key' not in merged[0]
    assert not isinstance(merged[0].get('message'), dict)


def test_load_session_payload_unwraps_nested_message_wrapper(isolated_codex_workspace):
    store_path = isolated_codex_workspace['store_path']

    base_message = {
        'id': 'assistant-1',
        'role': 'assistant',
        'content': 'final answer',
        'created_at': '2026-04-16T10:00:00+09:00',
    }
    nested = dict(base_message)
    for idx in range(40):
        nested = {
            'message': nested,
            'sort_key': ['2026-04-16T10:00:00+09:00', 0, idx],
            'id': base_message['id'],
            'role': base_message['role'],
            'content': base_message['content'],
            'created_at': base_message['created_at'],
        }

    payload = {
        'sessions': [{
            'id': 'session-1',
            'title': 'nested-message',
            'created_at': '2026-04-16T10:00:00+09:00',
            'updated_at': '2026-04-16T10:00:00+09:00',
            'messages': [nested],
            'pending_queue': [],
        }]
    }
    store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    loaded = codex_chat._load_session_store_payload_from_path(store_path)

    assert len(loaded['sessions']) == 1
    messages = loaded['sessions'][0]['messages']
    assert len(messages) == 1
    assert messages[0]['id'] == 'assistant-1'
    assert messages[0]['content'] == 'final answer'
    assert 'sort_key' not in messages[0]
    assert not isinstance(messages[0].get('message'), dict)


def test_candidate_paths_skip_legacy_when_primary_exists(monkeypatch, tmp_path):
    primary = tmp_path / 'primary' / 'codex_chat_sessions.json'
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_text('{"sessions": []}', encoding='utf-8')
    legacy = tmp_path / 'legacy' / 'codex_chat_sessions.json'
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{"sessions": []}', encoding='utf-8')

    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(codex_chat, 'CODEX_ENABLE_LEGACY_STATE_IMPORT', False)

    candidates = codex_chat._iter_codex_state_candidate_paths(primary, legacy)

    assert candidates == [primary]


def test_get_session_storage_summary_reports_work_detail_usage(isolated_codex_workspace):
    session = codex_chat.create_session('storage-summary')
    codex_chat.append_message(
        session['id'],
        'assistant',
        'hello',
        metadata={'work_details': 'line-1\nline-2'},
    )

    summary = codex_chat.get_session_storage_summary()

    assert summary['path'].endswith('codex_chat_sessions.json')
    assert summary['session_count'] == 1
    assert summary['message_count'] == 1
    assert summary['work_details_count'] == 1
    assert summary['work_details_bytes'] == len('line-1\nline-2'.encode('utf-8'))
    assert summary['total_bytes'] > 0


def test_token_usage_ledger_tracks_input_output_and_deduplicates(isolated_codex_workspace):
    session = codex_chat.create_session('token-ledger')
    session_id = session['id']

    first_saved = codex_chat.record_token_usage_for_message(
        session_id=session_id,
        message_id='msg-001',
        token_usage={
            'input_tokens': 120,
            'cached_input_tokens': 80,
            'output_tokens': 30,
        },
        source='unit_test',
    )
    second_saved = codex_chat.record_token_usage_for_message(
        session_id=session_id,
        message_id='msg-001',
        token_usage={
            'input_tokens': 120,
            'cached_input_tokens': 80,
            'output_tokens': 30,
        },
        source='unit_test',
    )

    assert first_saved is True
    assert second_saved is False

    summary = codex_chat.get_token_usage_summary(
        recent_days=7,
        ledger_path=isolated_codex_workspace['token_usage_path'],
    )
    assert summary['path'].endswith('codex_token_usage.json')
    assert summary['all_time']['input_tokens'] == 120
    assert summary['all_time']['cached_input_tokens'] == 80
    assert summary['all_time']['output_tokens'] == 30
    assert summary['all_time']['total_tokens'] == 150
    assert summary['all_time']['requests'] == 1
    assert summary['today']['input_tokens'] == 120
    assert summary['today']['output_tokens'] == 30
    assert isolated_codex_workspace['token_usage_path'].exists()


def test_usage_history_keeps_retention_window_and_reports_hourly_averages(isolated_codex_workspace):
    history_path = isolated_codex_workspace['usage_history_path']
    start = datetime(2026, 4, 1, 0, 0, tzinfo=codex_chat.KST)
    expected_hours = codex_chat._USAGE_HISTORY_MAX_ITEMS
    expected_days = codex_chat._USAGE_HISTORY_RETENTION_DAYS

    workspace_total = 0
    items = []
    for hour_index in range(expected_hours + 48):
        if hour_index > 0:
            workspace_total += 120
        bucket_start = codex_chat.normalize_timestamp(start + timedelta(hours=hour_index))
        items.append({
            'bucket_start': bucket_start,
            'recorded_at': bucket_start,
            'workspace_scope_id': codex_chat._WORKSPACE_SCOPE_ID,
            'workspace_path': str(isolated_codex_workspace['workspace_dir']),
            'token_workspace_total': workspace_total,
            'token_workspace_input': workspace_total,
            'token_workspace_cached_input': 0,
            'token_workspace_output': 0,
            'token_workspace_reasoning_output': 0,
            'token_workspace_requests': hour_index,
            'token_account_total': 0,
            'token_account_input': 0,
            'token_account_cached_input': 0,
            'token_account_output': 0,
            'token_account_reasoning_output': 0,
            'token_account_requests': 0,
            'five_hour_used_percent': float(hour_index % 100),
            'weekly_used_percent': round((hour_index % 168) / 2, 2),
        })

    codex_chat._save_usage_history_ledger({
        'version': codex_chat._USAGE_HISTORY_VERSION,
        'updated_at': codex_chat.normalize_timestamp(start + timedelta(hours=(24 * 16) - 1)),
        'bucket_hours': codex_chat._USAGE_HISTORY_BUCKET_HOURS,
        'timezone': 'Asia/Seoul',
        'items': items,
    }, path=history_path)

    loaded = codex_chat._load_usage_history_ledger(path=history_path)
    assert len(loaded['items']) == expected_hours

    summary = codex_chat.get_usage_history_summary(hours=24 * 30)

    assert summary['requested_hours'] == expected_hours
    assert summary['retention_days'] == expected_days
    assert summary['retention_hours'] == expected_hours
    assert summary['count'] == expected_hours
    assert summary['token_delta_scope'] == 'workspace'
    assert summary['averages']['daily']['avg_tokens_per_hour'] == pytest.approx(120)
    assert summary['averages']['daily']['token_total'] == 120 * 24
    assert summary['averages']['daily']['sample_count'] == 24
    assert summary['averages']['weekly']['avg_tokens_per_hour'] == pytest.approx(120)
    assert summary['averages']['weekly']['token_total'] == 120 * (24 * 7)
    assert summary['averages']['weekly']['sample_count'] == 24 * 7


def test_extract_exec_json_summary_parses_usage_and_last_agent_text():
    payload = '\n'.join([
        json.dumps({'type': 'thread.started', 'thread_id': 'abc'}),
        json.dumps({
            'type': 'turn.completed',
            'usage': {
                'input_tokens': 222,
                'cached_input_tokens': 128,
                'output_tokens': 44
            }
        }),
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'agent_message', 'text': 'hello world'}
        })
    ])

    summary = codex_chat._extract_exec_json_summary(payload)

    assert summary['event_count'] == 3
    assert summary['last_text'] == 'hello world'
    assert summary['usage']['input_tokens'] == 222
    assert summary['usage']['cached_input_tokens'] == 128
    assert summary['usage']['output_tokens'] == 44
    assert summary['usage']['total_tokens'] == 266


def test_extract_exec_json_summary_ignores_completed_command_execution_as_fatal():
    payload = '\n'.join([
        json.dumps({
            'type': 'item.completed',
            'item': {
                'type': 'command_execution',
                'status': 'failed',
                'command': 'pytest -q',
                'exit_code': 1,
            },
        }),
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'agent_message', 'text': '테스트 실패 원인을 수정했습니다.'},
        }),
    ])

    summary = codex_chat._extract_exec_json_summary(payload)

    assert summary['event_count'] == 2
    assert summary['last_error'] == ''
    assert summary['last_text'] == '테스트 실패 원인을 수정했습니다.'


def test_extract_exec_json_summary_marks_text_before_command_as_progress_only():
    payload = '\n'.join([
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'agent_message', 'text': '파일을 만들겠습니다.'},
        }),
        json.dumps({
            'type': 'item.started',
            'item': {'type': 'command_execution', 'command': 'mkdir app'},
        }),
        json.dumps({
            'type': 'item.completed',
            'item': {
                'type': 'command_execution',
                'status': 'completed',
                'command': 'mkdir app',
                'exit_code': 0,
            },
        }),
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'agent_message', 'text': ''},
        }),
        json.dumps({'type': 'turn.completed'}),
    ])

    summary = codex_chat._extract_exec_json_summary(payload)

    assert summary['last_text'] == '파일을 만들겠습니다.'
    assert summary['last_text_invalidated_by_work_item'] is True
    assert summary['turn_completed_seen'] is True
    assert summary['missing_final_response_after_work_item'] is True


def test_extract_exec_json_summary_marks_turn_completed_without_final_after_command():
    payload = '\n'.join([
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'agent_message', 'text': '먼저 상태를 확인하겠습니다.'},
        }),
        json.dumps({
            'type': 'item.completed',
            'item': {
                'type': 'command_execution',
                'status': 'completed',
                'command': 'powershell.exe -Command "Get-ChildItem test"',
                'exit_code': 0,
            },
        }),
        json.dumps({'type': 'turn.completed'}),
    ])

    summary = codex_chat._extract_exec_json_summary(payload)

    assert summary['last_text'] == '먼저 상태를 확인하겠습니다.'
    assert summary['last_text_invalidated_by_work_item'] is True
    assert summary['turn_completed_seen'] is True
    assert summary['missing_final_response_after_work_item'] is True


def test_extract_exec_json_summary_ignores_completed_mcp_tool_call_as_fatal():
    payload = '\n'.join([
        json.dumps({
            'type': 'item.completed',
            'item': {
                'type': 'mcp_tool_call',
                'status': 'failed',
                'name': 'browser',
            },
        }),
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'agent_message', 'text': '검증 불가 사유를 정리했습니다.'},
        }),
    ])

    summary = codex_chat._extract_exec_json_summary(payload)

    assert summary['event_count'] == 2
    assert summary['last_error'] == ''
    assert summary['last_text'] == '검증 불가 사유를 정리했습니다.'


def test_extract_exec_json_summary_identifies_mcp_tool_call_cancel_error():
    payload = json.dumps({
        'type': 'error',
        'message': 'user cancelled MCP tool call',
    })

    summary = codex_chat._extract_exec_json_summary(payload)

    assert summary['last_error'] == 'user cancelled MCP tool call'
    assert summary['last_mcp_tool_call_cancel_error'] == 'user cancelled MCP tool call'


def test_extract_exec_json_summary_parses_response_item_and_task_complete():
    payload = '\n'.join([
        json.dumps({
            'type': 'response_item',
            'payload': {
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': '중간 응답'}],
            },
        }),
        json.dumps({
            'type': 'event_msg',
            'payload': {
                'type': 'token_count',
                'info': {
                    'last_token_usage': {
                        'input_tokens': 120,
                        'cached_input_tokens': 20,
                        'output_tokens': 30,
                    },
                },
            },
        }),
        json.dumps({
            'type': 'task_complete',
            'payload': {'last_agent_message': '최종 응답'},
        }),
    ])

    summary = codex_chat._extract_exec_json_summary(payload)

    assert summary['event_count'] == 3
    assert summary['last_text'] == '최종 응답'
    assert summary['usage']['input_tokens'] == 120
    assert summary['usage']['cached_input_tokens'] == 20
    assert summary['usage']['output_tokens'] == 30
    assert summary['usage']['total_tokens'] == 150


def test_extract_exec_json_summary_records_app_server_event_lag():
    payload = '\n'.join([
        'in-process app-server event stream lagged; dropped 519 events',
        json.dumps({
            'type': 'response_item',
            'payload': {
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': '진행 중'}],
            },
        }),
    ])

    summary = codex_chat._extract_exec_json_summary(payload)

    assert summary['event_stream_lagged'] is True
    assert summary['dropped_event_count'] == 519
    assert summary['event_count'] == 1
    assert summary['last_text'] == '진행 중'


def test_execute_codex_prompt_uses_json_response_when_output_file_missing(monkeypatch, isolated_codex_workspace):
    stdout_payload = '\n'.join([
        json.dumps({
            'type': 'response_item',
            'payload': {
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': 'sync final response'}],
                'phase': 'final_answer',
            },
        }),
        json.dumps({
            'type': 'event_msg',
            'payload': {
                'type': 'token_count',
                'info': {
                    'total_token_usage': {
                        'input_tokens': 100,
                        'cached_input_tokens': 40,
                        'output_tokens': 20,
                    },
                },
            },
        }),
    ])

    captured = {}

    def _fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        captured['input'] = kwargs.get('input')
        captured['encoding'] = kwargs.get('encoding')
        captured['errors'] = kwargs.get('errors')
        return subprocess.CompletedProcess(cmd, 0, stdout_payload, '')

    monkeypatch.setattr(codex_chat.subprocess, 'run', _fake_run)

    output, error, token_usage, timing = codex_chat.execute_codex_prompt('sync prompt')

    assert error is None
    assert output == 'sync final response'
    assert isinstance(timing, dict)
    assert token_usage['input_tokens'] == 100
    assert token_usage['cached_input_tokens'] == 40
    assert token_usage['output_tokens'] == 20
    assert token_usage['total_tokens'] == 120
    assert captured['cmd'][-2:] == ['--', '-']
    assert captured['input'] == 'sync prompt'
    assert captured['encoding'] == 'utf-8'
    assert captured['errors'] == 'replace'
    assert 'Codex exec input:' in timing.get('work_details', '')
    assert 'prompt sent to stdin:' in timing.get('work_details', '')
    assert 'prompt_encoding: utf-8' in timing.get('work_details', '')
    assert 'sync prompt' in timing.get('work_details', '')


def test_execute_codex_prompt_does_not_surface_raw_json_events_as_response(
        monkeypatch,
        isolated_codex_workspace):
    stdout_payload = json.dumps({
        'type': 'item.completed',
        'item': {
            'type': 'command_execution',
            'status': 'failed',
            'command': 'pytest -q',
            'exit_code': 1,
        },
    })

    def _fake_run(cmd, **kwargs):
        del cmd
        del kwargs
        return subprocess.CompletedProcess([], 0, stdout_payload, '')

    monkeypatch.setattr(codex_chat.subprocess, 'run', _fake_run)

    output, error, token_usage, timing = codex_chat.execute_codex_prompt('sync prompt')

    assert error is None
    assert output == 'Codex completed without a final response.'
    assert 'item.completed' not in output
    assert token_usage is None
    assert isinstance(timing, dict)


def test_execute_codex_prompt_preserves_output_when_mcp_cancel_exit_fails(
        monkeypatch,
        isolated_codex_workspace):
    stdout_payload = '\n'.join([
        json.dumps({
            'type': 'task_complete',
            'payload': {'last_agent_message': 'sync work summary'},
        }),
        json.dumps({
            'type': 'error',
            'message': 'user canceled MCP tool call',
        }),
    ])

    def _fake_run(cmd, **kwargs):
        del kwargs
        return subprocess.CompletedProcess(cmd, 1, stdout_payload, '')

    monkeypatch.setattr(codex_chat.subprocess, 'run', _fake_run)

    output, error, token_usage, timing = codex_chat.execute_codex_prompt('sync prompt')

    assert output is None
    assert 'sync work summary' in error
    assert 'user canceled MCP tool call' in error
    assert token_usage is None
    assert isinstance(timing, dict)


def test_build_codex_command_uses_workspace_write_sandbox(isolated_codex_workspace):
    cmd = codex_chat._build_codex_command('sync prompt')

    assert cmd[:8] == [
        'codex',
        '--ask-for-approval',
        'never',
        'exec',
        '--sandbox',
        'workspace-write',
        '--color',
        'never',
    ]
    assert '--full-auto' not in cmd


def test_build_codex_command_supports_standard_sandbox_override(isolated_codex_workspace, monkeypatch):
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SANDBOX', 'danger-full-access')

    cmd = codex_chat._build_codex_command('sync prompt')

    assert cmd[cmd.index('--sandbox') + 1] == 'danger-full-access'
    assert '--full-auto' not in cmd


def test_build_codex_command_supports_read_only_output_schema(isolated_codex_workspace, tmp_path):
    schema_path = tmp_path / 'report.schema.json'

    cmd = codex_chat._build_codex_command(
        'report prompt',
        output_schema_path=schema_path,
        question_only=True,
    )

    assert cmd[:10] == [
        'codex',
        '--ask-for-approval',
        'never',
        'exec',
        '--sandbox',
        'read-only',
        '--ephemeral',
        '--color',
        'never',
        '--skip-git-repo-check',
    ]
    assert '--full-auto' not in cmd
    assert cmd[cmd.index('--output-schema') + 1] == str(schema_path)


def test_build_codex_command_supports_read_only_sandbox_override(isolated_codex_workspace, tmp_path, monkeypatch):
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_READ_ONLY_SANDBOX', 'danger-full-access')
    schema_path = tmp_path / 'report.schema.json'

    cmd = codex_chat._build_codex_command(
        'report prompt',
        output_schema_path=schema_path,
        question_only=True,
    )

    assert cmd[cmd.index('--sandbox') + 1] == 'danger-full-access'
    assert '--ephemeral' in cmd
    assert cmd[cmd.index('--output-schema') + 1] == str(schema_path)


def test_build_codex_command_supports_company_cli_routing(isolated_codex_workspace, monkeypatch):
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_PROFILE', 'dtgpt_linux')
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_MODEL_PROVIDER', 'dtgpt_linux')
    monkeypatch.setattr(codex_chat, 'get_settings', lambda: {
        'model': None,
        'reasoning_effort': None,
        'plan_mode_model': None,
        'plan_mode_reasoning_effort': None,
        'app_server_pilot_enabled': False,
    })

    cmd = codex_chat._build_codex_command('sync prompt')

    assert cmd[:10] == [
        'codex',
        '--ask-for-approval',
        'never',
        '--profile',
        'dtgpt_linux',
        'exec',
        '--sandbox',
        'workspace-write',
        '--color',
        'never',
    ]
    provider_index = cmd.index('model_provider="dtgpt_linux"')
    assert cmd[provider_index - 1] == '--config'


def test_company_runner_restart_policy_reports_reloader_enabled():
    job_config = {
        'commands': [
            'powershell.exe -ExecutionPolicy Bypass -File .\\run_codex_chat_server_company.ps1'
        ],
    }

    assert codex_chat_blueprint._is_codex_chat_job_config(job_config) is True
    assert codex_chat_blueprint._resolve_codex_use_reloader(job_config) is True


def test_restart_policy_reports_reload_flag_enabled():
    job_config = {'commands': ['python run_codex_chat_server.py --reload']}

    assert codex_chat_blueprint._resolve_codex_use_reloader(job_config) is True


def test_codex_exec_input_details_include_policy_values(isolated_codex_workspace):
    details = codex_chat._build_codex_exec_input_details(
        [
            'codex',
            '--ask-for-approval',
            'never',
            '--profile',
            'dtgpt_oa',
            'exec',
            '--sandbox',
            'danger-full-access',
            '--color',
            'never',
            '--',
            '-',
        ],
        'hello',
        execution_cwd='/tmp/workspace',
        exec_env={'CODEX_HOME': '/tmp/codex-home'},
    )

    formatted = codex_chat._format_codex_exec_input_details(details)

    assert 'approval_policy: never' in formatted
    assert 'sandbox: danger-full-access' in formatted
    assert 'profile: dtgpt_oa' in formatted
    assert 'CODEX_HOME: /tmp/codex-home' in formatted


def test_codex_exec_input_details_include_host_shell_on_windows(monkeypatch, isolated_codex_workspace):
    monkeypatch.setattr(codex_chat.sys, 'platform', 'win32')

    details = codex_chat._build_codex_exec_input_details(
        ['codex', 'exec', '--sandbox', 'danger-full-access', '--', '-'],
        'hello',
    )
    formatted = codex_chat._format_codex_exec_input_details(details)

    assert details['host_platform'] == 'win32'
    assert details['shell_family'] == 'powershell'
    assert 'host_platform: win32' in formatted
    assert 'shell_family: powershell' in formatted


def test_build_codex_command_uses_configured_cli_bin(isolated_codex_workspace, monkeypatch):
    monkeypatch.setenv('CODEX_CLI_BIN', '/opt/codex/bin/codex')

    cmd = codex_chat._build_codex_command('sync prompt')

    assert cmd[0] == '/opt/codex/bin/codex'


def test_build_codex_command_prefers_windows_cmd_launcher(isolated_codex_workspace, monkeypatch):
    monkeypatch.delenv('CODEX_CLI_BIN', raising=False)
    monkeypatch.setattr(codex_chat.sys, 'platform', 'win32')
    monkeypatch.setattr(
        codex_chat.shutil,
        'which',
        lambda name: r'C:\offline_codex\npm-prefix\codex.cmd' if name == 'codex.cmd' else None,
    )

    cmd = codex_chat._build_codex_command('sync prompt')

    assert cmd[0] == r'C:\offline_codex\npm-prefix\codex.cmd'


def test_build_codex_command_uses_app_bundle_cli_fallback(isolated_codex_workspace, tmp_path, monkeypatch):
    bundle_bin = tmp_path / 'Codex.app' / 'Contents' / 'Resources' / 'codex'
    bundle_bin.parent.mkdir(parents=True)
    bundle_bin.write_text('#!/usr/bin/env bash\n', encoding='utf-8')
    bundle_bin.chmod(0o755)
    monkeypatch.delenv('CODEX_CLI_BIN', raising=False)
    monkeypatch.setattr(codex_chat.sys, 'platform', 'darwin')
    monkeypatch.setattr(codex_chat.shutil, 'which', lambda name: None)
    monkeypatch.setattr(codex_chat, '_codex_cli_file_candidates', lambda: (str(bundle_bin),))

    cmd = codex_chat._build_codex_command('sync prompt')

    assert cmd[0] == str(bundle_bin)


def test_build_codex_command_passes_fast_service_tier(isolated_codex_workspace, monkeypatch):
    monkeypatch.setattr(codex_chat, 'get_settings', lambda: {
        'model': None,
        'reasoning_effort': None,
        'plan_mode_model': None,
        'plan_mode_reasoning_effort': None,
        'service_tier': 'priority',
        'app_server_pilot_enabled': False,
    })

    cmd = codex_chat._build_codex_command('sync prompt')

    service_tier_index = cmd.index('service_tier="priority"')
    assert cmd[service_tier_index - 1] == '--config'


def test_structured_report_preset_formats_valid_payload():
    payload = {
        'title': 'Risk report',
        'summary': 'No critical risk.',
        'risk_level': 'low',
        'sections': [
            {'heading': 'Checks', 'bullets': ['Run unit tests']},
        ],
        'action_items': ['Review diff'],
        'findings': [],
        'report_markdown': '## Risk report\n\nNo critical risk.',
    }

    output, metadata = codex_chat._format_structured_report_output(
        json.dumps(payload),
        'pr_risk',
    )

    assert output == '## Risk report\n\nNo critical risk.'
    assert metadata['preset'] == 'pr_risk'
    assert metadata['schema_valid'] is True


def _assert_openai_strict_object_required(schema, path='schema'):
    if not isinstance(schema, dict):
        return

    properties = schema.get('properties')
    if isinstance(properties, dict):
        required = schema.get('required')
        assert isinstance(required, list), f'{path}.required must be an array'
        missing = sorted(set(properties) - set(required))
        extra = sorted(set(required) - set(properties))
        assert not missing, f'{path}.required is missing: {missing}'
        assert not extra, f'{path}.required has unknown fields: {extra}'
        assert schema.get('additionalProperties') is False, (
            f'{path}.additionalProperties must be false'
        )
        for key, child_schema in properties.items():
            _assert_openai_strict_object_required(child_schema, f'{path}.properties.{key}')

    items = schema.get('items')
    if isinstance(items, dict):
        _assert_openai_strict_object_required(items, f'{path}.items')

    for keyword in ('anyOf', 'oneOf', 'allOf'):
        children = schema.get(keyword)
        if isinstance(children, list):
            for index, child_schema in enumerate(children):
                _assert_openai_strict_object_required(child_schema, f'{path}.{keyword}[{index}]')


def test_structured_report_schemas_match_openai_strict_required_rules():
    for preset_id in ('pr_risk', 'test_plan', 'release_notes', 'codebase_explain'):
        preset = codex_chat.get_structured_report_preset(preset_id)
        assert preset is not None

        _assert_openai_strict_object_required(preset['schema'], f'{preset_id}.schema')


def test_structured_report_preset_validates_findings_contract():
    payload = {
        'title': 'Risk report',
        'summary': 'Needs one follow-up.',
        'risk_level': 'medium',
        'sections': [
            {'heading': 'Checks', 'bullets': ['Inspect report schema']},
        ],
        'action_items': ['Run structured report request'],
        'findings': [
            {
                'severity': 'info',
                'title': 'Schema check',
                'detail': 'All object properties are required.',
                'recommendation': '',
            },
        ],
        'report_markdown': '## Risk report\n\nNeeds one follow-up.',
    }

    output, metadata = codex_chat._format_structured_report_output(
        json.dumps(payload),
        'codebase_explain',
    )

    assert output == '## Risk report\n\nNeeds one follow-up.'
    assert metadata['schema_valid'] is True


def test_structured_report_preset_rejects_missing_findings():
    payload = {
        'title': 'Risk report',
        'summary': 'No critical risk.',
        'risk_level': 'low',
        'sections': [],
        'action_items': [],
        'report_markdown': 'No critical risk.',
    }

    output, metadata = codex_chat._format_structured_report_output(
        json.dumps(payload),
        'pr_risk',
    )

    assert metadata['schema_valid'] is False
    assert 'missing required field: findings' in output


def test_structured_report_preset_rejects_unexpected_fields():
    payload = {
        'title': 'Risk report',
        'summary': 'No critical risk.',
        'risk_level': 'low',
        'sections': [],
        'action_items': [],
        'findings': [],
        'report_markdown': 'No critical risk.',
        'extra': 'not allowed',
    }

    output, metadata = codex_chat._format_structured_report_output(
        json.dumps(payload),
        'pr_risk',
    )

    assert metadata['schema_valid'] is False
    assert 'unexpected field(s): extra' in output


def test_execution_policy_presets_keep_danger_access_hidden():
    presets = codex_chat.get_execution_policy_presets()

    assert any(item['sandbox'] == 'workspace-write' for item in presets)
    assert any(item['id'] == 'worktree_isolated' for item in presets)
    assert any(item['sandbox'] == 'read-only' and item['ephemeral'] for item in presets)
    assert all(item['sandbox'] != 'danger-full-access' for item in presets)


def test_self_protect_git_rw_rebinds_git_after_ro_parent(tmp_path, monkeypatch):
    repo_root = tmp_path / 'codex_workbench'
    git_dir = repo_root / '.git'
    git_dir.mkdir(parents=True)

    monkeypatch.setattr(codex_chat, 'REPO_ROOT', repo_root)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', tmp_path)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SELF_PROTECT', True)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SELF_PROTECT_GIT_RW', True)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_PROTECTED_PATHS', tuple())
    monkeypatch.setattr(
        codex_chat.shutil,
        'which',
        lambda name: '/usr/bin/bwrap' if name == 'bwrap' else None,
    )

    wrapped = codex_chat._wrap_codex_cli_command(['codex', 'exec'])
    ro_bind = ['--ro-bind-try', str(repo_root.resolve()), str(repo_root.resolve())]
    rw_bind = ['--bind-try', str(git_dir.resolve()), str(git_dir.resolve())]
    ro_index = next(
        idx for idx in range(len(wrapped) - 2) if wrapped[idx:idx + 3] == ro_bind
    )
    rw_index = next(
        idx for idx in range(len(wrapped) - 2) if wrapped[idx:idx + 3] == rw_bind
    )

    assert rw_index > ro_index


def test_self_protect_rebinds_runtime_paths_after_ro_parent(tmp_path, monkeypatch):
    repo_root = tmp_path / 'codex_workbench'
    queued_home = repo_root / 'workspace' / '.agent_state' / 'queued_codex_home'
    queued_home.mkdir(parents=True)
    (queued_home / 'cache').mkdir()
    (queued_home / 'state').mkdir()
    (queued_home / 'config').mkdir()
    (queued_home / 'tmp').mkdir()
    external_home = tmp_path / 'home'
    external_home.mkdir()

    monkeypatch.setattr(codex_chat, 'REPO_ROOT', repo_root)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', tmp_path)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SELF_PROTECT', True)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SELF_PROTECT_GIT_RW', False)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_PROTECTED_PATHS', tuple())
    monkeypatch.setattr(
        codex_chat.shutil,
        'which',
        lambda name: '/usr/bin/bwrap' if name == 'bwrap' else None,
    )

    wrapped = codex_chat._wrap_codex_cli_command(
        ['codex', 'exec'],
        env={
            'CODEX_HOME': str(queued_home),
            'HOME': str(external_home),
            'XDG_CACHE_HOME': str(queued_home / 'cache'),
            'XDG_STATE_HOME': str(queued_home / 'state'),
            'XDG_CONFIG_HOME': str(queued_home / 'config'),
            'TMPDIR': str(queued_home / 'tmp'),
        },
    )
    ro_bind = ['--ro-bind-try', str(repo_root.resolve()), str(repo_root.resolve())]
    queued_home_bind = ['--bind-try', str(queued_home.resolve()), str(queued_home.resolve())]
    cache_bind = [
        '--bind-try',
        str((queued_home / 'cache').resolve()),
        str((queued_home / 'cache').resolve()),
    ]
    home_bind = ['--bind-try', str(external_home.resolve()), str(external_home.resolve())]

    ro_index = next(
        idx for idx in range(len(wrapped) - 2) if wrapped[idx:idx + 3] == ro_bind
    )
    queued_home_index = next(
        idx for idx in range(len(wrapped) - 2) if wrapped[idx:idx + 3] == queued_home_bind
    )

    assert queued_home_index > ro_index
    assert any(wrapped[idx:idx + 3] == cache_bind for idx in range(len(wrapped) - 2))
    assert not any(wrapped[idx:idx + 3] == home_bind for idx in range(len(wrapped) - 2))


def test_self_protect_is_ignored_on_non_linux_without_bwrap(tmp_path, monkeypatch, caplog):
    repo_root = tmp_path / 'codex_workbench'
    repo_root.mkdir()

    monkeypatch.setattr(codex_chat, 'REPO_ROOT', repo_root)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', tmp_path)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SELF_PROTECT', True)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SELF_PROTECT_GIT_RW', False)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_PROTECTED_PATHS', tuple())
    monkeypatch.setattr(codex_chat, '_CODEX_CLI_SELF_PROTECT_UNAVAILABLE_WARNED', False)
    monkeypatch.setattr(codex_chat.sys, 'platform', 'darwin')
    monkeypatch.setattr(codex_chat.shutil, 'which', lambda name: None)

    wrapped = codex_chat._wrap_codex_cli_command(['codex', 'exec'])

    assert wrapped == ['codex', 'exec']
    assert 'CODEX_CLI_SELF_PROTECT=1 ignored on darwin' in caplog.text


def test_self_protect_requires_bwrap_on_linux(tmp_path, monkeypatch):
    repo_root = tmp_path / 'codex_workbench'
    repo_root.mkdir()

    monkeypatch.setattr(codex_chat, 'REPO_ROOT', repo_root)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', tmp_path)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SELF_PROTECT', True)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_SELF_PROTECT_GIT_RW', False)
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_PROTECTED_PATHS', tuple())
    monkeypatch.setattr(codex_chat.sys, 'platform', 'linux')
    monkeypatch.setattr(codex_chat.shutil, 'which', lambda name: None)

    with pytest.raises(RuntimeError, match='requires bubblewrap'):
        codex_chat._wrap_codex_cli_command(['codex', 'exec'])


def test_app_server_pilot_setting_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_chat, 'CODEX_SETTINGS_PATH', tmp_path / 'settings.json')
    monkeypatch.setattr(codex_chat, 'LEGACY_CODEX_SETTINGS_PATH', tmp_path / 'legacy_settings.json')
    monkeypatch.delenv('CODEX_APP_SERVER_PILOT_ENABLED', raising=False)

    assert codex_chat.get_settings()['app_server_pilot_enabled'] is False

    updated = codex_chat.update_settings(app_server_pilot_enabled=True)

    assert updated['app_server_pilot_enabled'] is True
    assert codex_chat.get_settings()['app_server_pilot_enabled'] is True

    disabled = codex_chat.update_settings(app_server_pilot_enabled=False)
    assert disabled['app_server_pilot_enabled'] is False


def test_service_tier_setting_round_trips(tmp_path, monkeypatch):
    settings_path = tmp_path / 'settings.json'
    monkeypatch.setattr(codex_chat, 'CODEX_SETTINGS_PATH', settings_path)
    monkeypatch.setattr(codex_chat, 'LEGACY_CODEX_SETTINGS_PATH', tmp_path / 'legacy_settings.json')

    updated = codex_chat.update_settings(service_tier='fast')

    assert updated['service_tier'] == 'priority'
    assert codex_chat.get_settings()['service_tier'] == 'priority'
    stored = json.loads(settings_path.read_text(encoding='utf-8'))
    assert stored['service_tier'] == 'priority'

    disabled = codex_chat.update_settings(service_tier='')

    assert disabled['service_tier'] is None


def test_cli_routing_settings_are_runtime_only(tmp_path, monkeypatch):
    settings_path = tmp_path / 'settings.json'
    monkeypatch.setattr(codex_chat, 'CODEX_SETTINGS_PATH', settings_path)
    monkeypatch.setattr(codex_chat, 'LEGACY_CODEX_SETTINGS_PATH', tmp_path / 'legacy_settings.json')
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_PROFILE', 'dtgpt_linux')
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_MODEL_PROVIDER', 'dtgpt_linux')

    updated = codex_chat.update_settings(model='DeepSeek-V4-Pro')

    assert updated['cli_profile'] == 'dtgpt_linux'
    assert updated['model_provider'] == 'dtgpt_linux'
    stored = json.loads(settings_path.read_text(encoding='utf-8'))
    assert 'cli_profile' not in stored
    assert 'model_provider' not in stored


def test_app_server_model_list_uses_allowlisted_json_rpc(monkeypatch, tmp_path):
    captured = {}

    class FakePopen:
        returncode = 0

        def __init__(self, command, **kwargs):
            captured['command'] = command
            captured['kwargs'] = kwargs

        def communicate(self, input=None, timeout=None):
            captured['input'] = input
            captured['timeout'] = timeout
            stdout = '\n'.join([
                json.dumps({'id': 1, 'result': {'protocolVersion': 'v2'}}),
                json.dumps({
                    'id': 2,
                    'result': {
                        'data': [
                            {
                                'id': 'gpt-5.4',
                                'model': 'gpt-5.4',
                                'defaultReasoningEffort': 'medium',
                            }
                        ],
                        'nextCursor': None,
                    },
                }),
            ])
            return stdout, ''

    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', tmp_path)
    monkeypatch.setattr(codex_chat, 'CODEX_STORAGE_DIR', tmp_path / 'state')
    monkeypatch.setattr(codex_chat, 'get_settings', lambda: {'app_server_pilot_enabled': True})
    monkeypatch.setattr(codex_chat, '_read_app_server_remote_control_running', lambda: False)
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', FakePopen)

    result = codex_chat.list_codex_app_server_models(limit=5)

    assert captured['command'] == ['codex', 'app-server']
    assert captured['kwargs']['env']['CODEX_HOME'] == str(tmp_path / 'state' / 'app_server_codex_home')
    assert '"method": "initialize"' in captured['input']
    assert '"method": "model/list"' in captured['input']
    assert result['transport'] == 'stdio'
    assert result['models'][0]['id'] == 'gpt-5.4'


def test_build_codex_app_server_env_uses_writable_home_without_linked_skills(monkeypatch, tmp_path):
    source_home = tmp_path / 'source-codex-home'
    source_home.mkdir()
    (source_home / 'auth.json').write_text('{"token": "test"}', encoding='utf-8')
    (source_home / 'skills').mkdir()
    storage_dir = tmp_path / 'state'

    monkeypatch.setenv('CODEX_HOME', str(source_home))
    monkeypatch.setenv('HOME', str(tmp_path / 'read-only-home'))
    monkeypatch.setattr(codex_chat, 'CODEX_STORAGE_DIR', storage_dir)

    env = codex_chat._build_codex_app_server_env()

    app_server_home = storage_dir / 'app_server_codex_home'
    assert env['CODEX_HOME'] == str(app_server_home)
    assert env['HOME'] == str(app_server_home)
    assert (app_server_home / 'auth.json').read_text(encoding='utf-8') == '{"token": "test"}'
    assert (app_server_home / 'skills').is_dir()
    assert not (app_server_home / 'skills').is_symlink()


def test_build_codex_child_env_strips_parent_runtime_logs(monkeypatch, tmp_path):
    explicit_home = tmp_path / 'explicit-codex-home'
    explicit_home.mkdir()
    default_home = tmp_path / 'default-codex-home'
    default_home.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('CODEX_HOME', str(explicit_home))
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(codex_chat, '_CODEX_HOME', default_home)
    monkeypatch.setenv('RUST_LOG', 'warn')
    monkeypatch.setenv('LOG_FORMAT', 'json')
    monkeypatch.setenv('CODEX_THREAD_ID', 'thread-from-parent')
    monkeypatch.setenv('CODEX_TURN_ID', 'turn-from-parent')
    monkeypatch.setenv('CODEX_APP_SERVER_PILOT_ENABLED', '1')
    monkeypatch.setenv('CODEX_TRACE_ID', 'trace-from-parent')

    env = codex_chat._build_codex_exec_env()

    assert env['CODEX_HOME'] == str(explicit_home)
    assert env[codex_chat._IMAGEGEN_WORKBENCH_OUTPUT_ENV]
    assert env[codex_chat._IMAGEGEN_WORKBENCH_TMP_ENV]
    for key in (
            'RUST_LOG',
            'LOG_FORMAT',
            'CODEX_THREAD_ID',
            'CODEX_TURN_ID',
            'CODEX_APP_SERVER_PILOT_ENABLED',
            'CODEX_TRACE_ID'):
        assert key not in env


def test_app_server_blocks_unallowlisted_methods(monkeypatch):
    monkeypatch.setattr(codex_chat, 'get_settings', lambda: {'app_server_pilot_enabled': True})

    with pytest.raises(codex_chat.CodexAppServerError) as exc_info:
        codex_chat.call_codex_app_server_method('thread/shellCommand', {})

    assert exc_info.value.error_code == 'app_server_method_not_allowed'


def test_app_server_thread_list_passes_pagination_filters(monkeypatch):
    captured = {}

    def fake_call(method, params):
        captured['method'] = method
        captured['params'] = params
        return {
            'result': {
                'data': [{'id': 'thr_123', 'preview': 'hello'}],
                'nextCursor': 'next-page',
            },
            'transport': 'stdio',
            'elapsed_ms': 12,
        }

    monkeypatch.setattr(codex_chat, 'call_codex_app_server_method', fake_call)

    result = codex_chat.list_codex_app_server_threads(
        limit=250,
        cursor='cursor-1',
        search_term='repo fix',
        cwd='/tmp/workspace',
        include_exec=True,
    )

    assert captured['method'] == 'thread/list'
    assert captured['params']['limit'] == 100
    assert captured['params']['cursor'] == 'cursor-1'
    assert captured['params']['searchTerm'] == 'repo fix'
    assert captured['params']['cwd'] == '/tmp/workspace'
    assert 'exec' in captured['params']['sourceKinds']
    assert result['threads'][0]['id'] == 'thr_123'
    assert result['next_cursor'] == 'next-page'


def test_app_server_thread_read_preserves_turns(monkeypatch):
    def fake_call(method, params):
        assert method == 'thread/read'
        assert params == {'threadId': 'thr_123', 'includeTurns': True}
        return {
            'result': {
                'thread': {'id': 'thr_123', 'title': 'Thread'},
                'turns': [{'id': 'turn_1'}],
                'nextCursor': 'turn-page-2',
            },
            'transport': 'stdio',
            'elapsed_ms': 7,
        }

    monkeypatch.setattr(codex_chat, 'call_codex_app_server_method', fake_call)

    result = codex_chat.read_codex_app_server_thread('thr_123', include_turns=True)

    assert result['thread']['id'] == 'thr_123'
    assert result['turns'] == [{'id': 'turn_1'}]
    assert result['next_cursor'] == 'turn-page-2'


def test_app_server_thread_turns_list_uses_allowlisted_method(monkeypatch):
    captured = {}

    def fake_call(method, params):
        captured['method'] = method
        captured['params'] = params
        return {
            'result': {
                'data': [{'id': 'turn_1'}],
                'nextCursor': None,
            },
            'transport': 'stdio',
            'elapsed_ms': 5,
        }

    monkeypatch.setattr(codex_chat, 'call_codex_app_server_method', fake_call)

    result = codex_chat.list_codex_app_server_thread_turns('thr_123', limit=10, cursor='c2')

    assert captured['method'] == 'thread/turns/list'
    assert captured['params'] == {'threadId': 'thr_123', 'limit': 10, 'cursor': 'c2'}
    assert result['turns'] == [{'id': 'turn_1'}]


def test_app_server_lifecycle_preview_does_not_allow_execution_methods():
    preview = codex_chat.build_codex_app_server_thread_lifecycle_preview('thr_123', 'rollback')

    assert preview['action'] == 'rollback'
    assert preview['method'] == 'thread/rollback'
    assert preview['preview_only'] is True
    assert preview['executable'] is False
    assert preview['params']['turnId'] == '<select-turn-id>'
    assert 'thread/rollback' not in codex_chat._APP_SERVER_ALLOWED_METHODS
    assert 'thread/compact' not in codex_chat._APP_SERVER_ALLOWED_METHODS


def test_subagent_cockpit_preview_formats_lanes_without_starting_jobs():
    preview = codex_chat.build_subagent_cockpit_preview('explore_three', 'Phase 4 구현')

    assert preview['preset']['id'] == 'explore_three'
    assert preview['auto_fan_out'] is False
    assert preview['execution_policy'] == 'read_only_ephemeral'
    assert len(preview['lanes']) == 3
    assert all('Phase 4 구현' in lane['prompt'] for lane in preview['lanes'])


def test_subagent_cockpit_run_starts_explicit_lane_subjobs(monkeypatch, isolated_codex_workspace):
    session = codex_chat.create_session('parent')
    calls = []

    def fake_start(parent_session_id, prompt, attachments=None):
        calls.append((parent_session_id, prompt, attachments))
        return {
            'ok': True,
            'child_session': {'id': f'child-{len(calls)}'},
            'stream_id': f'stream-{len(calls)}',
            'started_at': 123,
        }

    monkeypatch.setattr(codex_chat, 'start_codex_subjob_for_session', fake_start)

    result = codex_chat.start_subagent_cockpit_preset_for_session(
        session['id'],
        'review_tripwire',
        base_prompt='검증',
        attachments=[{'id': 'att-1'}],
    )

    assert result['ok'] is True
    assert result['requested_count'] == 3
    assert result['started_count'] == 3
    assert len(calls) == 3
    assert all(call[0] == session['id'] for call in calls)
    assert all(call[2] == [{'id': 'att-1'}] for call in calls)


def test_repo_skill_preview_and_create_are_workspace_scoped(isolated_codex_workspace):
    workspace_dir = isolated_codex_workspace['workspace_dir']

    preview = codex_chat.build_repo_skill_preview(
        'Review Helper',
        trigger='Use for reviews.',
        description='Review workflow.',
    )

    assert preview['slug'] == 'review-helper'
    assert preview['root'] == '.agents/skills/review-helper'
    assert any(item['path'].endswith('SKILL.md') for item in preview['files'])

    result = codex_chat.create_repo_skill_from_preview(
        'Review Helper',
        trigger='Use for reviews.',
        description='Review workflow.',
    )

    skill_path = workspace_dir / '.agents' / 'skills' / 'review-helper' / 'SKILL.md'
    assert result['ok'] is True
    assert skill_path.exists()
    assert 'Review workflow.' in skill_path.read_text(encoding='utf-8')

    with pytest.raises(codex_chat.CodexToolingError) as exc_info:
        codex_chat.create_repo_skill_from_preview('Review Helper')

    assert exc_info.value.error_code == 'skill_exists'


def test_project_safety_mcp_and_github_templates_save_only_preview_files(isolated_codex_workspace):
    workspace_dir = isolated_codex_workspace['workspace_dir']

    safety = codex_chat.save_codex_project_safety_template('hooks_preview')
    mcp = codex_chat.save_mcp_setup_preview()
    github = codex_chat.save_github_action_template_preview('pr_review')

    assert safety['path'] == '.codex/hooks.preview.json'
    assert mcp['path'] == '.codex/mcp.preview.toml'
    assert '.agents/github-action-templates/codex-pr-review.yml' in github['paths']
    assert (workspace_dir / '.codex' / 'hooks.preview.json').exists()
    assert (workspace_dir / '.codex' / 'mcp.preview.toml').exists()
    assert (workspace_dir / '.agents' / 'github-action-templates' / 'codex-pr-review.yml').exists()
    assert not (workspace_dir / '.codex' / 'hooks.json').exists()
    assert not (workspace_dir / '.github' / 'workflows' / 'codex-pr-review.yml').exists()


def test_project_preview_paths_fall_back_when_preferred_roots_are_unusable(isolated_codex_workspace):
    workspace_dir = isolated_codex_workspace['workspace_dir']
    (workspace_dir / '.codex').write_text('', encoding='utf-8')
    (workspace_dir / '.agents').mkdir()
    (workspace_dir / '.agents').chmod(0o555)

    try:
        skill = codex_chat.build_repo_skill_preview('Fallback Skill')
        safety = codex_chat.get_codex_project_safety_preview()
        mcp = codex_chat.get_mcp_setup_preview()
        github = codex_chat.get_github_action_template_preview('pr_review')
    finally:
        (workspace_dir / '.agents').chmod(0o755)

    assert skill['root'] == '.codex-workbench-previews/skills/fallback-skill'
    assert safety['templates'][0]['path'].startswith('.codex-workbench-previews/')
    assert mcp['path'] == '.codex-workbench-previews/codex/mcp.preview.toml'
    assert github['workflow_path'].startswith('.codex-workbench-previews/')


def test_parse_codex_features_list_output_handles_multi_word_stage():
    output = '\n'.join([
        'apply_patch_freeform                    under development  false',
        'apps                                    stable             true',
    ])

    parsed = codex_chat._parse_codex_features_list_output(output)

    assert parsed[0]['name'] == 'apply_patch_freeform'
    assert parsed[0]['stage'] == 'under development'
    assert parsed[0]['enabled'] is False
    assert parsed[1]['name'] == 'apps'
    assert parsed[1]['enabled'] is True


def _init_git_repo(repo_root):
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', '-C', str(repo_root), 'init'], check=True, capture_output=True, text=True)
    subprocess.run(['git', '-C', str(repo_root), 'config', 'user.email', 'test@example.com'], check=True)
    subprocess.run(['git', '-C', str(repo_root), 'config', 'user.name', 'Test User'], check=True)
    (repo_root / 'README.md').write_text('# test\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(repo_root), 'add', 'README.md'], check=True)
    subprocess.run(['git', '-C', str(repo_root), 'commit', '-m', 'initial'], check=True, capture_output=True, text=True)


def test_git_worktree_task_create_and_cleanup(tmp_path, monkeypatch):
    repo_root = tmp_path / 'repo'
    _init_git_repo(repo_root)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', repo_root)
    monkeypatch.setattr(codex_chat, 'CODEX_STORAGE_DIR', tmp_path / 'state')
    monkeypatch.setenv('CODEX_WORKTREE_ROOT', str(tmp_path / 'worktrees'))

    task = codex_chat.create_git_worktree_task('isolated change', session_id='session-1')

    task_path = Path(task['path'])
    assert task['id'].startswith('wt-')
    assert task['branch'].startswith('codex-workbench/')
    assert task_path.exists()
    assert (task_path / 'README.md').exists()
    assert task['dirty'] is False

    removed = codex_chat.cleanup_git_worktree_task(task['id'])

    assert removed['status'] == 'removed'
    assert not task_path.exists()


def test_git_worktree_cleanup_requires_force_when_dirty(tmp_path, monkeypatch):
    repo_root = tmp_path / 'repo'
    _init_git_repo(repo_root)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', repo_root)
    monkeypatch.setattr(codex_chat, 'CODEX_STORAGE_DIR', tmp_path / 'state')
    monkeypatch.setenv('CODEX_WORKTREE_ROOT', str(tmp_path / 'worktrees'))

    task = codex_chat.create_git_worktree_task('dirty worktree')
    task_path = Path(task['path'])
    (task_path / 'new-file.txt').write_text('dirty\n', encoding='utf-8')

    with pytest.raises(codex_chat.CodexWorktreeError) as exc_info:
        codex_chat.cleanup_git_worktree_task(task['id'])

    assert exc_info.value.error_code == 'worktree_dirty'
    forced = codex_chat.cleanup_git_worktree_task(task['id'], force=True)
    assert forced['status'] == 'removed'
    assert not task_path.exists()


def test_imagegen_overlay_points_to_workbench_managed_dirs(isolated_codex_workspace):
    workspace_dir = isolated_codex_workspace['workspace_dir']

    prompt = codex_chat.build_codex_prompt([], '$imagegen 테스트용 이미지를 만들어줘')

    assert '## Image Generation Workbench Overlay' in prompt
    assert 'CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR' in prompt
    assert 'CODEX_WORKBENCH_IMAGEGEN_TMP_DIR' in prompt
    assert str(workspace_dir / 'output' / 'imagegen') in prompt
    assert str(workspace_dir / 'tmp' / 'imagegen') in prompt


def test_build_codex_prompt_includes_powershell_rules_on_windows(monkeypatch):
    monkeypatch.setattr(codex_chat.sys, 'platform', 'win32')

    prompt = codex_chat.build_codex_prompt([], '폴더와 파일을 만들어줘')

    assert '## Execution Environment' in prompt
    assert 'Host OS: Windows (`sys.platform=win32`)' in prompt
    assert 'commands run in PowerShell' in prompt
    assert 'New-Item -ItemType Directory -Force' in prompt
    assert "Never emit compact invalid here-strings like `@'`n'@`" in prompt
    assert 'ParserError' in prompt


def test_build_codex_prompt_omits_powershell_rules_on_posix(monkeypatch):
    monkeypatch.setattr(codex_chat.sys, 'platform', 'darwin')

    prompt = codex_chat.build_codex_prompt([], '폴더와 파일을 만들어줘')

    assert '## Execution Environment' not in prompt
    assert 'commands run in PowerShell' not in prompt


def test_execute_codex_prompt_prepares_imagegen_dirs_and_env(monkeypatch, isolated_codex_workspace):
    workspace_dir = isolated_codex_workspace['workspace_dir']
    stdout_payload = json.dumps({
        'type': 'task_complete',
        'payload': {'last_agent_message': 'image done'},
    })
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured['env'] = kwargs.get('env') or {}
        return subprocess.CompletedProcess(cmd, 0, stdout_payload, '')

    monkeypatch.setattr(codex_chat.subprocess, 'run', _fake_run)

    output, error, token_usage, timing = codex_chat.execute_codex_prompt('$imagegen 테스트 이미지를 만들어줘')

    assert error is None
    assert output == 'image done'
    assert token_usage is None
    assert isinstance(timing, dict)
    assert (workspace_dir / 'output' / 'imagegen').is_dir()
    assert (workspace_dir / 'tmp' / 'imagegen').is_dir()
    assert captured['env']['CODEX_WORKBENCH_IMAGEGEN_OUTPUT_DIR'] == str(
        workspace_dir / 'output' / 'imagegen'
    )
    assert captured['env']['CODEX_WORKBENCH_IMAGEGEN_TMP_DIR'] == str(
        workspace_dir / 'tmp' / 'imagegen'
    )


def test_imagegen_stream_uses_extended_final_response_timeout(monkeypatch):
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_IMAGEGEN_FINAL_RESPONSE_TIMEOUT_SECONDS', 180)

    base_timeout = 15

    assert codex_chat._final_response_timeout_seconds_for_stream({}, base_timeout) == base_timeout
    assert codex_chat._final_response_timeout_seconds_for_stream(
        {'imagegen_workbench_requested': True},
        base_timeout,
    ) == 180


def test_copy_imagegen_outputs_for_requested_stream_uses_time_window_fallback_while_finalizing(
        isolated_codex_workspace,
        tmp_path):
    workspace_dir = isolated_codex_workspace['workspace_dir']
    fake_codex_home = tmp_path / 'codex_home'
    source_dir = fake_codex_home / 'generated_images' / 'detached-image-session'
    source_dir.mkdir(parents=True)
    source_path = source_dir / 'ig_delayed.png'
    source_path.write_bytes(b'fake png bytes')

    session = codex_chat.create_session('imagegen-copy-fallback')
    session_id = session['id']
    stream_id = 'stream-imagegen-copy-fallback'
    now = time.time()
    process_exited_at = now - 120

    stream = _build_stream_state(
        stream_id,
        session_id,
        started_at=now - 180,
        output_path=workspace_dir / 'stream-imagegen-copy-fallback.txt',
    )
    stream.update({
        'cli_started_at': now - 180,
        'process_exited_at': process_exited_at,
        'completed_at': process_exited_at,
        'codex_home': str(fake_codex_home),
        'imagegen_workbench_requested': True,
        'user_prompt': '$imagegen 네이버 뉴스 화면을 만들어줘',
    })

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = stream

    copied = codex_chat._copy_imagegen_workbench_outputs_for_stream(stream_id)

    assert len(copied) == 1
    copied_path = Path(copied[0])
    assert copied_path.is_file()
    assert copied_path.parent == workspace_dir / 'output' / 'imagegen'
    assert copied_path.read_bytes() == b'fake png bytes'


def test_build_work_details_keeps_key_parts_for_long_code_logs():
    code_lines = [f'line_{idx} = {idx}' for idx in range(140)]
    code_lines[0] = 'def important_entry():'
    code_lines[70] = 'class ImportantClass:'
    code_lines[-1] = 'return line_139'
    long_block = '\n'.join(code_lines)
    stdout_text = f"```python\n{long_block}\n```"

    details = codex_chat._build_work_details(stdout_text, '', '')

    assert details is not None
    assert 'CLI stdout:' in details
    assert 'important_entry' in details
    assert 'ImportantClass' in details
    assert 'key parts only' in details
    assert len(details) <= codex_chat._WORK_DETAILS_MAX_CHARS


def test_finalize_stream_uses_completed_at_metadata(monkeypatch, isolated_codex_workspace):
    session = codex_chat.create_session('finalize-metadata')
    session_id = session['id']

    stream_id = 'stream-finalize-metadata'
    with state.codex_streams_lock:
        stream = _build_stream_state(
            stream_id,
            session_id,
            started_at=100.0,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-finalize-metadata.txt',
        )
        stream['done'] = True
        stream['exit_code'] = 0
        stream['output'] = 'step 1\nstep 2'
        stream['output_last_message'] = 'assistant text'
        stream['output_length'] = len(stream['output'])
        stream['completed_at'] = 102.0
        stream['updated_at'] = 102.0
        stream['finalize_reason'] = 'process_exit'
        state.codex_streams[stream_id] = stream

    monkeypatch.setattr(codex_chat.time, 'time', lambda: 105.0)

    saved_message = codex_chat.finalize_codex_stream(stream_id)

    assert saved_message is not None
    assert saved_message['role'] == 'assistant'
    assert saved_message['content'] == 'assistant text'
    assert saved_message['duration_ms'] == 5000
    assert saved_message['finalize_reason'] == 'process_exit'
    assert saved_message['finalize_lag_ms'] == 3000
    assert 'CLI stdout:' in saved_message.get('work_details', '')
    assert 'step 1' in saved_message.get('work_details', '')
    assert saved_message['completed_at'] == saved_message['created_at']


def test_finalize_stream_suppresses_stale_output_file_after_work_without_final(
        monkeypatch,
        isolated_codex_workspace):
    session = codex_chat.create_session('finalize-missing-final')
    session_id = session['id']

    stream_id = 'stream-finalize-missing-final'
    output_path = isolated_codex_workspace['workspace_dir'] / 'stream-finalize-missing-final.txt'
    output_path.write_text('먼저 상태를 확인하겠습니다.', encoding='utf-8')
    with state.codex_streams_lock:
        stream = _build_stream_state(
            stream_id,
            session_id,
            started_at=100.0,
            output_path=output_path,
        )
        stream['done'] = True
        stream['exit_code'] = 1
        stream['output'] = '먼저 상태를 확인하겠습니다.'
        stream['output_last_message'] = '먼저 상태를 확인하겠습니다.'
        stream['error'] = 'Codex CLI가 작업 명령 실행 후 최종 응답 없이 turn.completed를 반환했습니다.'
        stream['work_item_seen'] = True
        stream['work_item_completed_seen'] = True
        stream['progress_output_invalidated'] = True
        stream['turn_completed_seen'] = True
        stream['missing_final_response_after_work_item'] = True
        stream['untrusted_output_suppressed'] = True
        stream['codex_error_seen'] = True
        stream['completed_at'] = 102.0
        stream['updated_at'] = 102.0
        stream['finalize_reason'] = 'missing_final_response_after_work_item'
        state.codex_streams[stream_id] = stream

    monkeypatch.setattr(codex_chat.time, 'time', lambda: 105.0)

    saved_message = codex_chat.finalize_codex_stream(stream_id)

    assert saved_message is not None
    assert saved_message['role'] == 'error'
    assert saved_message['finalize_reason'] == 'missing_final_response_after_work_item'
    assert saved_message.get('work_item_seen') is True
    assert saved_message.get('work_item_completed_seen') is True
    assert saved_message.get('missing_final_response_after_work_item') is True
    assert '최종 응답 없이 turn.completed' in saved_message['content']
    assert '먼저 상태를 확인하겠습니다.' not in saved_message['content']


def test_enqueue_codex_queue_persists_and_starts_when_triggered(monkeypatch, isolated_codex_workspace):
    session = codex_chat.create_session('queue-trigger')
    session_id = session['id']

    with state.codex_streams_lock:
        active_stream = _build_stream_state(
            'active-stream',
            session_id,
            started_at=time.time(),
            output_path=isolated_codex_workspace['workspace_dir'] / 'active-stream.txt',
        )
        active_stream['done'] = False
        state.codex_streams['active-stream'] = active_stream

    captured = {}

    def _fake_create_stream(
        session_id_arg,
        prompt,
        model_override=None,
        reasoning_override=None,
            plan_mode=False,
            assistant_message_id=None,
            queued_execution=False,
            attachments=None,
            **_kwargs,
        ):
        captured['session_id'] = session_id_arg
        captured['prompt'] = prompt
        captured['model_override'] = model_override
        captured['reasoning_override'] = reasoning_override
        captured['plan_mode'] = bool(plan_mode)
        captured['assistant_message_id'] = assistant_message_id
        captured['queued_execution'] = bool(queued_execution)
        captured['attachments'] = attachments
        return {'id': 'queued-stream', 'started_at': 12345, 'created_at': 12345}

    monkeypatch.setattr(codex_chat, 'create_codex_stream', _fake_create_stream)

    queued = codex_chat.enqueue_codex_stream_for_session(
        session_id,
        '다음 작업을 진행해줘',
        plan_mode=True,
    )

    assert queued.get('ok') is True
    assert queued.get('started') is False
    assert queued.get('queued') is True
    assert queued.get('queue_count') == 1
    assert codex_chat.get_session(session_id).get('pending_queue_count') == 1

    with state.codex_streams_lock:
        state.codex_streams['active-stream']['done'] = True

    started = codex_chat.trigger_next_queued_codex_stream(session_id)

    assert started is not None
    assert started.get('ok') is True
    assert started.get('started') is True
    assert started.get('stream_id') == 'queued-stream'
    assert started.get('queue_count') == 0
    assert captured['session_id'] == session_id
    assert '## Plan Mode Guardrails' in captured['prompt']
    assert captured['queued_execution'] is True
    updated = codex_chat.get_session(session_id)
    assert updated.get('pending_queue_count') == 0
    assert updated['messages'][-2]['role'] == 'user'
    assert updated['messages'][-2]['content'] == '다음 작업을 진행해줘'
    assert updated['messages'][-1]['role'] == 'assistant'


def test_chat_queue_route_rejects_plain_prompt_when_encryption_required(chat_route_client):
    session = codex_chat.create_session('encrypted-route-reject')

    response = chat_route_client.post(
        f"/api/codex/sessions/{session['id']}/message/queue",
        json={'prompt': 'plain prompt'},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['error_code'] == 'encrypted_chat_prompt_required'


def test_chat_queue_route_accepts_trusted_tailscale_http_fallback(
        chat_route_client,
        isolated_codex_workspace,
        monkeypatch):
    monkeypatch.setattr(codex_chat_blueprint, 'CODEX_ALLOW_TRUSTED_HTTP_CRYPTO_FALLBACK', True)
    session = codex_chat.create_session('trusted-http-route-queue')
    session_id = session['id']
    with state.codex_streams_lock:
        active_stream = _build_stream_state(
            'active-trusted-http-stream',
            session_id,
            started_at=time.time(),
            output_path=isolated_codex_workspace['workspace_dir'] / 'active-trusted-http-stream.txt',
        )
        active_stream['done'] = False
        state.codex_streams['active-trusted-http-stream'] = active_stream

    response = chat_route_client.post(
        f'/api/codex/sessions/{session_id}/message/queue',
        base_url='http://100.64.12.34',
        headers={'X-Codex-Trusted-Http-Fallback': '1'},
        json={
            'prompt': 'Tailscale HTTP fallback prompt',
            'plan_mode': True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['queued'] is True
    assert payload['queue_count'] == 1
    assert payload['pending_queue'][0]['prompt'] == 'Tailscale HTTP fallback prompt'
    assert payload.get('encrypted') is None


def test_chat_queue_route_rejects_untrusted_http_fallback_header(chat_route_client):
    session = codex_chat.create_session('untrusted-http-route-reject')

    response = chat_route_client.post(
        f'/api/codex/sessions/{session["id"]}/message/queue',
        base_url='http://example.com',
        headers={'X-Codex-Trusted-Http-Fallback': '1'},
        json={'prompt': 'plain prompt'},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['error_code'] == 'encrypted_chat_prompt_required'


def test_encrypted_chat_queue_route_accepts_prompt_and_encrypts_response(
        chat_route_client,
        isolated_codex_workspace):
    session = codex_chat.create_session('encrypted-route-queue')
    session_id = session['id']
    with state.codex_streams_lock:
        active_stream = _build_stream_state(
            'active-route-stream',
            session_id,
            started_at=time.time(),
            output_path=isolated_codex_workspace['workspace_dir'] / 'active-route-stream.txt',
        )
        active_stream['done'] = False
        state.codex_streams['active-route-stream'] = active_stream

    crypto_session = _open_test_chat_crypto_session(chat_route_client)
    response = chat_route_client.post(
        f'/api/codex/sessions/{session_id}/message/queue',
        json=_encrypt_test_chat_payload(crypto_session, {
            'prompt': '암호화된 다음 작업',
            'plan_mode': True,
        }),
    )

    assert response.status_code == 200
    envelope = response.get_json()
    payload = _decrypt_test_chat_payload(crypto_session, envelope)
    assert payload['queued'] is True
    assert payload['queue_count'] == 1
    assert payload['pending_queue'][0]['prompt'] == '암호화된 다음 작업'
    updated = codex_chat.get_session(session_id)
    assert updated['pending_queue'][0]['prompt'] == '암호화된 다음 작업'


def test_build_codex_exec_env_keeps_default_home_for_direct_execution(monkeypatch, tmp_path):
    explicit_home = tmp_path / 'explicit-codex-home'
    default_home = tmp_path / 'default-codex-home'
    default_home.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('CODEX_HOME', str(explicit_home))
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(codex_chat, '_CODEX_HOME', default_home)

    env = codex_chat._build_codex_exec_env()

    assert env.get('CODEX_HOME') == str(explicit_home)


def test_build_codex_exec_env_uses_authenticated_default_home(monkeypatch, tmp_path):
    explicit_home = tmp_path / 'explicit-codex-home'
    explicit_home.mkdir()
    default_home = tmp_path / 'default-codex-home'
    default_home.mkdir()
    (default_home / 'auth.json').write_text('{"token": "test"}', encoding='utf-8')

    monkeypatch.setenv('CODEX_HOME', str(explicit_home))
    monkeypatch.setattr(codex_chat, '_CODEX_HOME', default_home)

    env = codex_chat._build_codex_exec_env()

    assert env.get('CODEX_HOME') == str(default_home)


def test_build_codex_exec_env_uses_authenticated_login_home(monkeypatch, tmp_path):
    explicit_home = tmp_path / 'explicit-codex-home'
    explicit_home.mkdir()
    default_home = tmp_path / 'default-codex-home'
    default_home.mkdir()
    shifted_home = tmp_path / 'works'
    shifted_home.mkdir()
    login_home = tmp_path / 'real-home' / '.codex'
    login_home.mkdir(parents=True)
    (login_home / 'auth.json').write_text('{"token": "test"}', encoding='utf-8')

    monkeypatch.setenv('CODEX_HOME', str(explicit_home))
    monkeypatch.setenv('HOME', str(shifted_home))
    monkeypatch.setattr(codex_chat, '_CODEX_HOME', default_home)
    monkeypatch.setattr(codex_chat, '_get_login_codex_home', lambda: login_home)

    env = codex_chat._build_codex_exec_env()

    assert env.get('CODEX_HOME') == str(login_home)


def test_build_codex_exec_env_redirects_unwritable_codex_home_for_direct_execution(
        monkeypatch,
        tmp_path):
    source_home = tmp_path / 'source-codex-home'
    source_home.mkdir()
    (source_home / 'auth.json').write_text('{"token": "test"}', encoding='utf-8')
    (source_home / 'config.toml').write_text('model = "test"\n', encoding='utf-8')
    (source_home / 'models_cache.json').write_text('{"models": []}\n', encoding='utf-8')
    storage_dir = tmp_path / 'agent-state'

    monkeypatch.setenv('CODEX_HOME', str(source_home))
    monkeypatch.setattr(codex_chat, 'CODEX_STORAGE_DIR', storage_dir)

    original_probe = codex_chat._path_is_writable_directory

    def fake_writable_directory(path):
        if Path(path).expanduser() == source_home:
            return False
        return original_probe(path)

    monkeypatch.setattr(codex_chat, '_path_is_writable_directory', fake_writable_directory)

    env = codex_chat._build_codex_exec_env()

    queued_home = storage_dir / 'queued_codex_home'
    assert env.get('CODEX_HOME') == str(queued_home)
    assert (queued_home / 'auth.json').read_text(encoding='utf-8') == '{"token": "test"}'
    assert (queued_home / 'config.toml').read_text(encoding='utf-8') == 'model = "test"\n'
    assert (queued_home / 'models_cache.json').read_text(encoding='utf-8') == '{"models": []}\n'


def test_build_codex_exec_env_uses_storage_home_for_queued_execution(monkeypatch, tmp_path):
    source_home = tmp_path / 'source-codex-home'
    source_home.mkdir()
    (source_home / 'auth.json').write_text('{"token": "test"}', encoding='utf-8')
    (source_home / 'config.toml').write_text('model = "test"\n', encoding='utf-8')
    (source_home / 'models_cache.json').write_text('{"models": []}\n', encoding='utf-8')
    (source_home / 'skills').mkdir()
    storage_dir = tmp_path / 'agent-state'
    read_only_home = tmp_path / 'read-only-home'
    read_only_xdg_cache = tmp_path / 'read-only-cache'

    monkeypatch.setenv('CODEX_HOME', str(source_home))
    monkeypatch.setenv('HOME', str(read_only_home))
    monkeypatch.setenv('XDG_CACHE_HOME', str(read_only_xdg_cache))
    monkeypatch.delenv('CODEX_QUEUE_CODEX_HOME', raising=False)
    monkeypatch.setattr(codex_chat, 'CODEX_STORAGE_DIR', storage_dir)

    env = codex_chat._build_codex_exec_env(queued_execution=True)

    queued_home = storage_dir / 'queued_codex_home'
    assert env.get('CODEX_HOME') == str(queued_home)
    assert env.get('HOME') == str(queued_home)
    assert env.get('XDG_CACHE_HOME') == str(queued_home / 'cache')
    assert env.get('XDG_STATE_HOME') == str(queued_home / 'state')
    assert env.get('XDG_CONFIG_HOME') == str(queued_home / 'config')
    assert env.get('TMPDIR') == str(queued_home / 'tmp')
    assert (queued_home / 'sessions').is_dir()
    assert (queued_home / 'tmp').is_dir()
    assert (queued_home / 'shell_snapshots').is_dir()
    assert (queued_home / 'cache').is_dir()
    assert (queued_home / 'state').is_dir()
    assert (queued_home / 'config').is_dir()
    assert (queued_home / 'auth.json').read_text(encoding='utf-8') == '{"token": "test"}'
    assert (queued_home / 'config.toml').read_text(encoding='utf-8') == 'model = "test"\n'
    assert (queued_home / 'models_cache.json').read_text(encoding='utf-8') == '{"models": []}\n'
    assert (queued_home / 'skills').is_symlink()
    assert (queued_home / 'skills').resolve() == source_home / 'skills'


def test_build_codex_exec_env_copies_memories_for_queued_execution(monkeypatch, tmp_path):
    source_home = tmp_path / 'source-codex-home'
    source_home.mkdir()
    memories_dir = source_home / 'memories'
    (memories_dir / '.git').mkdir(parents=True)
    (memories_dir / '.git' / 'config').write_text('[core]\n', encoding='utf-8')
    (memories_dir / '.codex').mkdir()
    (memories_dir / '.codex' / 'notes.md').write_text('queued memory\n', encoding='utf-8')
    (source_home / 'skills').mkdir()
    storage_dir = tmp_path / 'agent-state'
    queued_home = storage_dir / 'queued_codex_home'
    queued_home.mkdir(parents=True)
    (queued_home / 'memories').symlink_to(memories_dir, target_is_directory=True)

    monkeypatch.setenv('CODEX_HOME', str(source_home))
    monkeypatch.setattr(codex_chat, 'CODEX_STORAGE_DIR', storage_dir)

    env = codex_chat._build_codex_exec_env(queued_execution=True)

    copied_memories = queued_home / 'memories'
    assert env.get('CODEX_HOME') == str(queued_home)
    assert copied_memories.is_dir()
    assert not copied_memories.is_symlink()
    assert (copied_memories / '.git').is_dir()
    assert (copied_memories / '.git' / 'config').read_text(encoding='utf-8') == '[core]\n'
    assert (copied_memories / '.codex' / 'notes.md').read_text(encoding='utf-8') == 'queued memory\n'
    assert (queued_home / 'skills').is_symlink()
    assert (queued_home / 'skills').resolve() == source_home / 'skills'


def test_build_codex_exec_env_preserves_writable_home_for_queued_execution(monkeypatch, tmp_path):
    source_home = tmp_path / 'source-codex-home'
    source_home.mkdir()
    storage_dir = tmp_path / 'agent-state'
    writable_home = tmp_path / 'home'
    writable_home.mkdir()

    monkeypatch.setenv('CODEX_HOME', str(source_home))
    monkeypatch.setenv('HOME', str(writable_home))
    monkeypatch.setattr(codex_chat, 'CODEX_STORAGE_DIR', storage_dir)

    env = codex_chat._build_codex_exec_env(queued_execution=True)

    queued_home = storage_dir / 'queued_codex_home'
    assert env.get('CODEX_HOME') == str(queued_home)
    assert env.get('HOME') == str(writable_home)
    assert env.get('XDG_CACHE_HOME') == str(queued_home / 'cache')


class _FakePipe:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        time.sleep(0.005)
        return ''

    def close(self):
        return None


def _write_output_last_message_from_cmd(cmd, text):
    output_path = None
    for index, token in enumerate(cmd):
        if token == '--output-last-message' and index + 1 < len(cmd):
            output_path = Path(cmd[index + 1])
            break
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding='utf-8')


class _HangingProcess:
    def __init__(self, cmd, **kwargs):
        self.pid = 43210
        self._return_code = None
        self.stdout = _FakePipe(['stream output\n'])
        self.stderr = _FakePipe([])

        output_path = None
        for index, token in enumerate(cmd):
            if token == '--output-last-message' and index + 1 < len(cmd):
                output_path = Path(cmd[index + 1])
                break
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('assistant from output file', encoding='utf-8')

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        if timeout is None:
            while self._return_code is None:
                time.sleep(0.001)
        else:
            deadline = time.time() + timeout
            while self._return_code is None and time.time() < deadline:
                time.sleep(0.001)
        if self._return_code is None:
            raise TimeoutError('process did not exit')
        return self._return_code


def test_run_codex_stream_finalizes_on_post_output_idle(monkeypatch, isolated_codex_workspace):
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _HangingProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 0.03)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 1)

    session = codex_chat.create_session('watchdog-finalize')
    session_id = session['id']
    stream_id = 'stream-watchdog-finalize'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-watchdog-finalize.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'watchdog prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'assistant'
    assert saved_message['content'] == 'assistant from output file'
    assert saved_message['finalize_reason'] == 'post_output_idle_timeout'
    assert isinstance(saved_message.get('duration_ms'), int)

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('done') is True
        assert stream.get('saved') is True


class _ExitedWithoutFinalMessageProcess:
    def __init__(self, cmd, **kwargs):
        self.pid = 54321
        self._return_code = 0
        self.stdout = _FakePipe([])
        self.stderr = _FakePipe([])
        self._cmd = cmd
        self._kwargs = kwargs

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedAfterProgressAndCommandWithoutFinalMessageProcess:
    def __init__(self, cmd, **kwargs):
        _write_output_last_message_from_cmd(cmd, '앱 구조를 설계하고 구현하겠습니다.')
        del cmd
        del kwargs
        self.pid = 54322
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'thread.started',
            }) + '\n',
            json.dumps({
                'type': 'turn.started',
            }) + '\n',
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'agent_message',
                    'text': '앱 구조를 설계하고 구현하겠습니다.',
                },
            }) + '\n',
            json.dumps({
                'type': 'item.started',
                'item': {
                    'type': 'command_execution',
                    'command': 'mkdir app',
                },
            }) + '\n',
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'command_execution',
                    'status': 'completed',
                    'command': 'mkdir app',
                    'exit_code': 0,
                    'stdout': '',
                    'stderr': '',
                },
            }) + '\n',
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'agent_message',
                    'text': '',
                },
            }) + '\n',
            json.dumps({
                'type': 'turn.completed',
            }) + '\n',
        ])
        self.stderr = _FakePipe([])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedAfterProgressAndCommandTurnCompletedWithoutFinalMessageProcess:
    def __init__(self, cmd, **kwargs):
        _write_output_last_message_from_cmd(
            cmd,
            '먼저 test 폴더 현재 상태를 확인하고 앱을 구현하겠습니다.',
        )
        del cmd
        del kwargs
        self.pid = 54323
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({'type': 'thread.started'}) + '\n',
            json.dumps({'type': 'turn.started'}) + '\n',
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'agent_message',
                    'text': '먼저 test 폴더 현재 상태를 확인하고 앱을 구현하겠습니다.',
                },
            }) + '\n',
            json.dumps({
                'type': 'item.started',
                'item': {
                    'type': 'command_execution',
                    'status': 'in_progress',
                    'command': (
                        'powershell.exe -Command "Get-ChildItem -Path \'test\' '
                        '-Recurse -ErrorAction SilentlyContinue | Select-Object FullName"'
                    ),
                },
            }) + '\n',
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'command_execution',
                    'status': 'completed',
                    'command': (
                        'powershell.exe -Command "Get-ChildItem -Path \'test\' '
                        '-Recurse -ErrorAction SilentlyContinue | Select-Object FullName"'
                    ),
                    'exit_code': 0,
                },
            }) + '\n',
            json.dumps({'type': 'turn.completed'}) + '\n',
        ])
        self.stderr = _FakePipe([])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedWithJsonFinalMessageProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 65432
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'response_item',
                'payload': {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': '중간 응답'}],
                    'phase': 'commentary',
                },
            }) + '\n',
            json.dumps({
                'type': 'task_complete',
                'payload': {'last_agent_message': '스트림 최종 응답'},
            }) + '\n',
        ])
        self.stderr = _FakePipe([])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


_IMAGEGEN_DELAYED_TEST_CODEX_SESSION_ID = 'abcdef1234567890abcdef12'
_IMAGEGEN_MISSING_TEST_CODEX_SESSION_ID = 'abcdef1234567890abcdef13'


class _ExitedWithDelayedImagegenOutputProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        self.pid = 65434
        self._started_at = time.time()
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'session_meta',
                'payload': {'id': _IMAGEGEN_DELAYED_TEST_CODEX_SESSION_ID},
            }) + '\n',
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'image_generation_call',
                    'status': 'completed',
                },
            }) + '\n',
            json.dumps({
                'type': 'task_complete',
                'payload': {
                    'last_agent_message': (
                        '<!-- codex-workbench:imagegen-filename: delayed-news.png -->'
                        '이미지 생성 완료'
                    ),
                },
            }) + '\n',
        ])
        self.stderr = _FakePipe([])
        codex_home = Path(kwargs.get('env', {}).get('CODEX_HOME') or '')
        source_path = (
            codex_home
            / 'generated_images'
            / _IMAGEGEN_DELAYED_TEST_CODEX_SESSION_ID
            / 'generated.png'
        )
        threading.Thread(
            target=self._write_delayed_image,
            args=(source_path,),
            daemon=True,
        ).start()

    @staticmethod
    def _write_delayed_image(source_path):
        time.sleep(0.15)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b'fake delayed png bytes')

    def poll(self):
        if time.time() - self._started_at < 0.03:
            return None
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedWithImagegenFinalMessageNoOutputProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 65435
        self._started_at = time.time()
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'session_meta',
                'payload': {'id': _IMAGEGEN_MISSING_TEST_CODEX_SESSION_ID},
            }) + '\n',
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'image_generation_call',
                    'status': 'completed',
                },
            }) + '\n',
            json.dumps({
                'type': 'task_complete',
                'payload': {
                    'last_agent_message': (
                        '<!-- codex-workbench:imagegen-filename: missing-news.png -->'
                        '이미지 생성 완료'
                    ),
                },
            }) + '\n',
        ])
        self.stderr = _FakePipe([])

    def poll(self):
        if time.time() - self._started_at < 0.03:
            return None
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


_STDIN_CLOSED_BENIGN_STDERR_LINE = (
    '2026-05-29T02:24:04.249616Z ERROR codex_core::tools::router: '
    'error=write_stdin failed: stdin is closed for this session; '
    'rerun exec_command with tty=true to keep stdin open'
)
_QUEUE_FULL_BENIGN_STDERR_LINE = (
    '2026-05-29T03:50:15.557962Z  WARN codex_app_server_client: '
    'dropping in-process app-server event because consumer queue is full'
)
_SAMPLING_RETRY_BENIGN_STDERR_LINE = (
    '2026-05-29T04:08:39.894468Z  WARN codex_core::session::turn: '
    'stream disconnected - retrying sampling request (1/5 in 219ms)'
)
_PLUGIN_MARKETPLACE_BENIGN_STDERR_LINE = (
    '2026-05-29T05:06:32.508104Z  WARN codex_core_plugins::manager: '
    'ignoring remote plugins missing from local marketplace during sync '
    'marketplace=openai-curated missing_remote_plugin_count=5 '
    'missing_remote_plugin_examples=["chatgpt-apps", "codex-security-victor-0528b"]'
)
_APP_SERVER_EVENT_LAG_BENIGN_STDERR_LINE = (
    '2026-05-29T05:51:40.451768Z  WARN codex_exec: '
    'in-process app-server event stream lagged; dropped 6475 events'
)


class _ExitedWithBenignStderrAndFinalMessageProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 65431
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'task_complete',
                'payload': {'last_agent_message': '정상 최종 응답'},
            }) + '\n',
        ])
        self.stderr = _FakePipe([
            'Reading additional input from stdin...\n',
            'WARNING: proceeding, even though we could not update PATH: Read-only file system (os error 30)\n',
            _STDIN_CLOSED_BENIGN_STDERR_LINE + '\n',
        ])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedWithLaggedProgressOnlyProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 65436
        self._return_code = 0
        self.stdout = _FakePipe([
            'in-process app-server event stream lagged; dropped 519 events\n',
            json.dumps({
                'type': 'response_item',
                'payload': {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': '진행 중 메시지'}],
                    'phase': 'commentary',
                },
            }) + '\n',
        ])
        self.stderr = _FakePipe([
            _QUEUE_FULL_BENIGN_STDERR_LINE + '\n',
            _SAMPLING_RETRY_BENIGN_STDERR_LINE + '\n',
        ])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedWithCommandExecutionFailureAndFinalMessageProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 65433
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'command_execution',
                    'status': 'failed',
                    'command': 'pytest -q',
                    'exit_code': 1,
                },
            }) + '\n',
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'agent_message',
                    'text': '실패한 테스트를 확인하고 수정했습니다.',
                },
            }) + '\n',
        ])
        self.stderr = _FakePipe([])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedWithMcpToolCallFailureAndFinalMessageProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 65434
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'item.completed',
                'item': {
                    'type': 'mcp_tool_call',
                    'status': 'failed',
                    'name': 'browser',
                },
            }) + '\n',
            json.dumps({
                'type': 'task_complete',
                'payload': {'last_agent_message': '브라우저 검증 불가 사유를 정리했습니다.'},
            }) + '\n',
        ])
        self.stderr = _FakePipe([
            _PLUGIN_MARKETPLACE_BENIGN_STDERR_LINE + '\n',
        ])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedWithJsonErrorProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 76543
        self._return_code = 1
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'thread.started',
                'payload': {'type': 'thread.started'},
            }) + '\n',
            json.dumps({
                'type': 'error',
                'message': 'Transport channel closed',
                'details': (
                    'UnexpectedContentType(text/plain; upstream connect error: '
                    'Connection refused)'
                ),
            }) + '\n',
            json.dumps({
                'type': 'turn.failed',
                'payload': {
                    'type': 'turn.failed',
                    'error': {'message': 'turn failed after MCP transport error'},
                },
            }) + '\n',
        ])
        self.stderr = _FakePipe([])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 1

    def kill(self):
        self._return_code = 1

    def wait(self, timeout=None):
        return self._return_code


class _ExitedWithMcpToolCancelAndFinalMessageProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 76544
        self._return_code = 0
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'error',
                'message': 'user cancelled MCP tool call',
            }) + '\n',
            json.dumps({
                'type': 'task_complete',
                'payload': {'last_agent_message': '작업 내용은 정상적으로 정리했습니다.'},
            }) + '\n',
        ])
        self.stderr = _FakePipe([])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 0

    def kill(self):
        self._return_code = 0

    def wait(self, timeout=None):
        return self._return_code


class _ExitedWithMcpToolCancelFinalMessageAndFailureProcess:
    def __init__(self, cmd, **kwargs):
        del cmd
        del kwargs
        self.pid = 76545
        self._return_code = 1
        self.stdout = _FakePipe([
            json.dumps({
                'type': 'task_complete',
                'payload': {'last_agent_message': '실패 전까지 완료한 작업입니다.'},
            }) + '\n',
            json.dumps({
                'type': 'error',
                'message': 'user canceled MCP tool call',
            }) + '\n',
        ])
        self.stderr = _FakePipe([])

    def poll(self):
        return self._return_code

    def terminate(self):
        self._return_code = 1

    def kill(self):
        self._return_code = 1

    def wait(self, timeout=None):
        return self._return_code


def test_run_codex_stream_uses_json_response_when_output_file_missing(monkeypatch, isolated_codex_workspace):
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _ExitedWithJsonFinalMessageProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-final')
    session_id = session['id']
    stream_id = 'stream-json-final'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-json-final.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'json stream prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'assistant'
    assert saved_message['content'] == '스트림 최종 응답'
    assert saved_message['finalize_reason'] == 'process_exit'
    assert 'Codex exec input:' in saved_message.get('work_details', '')
    assert 'prompt sent to stdin:' in saved_message.get('work_details', '')
    assert 'prompt_encoding: utf-8' in saved_message.get('work_details', '')
    assert 'json stream prompt' in saved_message.get('work_details', '')

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('saved') is True
        assert stream.get('done') is True


def test_run_codex_stream_uses_utf8_for_cli_text_pipes(monkeypatch, isolated_codex_workspace):
    captured = {}

    class CapturingProcess(_ExitedWithJsonFinalMessageProcess):
        def __init__(self, cmd, **kwargs):
            captured['cmd'] = cmd
            captured['kwargs'] = kwargs
            super().__init__(cmd, **kwargs)

    monkeypatch.setattr(codex_chat.subprocess, 'Popen', CapturingProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-utf8-pipes')
    stream_id = 'stream-json-utf8-pipes'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session['id'],
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-json-utf8-pipes.txt',
        )

    codex_chat._run_codex_stream(stream_id, '한글 stream prompt')

    assert captured['cmd'][-2:] == ['--', '-']
    assert captured['kwargs']['encoding'] == 'utf-8'
    assert captured['kwargs']['errors'] == 'replace'


def test_run_codex_stream_waits_for_delayed_imagegen_output_after_final_text(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setenv(
        'CODEX_QUEUE_CODEX_HOME',
        str(isolated_codex_workspace['workspace_dir'] / 'queued-codex-home'),
    )
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _ExitedWithDelayedImagegenOutputProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(
        codex_chat,
        '_final_response_timeout_seconds_for_stream',
        lambda stream, base_timeout: 1,
    )

    session = codex_chat.create_session('imagegen-delayed-output')
    session_id = session['id']
    stream_id = 'stream-imagegen-delayed-output'
    started_at = time.time()

    with state.codex_streams_lock:
        stream = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-imagegen-delayed.txt',
        )
        stream['user_prompt'] = '$imagegen 뉴스 이미지'
        stream['imagegen_workbench_requested'] = True
        stream['queued_execution'] = True
        state.codex_streams[stream_id] = stream

    codex_chat._run_codex_stream(stream_id, '$imagegen 뉴스 이미지')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'assistant'
    assert saved_message['finalize_reason'] == 'process_exit'
    assert '이미지 생성 완료' in saved_message['content']
    assert 'Generated image saved:' in saved_message['content']
    assert 'delayed-news.png' in saved_message['content']

    output_path = isolated_codex_workspace['workspace_dir'] / 'output' / 'imagegen' / 'delayed-news.png'
    assert output_path.read_bytes() == b'fake delayed png bytes'

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('saved') is True
        assert stream.get('done') is True
        assert stream.get('imagegen_workbench_outputs') == [str(output_path)]
        assert stream.get('imagegen_workbench_waiting_for_output') is False


def test_benign_stderr_filter_ignores_closed_stdin_tool_router_log():
    assert codex_chat._is_benign_codex_stderr_line(_STDIN_CLOSED_BENIGN_STDERR_LINE) is True


def test_benign_stderr_filter_ignores_app_server_and_sampling_retry_logs():
    stderr_text = '\n'.join([
        _QUEUE_FULL_BENIGN_STDERR_LINE,
        _SAMPLING_RETRY_BENIGN_STDERR_LINE,
        _PLUGIN_MARKETPLACE_BENIGN_STDERR_LINE,
        _APP_SERVER_EVENT_LAG_BENIGN_STDERR_LINE,
    ])

    assert codex_chat._is_benign_codex_stderr_line(_QUEUE_FULL_BENIGN_STDERR_LINE) is True
    assert codex_chat._is_benign_codex_stderr_line(_SAMPLING_RETRY_BENIGN_STDERR_LINE) is True
    assert codex_chat._is_benign_codex_stderr_line(_PLUGIN_MARKETPLACE_BENIGN_STDERR_LINE) is True
    assert codex_chat._is_benign_codex_stderr_line(_APP_SERVER_EVENT_LAG_BENIGN_STDERR_LINE) is True
    assert codex_chat._filter_benign_codex_stderr(stderr_text) == ''
    assert codex_chat._extract_codex_stderr_diagnostics(stderr_text) == {
        'queue_full_warning_count': 1,
        'sampling_stream_retry_count': 1,
        'event_stream_lagged': True,
        'dropped_event_count': 6475,
    }


def test_stream_reader_records_stderr_app_server_event_lag(isolated_codex_workspace):
    session = codex_chat.create_session('stderr-app-server-event-lag')
    stream_id = 'stream-stderr-app-server-event-lag'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session['id'],
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stderr-lag.txt',
        )

    codex_chat._stream_reader(
        stream_id,
        _FakePipe([_APP_SERVER_EVENT_LAG_BENIGN_STDERR_LINE + '\n']),
        'error',
    )

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('event_stream_lagged') is True
        assert stream.get('dropped_event_count') == 6475
        assert stream.get('codex_error_seen') is False
        assert stream.get('error') == ''


def test_codex_exec_gate_can_serialize_cli_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_chat, 'CODEX_CLI_EXEC_LOCK', True)
    monkeypatch.setattr(codex_chat, '_CODEX_EXEC_LOCK_PATH', tmp_path / 'codex_exec.lock')

    with codex_chat._codex_exec_gate() as lock_info:
        assert lock_info['parallel'] is False
        assert isinstance(lock_info['wait_ms'], int)


def test_run_codex_stream_ignores_benign_stderr_when_final_message_exists(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _ExitedWithBenignStderrAndFinalMessageProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-benign-stderr')
    session_id = session['id']
    stream_id = 'stream-json-benign-stderr'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-benign-stderr.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'json stream prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'assistant'
    assert saved_message['content'] == '정상 최종 응답'
    assert saved_message['finalize_reason'] == 'process_exit'
    assert 'Reading additional input' not in saved_message['content']
    assert 'write_stdin failed' not in saved_message['content']
    assert 'write_stdin failed' not in (saved_message.get('work_details') or '')

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('saved') is True
        assert stream.get('done') is True
        assert stream.get('error') == ''
        assert stream.get('codex_error_seen') is False


def test_run_codex_stream_errors_when_event_stream_lag_hides_final_response(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _ExitedWithLaggedProgressOnlyProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-lagged-no-final')
    session_id = session['id']
    stream_id = 'stream-json-lagged-no-final'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-lagged-no-final.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'json stream prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'error'
    assert saved_message['finalize_reason'] == 'event_stream_incomplete'
    assert 'Codex CLI event stream이 유실되어 최종 응답을 확인하지 못했습니다.' in saved_message['content']
    assert '진행 중 메시지' not in saved_message['content']
    assert saved_message.get('event_stream_lagged') is True
    assert saved_message.get('dropped_event_count') == 519
    assert saved_message.get('queue_full_warning_count') == 1
    assert saved_message.get('sampling_stream_retry_count') == 1
    assert saved_message.get('untrusted_output_suppressed') is True
    assert '진행 중 메시지' in (saved_message.get('work_details') or '')

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('done') is True
        assert stream.get('saved') is True
        assert stream.get('codex_error_seen') is True
        assert stream.get('event_stream_lagged') is True


def test_run_codex_stream_keeps_command_execution_failure_as_nonfatal_event(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setattr(
        codex_chat.subprocess,
        'Popen',
        _ExitedWithCommandExecutionFailureAndFinalMessageProcess,
    )
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-command-execution')
    session_id = session['id']
    stream_id = 'stream-json-command-execution'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-json-command.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'json stream prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'assistant'
    assert saved_message['content'] == '실패한 테스트를 확인하고 수정했습니다.'
    assert saved_message['finalize_reason'] == 'process_exit'
    assert 'item.completed' not in saved_message['content']
    assert any(
        event.get('item_type') == 'command_execution'
        for event in saved_message.get('codex_events') or []
    )

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('saved') is True
        assert stream.get('done') is True
        assert stream.get('codex_error_seen') is False


def test_run_codex_stream_keeps_mcp_tool_call_failure_as_nonfatal_event(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setattr(
        codex_chat.subprocess,
        'Popen',
        _ExitedWithMcpToolCallFailureAndFinalMessageProcess,
    )
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-mcp-tool-call')
    session_id = session['id']
    stream_id = 'stream-json-mcp-tool-call'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-json-mcp-tool-call.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'json stream prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'assistant'
    assert saved_message['content'] == '브라우저 검증 불가 사유를 정리했습니다.'
    assert saved_message['finalize_reason'] == 'process_exit'
    assert 'item.completed' not in saved_message['content']
    assert _PLUGIN_MARKETPLACE_BENIGN_STDERR_LINE not in saved_message['content']
    assert any(
        event.get('item_type') == 'mcp_tool_call'
        for event in saved_message.get('codex_events') or []
    )

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('saved') is True
        assert stream.get('done') is True
        assert stream.get('codex_error_seen') is False
        assert stream.get('error') == ''


def test_run_codex_stream_surfaces_json_error_event(monkeypatch, isolated_codex_workspace):
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _ExitedWithJsonErrorProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-error')
    session_id = session['id']
    stream_id = 'stream-json-error'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-json-error.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'json error prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'error'
    assert saved_message['finalize_reason'] == 'process_exit_error'
    assert 'Transport channel closed' in saved_message['content']
    assert 'Connection refused' in saved_message['content']
    assert '최종 응답을 받지 못해 종료합니다' not in saved_message['content']
    assert any(
        'Connection refused' in event.get('detail', '')
        for event in saved_message.get('codex_events') or []
    )

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('done') is True
        assert stream.get('saved') is True
        assert stream.get('exit_code') == 1
        assert stream.get('codex_error_seen') is True


def test_run_codex_stream_treats_mcp_tool_cancel_as_nonfatal_with_final_message(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _ExitedWithMcpToolCancelAndFinalMessageProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-mcp-cancel-final')
    session_id = session['id']
    stream_id = 'stream-json-mcp-cancel-final'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-json-mcp-cancel.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'json mcp cancel prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'assistant'
    assert saved_message['content'] == '작업 내용은 정상적으로 정리했습니다.'
    assert saved_message['finalize_reason'] == 'process_exit'
    assert saved_message.get('mcp_tool_call_cancel_error_seen') is True
    assert 'user cancelled MCP tool call' not in saved_message['content']

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('codex_error_seen') is False
        assert stream.get('mcp_tool_call_cancel_error_seen') is True
        assert 'user cancelled MCP tool call' in stream.get('error', '')


def test_run_codex_stream_preserves_final_message_when_mcp_tool_cancel_exit_fails(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setattr(
        codex_chat.subprocess,
        'Popen',
        _ExitedWithMcpToolCancelFinalMessageAndFailureProcess,
    )
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('json-stream-mcp-cancel-failed')
    session_id = session['id']
    stream_id = 'stream-json-mcp-cancel-failed'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-json-mcp-cancel-failed.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'json mcp cancel failed prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'error'
    assert saved_message['finalize_reason'] == 'process_exit_error'
    assert '실패 전까지 완료한 작업입니다.' in saved_message['content']
    assert 'user canceled MCP tool call' in saved_message['content']
    assert saved_message.get('mcp_tool_call_cancel_error_seen') is True


def test_run_codex_stream_times_out_when_final_message_missing(monkeypatch, isolated_codex_workspace):
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _ExitedWithoutFinalMessageProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('final-response-timeout')
    session_id = session['id']
    stream_id = 'stream-final-response-timeout'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-final-response-timeout.txt',
        )

    codex_chat._run_codex_stream(stream_id, 'timeout prompt')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'error'
    assert saved_message['finalize_reason'] == 'final_response_timeout'
    assert '최종 응답을 받지 못해 종료합니다' in saved_message['content']
    assert isinstance(saved_message.get('finalize_lag_ms'), int)

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('done') is True
        assert stream.get('saved') is True
        assert stream.get('exit_code') == 124


def test_run_codex_stream_errors_when_empty_final_after_command(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setattr(
        codex_chat.subprocess,
        'Popen',
        _ExitedAfterProgressAndCommandWithoutFinalMessageProcess,
    )
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 0.05)

    session = codex_chat.create_session('progress-before-command-timeout')
    session_id = session['id']
    stream_id = 'stream-progress-before-command-timeout'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=(
                isolated_codex_workspace['workspace_dir']
                / 'stream-progress-before-command-timeout.txt'
            ),
        )

    codex_chat._run_codex_stream(stream_id, 'make an app')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'error'
    assert saved_message['finalize_reason'] == 'missing_final_response_after_work_item'
    assert saved_message.get('progress_output_invalidated') is True
    assert saved_message.get('turn_completed_seen') is True
    assert saved_message.get('missing_final_response_after_work_item') is True
    assert saved_message.get('untrusted_output_suppressed') is True
    assert '앱 구조를 설계하고 구현하겠습니다.' not in saved_message['content']
    assert '중간 진행 메시지는 최종 답변이 아니므로 저장하지 않았습니다' in saved_message['content']
    assert any(
        event.get('item_type') == 'command_execution'
        and 'command=mkdir app' in event.get('detail', '')
        and 'exit_code=0' in event.get('detail', '')
        for event in saved_message.get('codex_events') or []
    )


def test_run_codex_stream_errors_immediately_when_turn_completes_without_final_after_command(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setattr(
        codex_chat.subprocess,
        'Popen',
        _ExitedAfterProgressAndCommandTurnCompletedWithoutFinalMessageProcess,
    )
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', 30)

    session = codex_chat.create_session('turn-completed-missing-final')
    session_id = session['id']
    stream_id = 'stream-turn-completed-missing-final'
    started_at = time.time()

    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=(
                isolated_codex_workspace['workspace_dir']
                / 'stream-turn-completed-missing-final.txt'
            ),
        )

    codex_chat._run_codex_stream(stream_id, 'make an app')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'error'
    assert saved_message['finalize_reason'] == 'missing_final_response_after_work_item'
    assert saved_message.get('progress_output_invalidated') is True
    assert saved_message.get('turn_completed_seen') is True
    assert saved_message.get('missing_final_response_after_work_item') is True
    assert '중간 진행 메시지는 최종 답변이 아니므로 저장하지 않았습니다' in saved_message['content']
    assert '먼저 test 폴더 현재 상태를 확인하고 앱을 구현하겠습니다.' not in saved_message['content']
    assert any(
        event.get('type') == 'turn.completed'
        for event in saved_message.get('codex_events') or []
    )


def test_run_codex_stream_times_out_waiting_for_imagegen_output_after_final_text(
        monkeypatch,
        isolated_codex_workspace):
    monkeypatch.setenv(
        'CODEX_QUEUE_CODEX_HOME',
        str(isolated_codex_workspace['workspace_dir'] / 'queued-codex-home'),
    )
    monkeypatch.setattr(codex_chat.subprocess, 'Popen', _ExitedWithImagegenFinalMessageNoOutputProcess)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.01)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', 5)
    monkeypatch.setattr(codex_chat, 'CODEX_STREAM_TERMINATE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(
        codex_chat,
        '_final_response_timeout_seconds_for_stream',
        lambda stream, base_timeout: 0.05,
    )

    session = codex_chat.create_session('imagegen-output-timeout')
    session_id = session['id']
    stream_id = 'stream-imagegen-output-timeout'
    started_at = time.time()

    with state.codex_streams_lock:
        stream = _build_stream_state(
            stream_id,
            session_id,
            started_at=started_at,
            output_path=isolated_codex_workspace['workspace_dir'] / 'stream-imagegen-timeout.txt',
        )
        stream['user_prompt'] = '$imagegen 뉴스 이미지'
        stream['imagegen_workbench_requested'] = True
        stream['queued_execution'] = True
        state.codex_streams[stream_id] = stream

    codex_chat._run_codex_stream(stream_id, '$imagegen 뉴스 이미지')

    updated_session = codex_chat.get_session(session_id)
    assert updated_session is not None
    assert updated_session['messages']
    saved_message = updated_session['messages'][-1]

    assert saved_message['role'] == 'error'
    assert saved_message['finalize_reason'] == 'imagegen_output_timeout'
    assert '이미지 생성 결과를 회수하지 못해 종료합니다' in saved_message['content']
    assert '최종 응답을 받지 못해' not in saved_message['content']

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('done') is True
        assert stream.get('saved') is True
        assert stream.get('exit_code') == 124
        assert not stream.get('imagegen_workbench_outputs')
