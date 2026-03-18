from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model_agent import state
from model_agent.services import model_chat


@pytest.fixture(autouse=True)
def _reset_stream_state():
    with state.model_streams_lock:
        state.model_streams.clear()
    yield
    with state.model_streams_lock:
        state.model_streams.clear()


@pytest.fixture
def isolated_model_workspace(tmp_path, monkeypatch):
    store_path = tmp_path / 'model_chat_sessions.json'
    workspace_dir = tmp_path / 'workspace'
    workspace_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(model_chat, 'MODEL_CHAT_STORE_PATH', store_path)
    monkeypatch.setattr(model_chat, 'WORKSPACE_DIR', workspace_dir)

    return {
        'store_path': store_path,
        'workspace_dir': workspace_dir,
    }


def _build_stream_state(stream_id, session_id, started_at):
    return {
        'id': stream_id,
        'session_id': session_id,
        'provider': 'gemini',
        'model': 'gemini-flash-latest',
        'output': '',
        'error': '',
        'done': False,
        'saved': False,
        'exit_code': None,
        'cancelled': False,
        'request_running': False,
        'started_at': started_at,
        'last_output_at': started_at,
        'completed_at': None,
        'saved_at': None,
        'finalize_reason': None,
        'output_length': 0,
        'error_length': 0,
        'created_at': started_at,
        'updated_at': started_at,
    }


def test_append_message_preserves_created_at(isolated_model_workspace):
    session = model_chat.create_session('append-message-created-at')

    created_at = '2026-03-19T10:20:30+09:00'
    message = model_chat.append_message(
        session['id'],
        'assistant',
        'hello',
        created_at=created_at,
    )

    assert message is not None
    assert message['created_at'] == created_at


def test_finalize_stream_uses_completed_at_metadata(monkeypatch, isolated_model_workspace):
    session = model_chat.create_session('finalize-metadata')
    session_id = session['id']

    stream_id = 'stream-finalize-metadata'
    with state.model_streams_lock:
        stream = _build_stream_state(stream_id, session_id, started_at=100.0)
        stream['done'] = True
        stream['exit_code'] = 0
        stream['output'] = 'assistant text'
        stream['output_length'] = len(stream['output'])
        stream['completed_at'] = 102.0
        stream['updated_at'] = 102.0
        stream['finalize_reason'] = 'process_exit'
        state.model_streams[stream_id] = stream

    monkeypatch.setattr(model_chat.time, 'time', lambda: 105.0)

    saved_message = model_chat.finalize_model_stream(stream_id)

    assert saved_message is not None
    assert saved_message['role'] == 'assistant'
    assert saved_message['content'] == 'assistant text'
    assert saved_message['duration_ms'] == 2000
    assert saved_message['finalize_reason'] == 'process_exit'
    assert saved_message['finalize_lag_ms'] == 3000
    assert saved_message['completed_at'] == saved_message['created_at']
