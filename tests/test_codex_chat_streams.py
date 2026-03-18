from __future__ import annotations

import sys
import time
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
    workspace_dir = tmp_path / 'workspace'
    workspace_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(codex_chat, 'CODEX_CHAT_STORE_PATH', store_path)
    monkeypatch.setattr(codex_chat, 'WORKSPACE_DIR', workspace_dir)
    monkeypatch.setattr(codex_chat, 'CODEX_SKIP_GIT_REPO_CHECK', True)

    return {
        'store_path': store_path,
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
    assert saved_message['duration_ms'] == 2000
    assert saved_message['finalize_reason'] == 'process_exit'
    assert saved_message['finalize_lag_ms'] == 3000
    assert 'CLI stdout:' in saved_message.get('work_details', '')
    assert 'step 1' in saved_message.get('work_details', '')
    assert saved_message['completed_at'] == saved_message['created_at']


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
