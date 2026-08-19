from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent import state
from codex_agent.services import codex_chat
from codex_agent.services import codex_cli_output_filter


RAW_REJECTED_COMMAND = (
    'z00_tmp=$(mktemp -d)\n'
    'rm -rf "$z00_tmp"`: CreateProcess { message: '
    '"Rejected(\\"rm -f style commands are not permitted. Use a safer approach\\")" }'
)


def _new_stream():
    return {
        'id': 'filter-test-stream',
        'output': '',
        'error': '',
        'raw_stderr': '',
        'cancelled': False,
        'done': False,
        'output_length': 0,
        'error_length': 0,
        'codex_error_seen': False,
        'mcp_tool_call_cancel_error_seen': False,
        'updated_at': 0,
    }


def setup_function(_function):
    with state.codex_streams_lock:
        state.codex_streams.clear()


def teardown_function(_function):
    with state.codex_streams_lock:
        state.codex_streams.clear()


def test_rejected_create_process_is_classified_as_internal_cli_detail():
    assert codex_cli_output_filter._looks_like_internal_cli_detail(RAW_REJECTED_COMMAND)
    assert codex_cli_output_filter._looks_like_internal_cli_detail(
        '{"cmd":["bash","-lc","ls"],"timeout":120000}'
    )


def test_normal_user_facing_errors_are_not_classified_as_internal_cli_detail():
    assert not codex_cli_output_filter._looks_like_internal_cli_detail(
        'fatal: unable to access repository: authentication failed'
    )
    assert not codex_cli_output_filter._looks_like_internal_cli_detail(
        'Workbench 연결에 실패했습니다.'
    )


def test_raw_exec_error_is_kept_out_of_chat_error_and_retained_as_diagnostic():
    codex_cli_output_filter.install_codex_cli_output_filter()
    stream_id = 'filter-test-stream'
    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _new_stream()

    assert codex_chat._append_stream_exec_error(stream_id, RAW_REJECTED_COMMAND)

    with state.codex_streams_lock:
        stream = state.codex_streams[stream_id]
        assert stream['error'] == ''
        assert stream.get('cli_diagnostic_seen') is True
        assert RAW_REJECTED_COMMAND in stream.get('cli_diagnostics', [])


def test_normal_error_still_uses_existing_user_facing_error_path():
    codex_cli_output_filter.install_codex_cli_output_filter()
    stream_id = 'filter-test-stream'
    with state.codex_streams_lock:
        state.codex_streams[stream_id] = _new_stream()

    message = 'fatal: repository authentication failed'
    assert codex_chat._append_stream_exec_error(stream_id, message)

    with state.codex_streams_lock:
        stream = state.codex_streams[stream_id]
        assert message in stream['error']
        assert not stream.get('cli_diagnostic_seen')


def test_final_message_does_not_append_raw_cli_detail():
    codex_cli_output_filter.install_codex_cli_output_filter()

    assert codex_chat._combine_stream_output_and_error(
        '보호 목록 검증 중 명령이 정책에 의해 거부되어 안전한 방식으로 다시 확인했습니다.',
        RAW_REJECTED_COMMAND,
    ) == '보호 목록 검증 중 명령이 정책에 의해 거부되어 안전한 방식으로 다시 확인했습니다.'

    assert codex_chat._combine_stream_output_and_error('', RAW_REJECTED_COMMAND) == (
        'Codex CLI 작업 중 오류가 발생했습니다. 상세 로그에서 원인을 확인하세요.'
    )
