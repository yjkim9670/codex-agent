from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent import state
from codex_agent.services import codex_chat


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

    return {
        'store_path': store_path,
        'token_usage_path': token_usage_path,
        'usage_history_path': usage_history_path,
        'workspace_dir': workspace_dir,
    }


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

    def _fake_run(cmd, **kwargs):
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


def test_build_codex_exec_env_keeps_default_home_for_direct_execution(monkeypatch, tmp_path):
    explicit_home = tmp_path / 'explicit-codex-home'
    monkeypatch.setenv('CODEX_HOME', str(explicit_home))

    env = codex_chat._build_codex_exec_env()

    assert env.get('CODEX_HOME') == str(explicit_home)


def test_build_codex_exec_env_redirects_unwritable_codex_home_for_direct_execution(
        monkeypatch,
        tmp_path):
    source_home = tmp_path / 'source-codex-home'
    source_home.mkdir()
    (source_home / 'auth.json').write_text('{"token": "test"}', encoding='utf-8')
    (source_home / 'config.toml').write_text('model = "test"\n', encoding='utf-8')
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


def test_build_codex_exec_env_uses_storage_home_for_queued_execution(monkeypatch, tmp_path):
    source_home = tmp_path / 'source-codex-home'
    source_home.mkdir()
    (source_home / 'auth.json').write_text('{"token": "test"}', encoding='utf-8')
    (source_home / 'config.toml').write_text('model = "test"\n', encoding='utf-8')
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

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('saved') is True
        assert stream.get('done') is True


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

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        assert stream is not None
        assert stream.get('saved') is True
        assert stream.get('done') is True
        assert stream.get('error') == ''
        assert stream.get('codex_error_seen') is False


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
