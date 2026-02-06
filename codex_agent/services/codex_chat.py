"""Codex chat session storage and execution helpers."""

import json
import subprocess
import threading
import time
import uuid
from copy import deepcopy

from .. import state
from ..config import (
    CODEX_CHAT_STORE_PATH,
    CODEX_CONTEXT_MAX_CHARS,
    CODEX_EXEC_TIMEOUT_SECONDS,
    CODEX_STREAM_TTL_SECONDS,
    REPO_ROOT,
    WORKSPACE_DIR,
)
from ..utils.time import normalize_timestamp

_DATA_LOCK = threading.Lock()

_ROLE_LABELS = {
    'user': 'User',
    'assistant': 'Assistant',
    'system': 'System',
    'error': 'Error'
}


def _load_data():
    if not CODEX_CHAT_STORE_PATH.exists():
        return {'sessions': []}
    try:
        data = json.loads(CODEX_CHAT_STORE_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {'sessions': []}
    if not isinstance(data, dict):
        return {'sessions': []}
    sessions = data.get('sessions')
    if not isinstance(sessions, list):
        data['sessions'] = []
    return data


def _save_data(data):
    CODEX_CHAT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODEX_CHAT_STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


def _sort_sessions(sessions):
    return sorted(
        sessions,
        key=lambda item: item.get('updated_at') or item.get('created_at') or '',
        reverse=True
    )


def _find_session(sessions, session_id):
    for session in sessions:
        if session.get('id') == session_id:
            return session
    return None


def _has_user_message(session):
    return any(message.get('role') == 'user' for message in session.get('messages', []))


def generate_session_title(prompt):
    normalized = ' '.join(str(prompt or '').strip().split())
    if not normalized:
        return 'New session'
    if len(normalized) > 24:
        return f"{normalized[:24]}..."
    return normalized


def list_sessions():
    data = _load_data()
    sessions = _sort_sessions(data.get('sessions', []))
    summary = []
    for session in sessions:
        summary.append({
            'id': session.get('id'),
            'title': session.get('title') or 'New session',
            'created_at': session.get('created_at'),
            'updated_at': session.get('updated_at'),
            'message_count': len(session.get('messages', []))
        })
    return summary


def get_session(session_id):
    data = _load_data()
    session = _find_session(data.get('sessions', []), session_id)
    return deepcopy(session) if session else None


def create_session(title=None):
    now = normalize_timestamp(None)
    session = {
        'id': uuid.uuid4().hex,
        'title': (title or '').strip() or 'New session',
        'created_at': now,
        'updated_at': now,
        'messages': []
    }
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        sessions.append(session)
        data['sessions'] = _sort_sessions(sessions)
        _save_data(data)
    return deepcopy(session)


def update_session_title(session_id, title):
    if not title:
        return None
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
        if not session:
            return None
        session['title'] = title
        session['updated_at'] = normalize_timestamp(None)
        data['sessions'] = _sort_sessions(data.get('sessions', []))
        _save_data(data)
        return deepcopy(session)


def append_message(session_id, role, content):
    if content is None:
        content = ''
    message = {
        'id': uuid.uuid4().hex,
        'role': role,
        'content': str(content),
        'created_at': normalize_timestamp(None)
    }
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        session = _find_session(sessions, session_id)
        if not session:
            return None
        session.setdefault('messages', []).append(message)
        session['updated_at'] = normalize_timestamp(None)
        data['sessions'] = _sort_sessions(sessions)
        _save_data(data)
    return deepcopy(message)


def ensure_default_title(session_id, prompt):
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
        if not session:
            return None
        title = session.get('title') or ''
        if title.strip() and title != 'New session':
            return deepcopy(session)
        if _has_user_message(session):
            return deepcopy(session)
        session['title'] = generate_session_title(prompt)
        session['updated_at'] = normalize_timestamp(None)
        data['sessions'] = _sort_sessions(data.get('sessions', []))
        _save_data(data)
        return deepcopy(session)


def rename_session(session_id, title):
    if not title:
        return None
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
        if not session:
            return None
        session['title'] = title
        session['updated_at'] = normalize_timestamp(None)
        data['sessions'] = _sort_sessions(data.get('sessions', []))
        _save_data(data)
        return deepcopy(session)


def delete_session(session_id):
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        remaining = [session for session in sessions if session.get('id') != session_id]
        if len(remaining) == len(sessions):
            return False
        data['sessions'] = _sort_sessions(remaining)
        _save_data(data)
        return True


def build_codex_prompt(messages, prompt):
    lines = ['The following is a conversation between a user and Codex CLI.']
    for message in messages:
        label = _ROLE_LABELS.get(message.get('role'), 'User')
        content = message.get('content') or ''
        lines.append(f"{label}: {content}")
    lines.append(f"User: {prompt}")
    transcript = '\n'.join(lines)
    if len(transcript) <= CODEX_CONTEXT_MAX_CHARS:
        return transcript
    return transcript[-CODEX_CONTEXT_MAX_CHARS:]


def execute_codex_prompt(prompt):
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = WORKSPACE_DIR / f"codex_output_{uuid.uuid4().hex}.txt"
    cmd = [
        'codex',
        'exec',
        '--full-auto',
        '--color',
        'never',
        '--output-last-message',
        str(output_path),
        prompt
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=CODEX_EXEC_TIMEOUT_SECONDS,
            check=False
        )
    except FileNotFoundError:
        return None, 'codex 명령을 찾을 수 없습니다.'
    except subprocess.TimeoutExpired:
        return None, 'Codex 응답 시간이 초과되었습니다.'
    except Exception as exc:
        return None, f'Codex 실행 중 오류가 발생했습니다: {exc}'

    output_text = ''
    if output_path.exists():
        try:
            output_text = output_path.read_text(encoding='utf-8').strip()
        except Exception:
            output_text = ''
        finally:
            try:
                output_path.unlink()
            except Exception:
                pass

    if not output_text:
        output_text = (result.stdout or '').strip()

    if result.returncode != 0:
        error_text = (result.stderr or '').strip()
        return None, error_text or output_text or 'Codex 실행에 실패했습니다.'

    return output_text, None


def _append_stream_chunk(stream_id, key, chunk):
    if not chunk:
        return
    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        if not stream:
            return
        if stream.get('cancelled'):
            return
        stream[key] += chunk
        stream['updated_at'] = time.time()


def _stream_reader(stream_id, pipe, key):
    try:
        for line in iter(pipe.readline, ''):
            _append_stream_chunk(stream_id, key, line)
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _run_codex_stream(stream_id, prompt):
    cmd = [
        'codex',
        'exec',
        '--full-auto',
        '--color',
        'never',
        prompt
    ]
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        _append_stream_chunk(stream_id, 'error', 'codex 명령을 찾을 수 없습니다.\n')
        with state.codex_streams_lock:
            stream = state.codex_streams.get(stream_id)
            if stream:
                stream['done'] = True
                stream['exit_code'] = 127
                stream['updated_at'] = time.time()
        return
    except Exception as exc:
        _append_stream_chunk(stream_id, 'error', f'Codex 실행 중 오류가 발생했습니다: {exc}\n')
        with state.codex_streams_lock:
            stream = state.codex_streams.get(stream_id)
            if stream:
                stream['done'] = True
                stream['exit_code'] = 1
                stream['updated_at'] = time.time()
        return

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        if stream:
            stream['process'] = process

    stdout_thread = threading.Thread(
        target=_stream_reader,
        args=(stream_id, process.stdout, 'output'),
        daemon=True
    )
    stderr_thread = threading.Thread(
        target=_stream_reader,
        args=(stream_id, process.stderr, 'error'),
        daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()

    exit_code = process.wait()
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        if stream:
            stream['done'] = True
            stream['exit_code'] = exit_code
            stream['updated_at'] = time.time()
            stream['process'] = None


def create_codex_stream(session_id, prompt):
    stream_id = uuid.uuid4().hex
    stream = {
        'id': stream_id,
        'session_id': session_id,
        'output': '',
        'error': '',
        'done': False,
        'saved': False,
        'exit_code': None,
        'cancelled': False,
        'process': None,
        'created_at': time.time(),
        'updated_at': time.time()
    }
    with state.codex_streams_lock:
        state.codex_streams[stream_id] = stream

    thread = threading.Thread(
        target=_run_codex_stream,
        args=(stream_id, prompt),
        daemon=True
    )
    thread.start()
    return stream_id


def get_codex_stream(stream_id):
    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        return deepcopy(stream) if stream else None


def read_codex_stream(stream_id, output_offset=0, error_offset=0):
    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        if not stream:
            return None
        output = stream['output']
        error = stream['error']
        data = {
            'output': output[output_offset:],
            'error': error[error_offset:],
            'output_length': len(output),
            'error_length': len(error),
            'done': stream['done'],
            'exit_code': stream['exit_code'],
            'saved': stream.get('saved', False),
            'session_id': stream['session_id']
        }
        return data


def finalize_codex_stream(stream_id):
    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        if not stream or stream.get('saved') or not stream.get('done'):
            return None
        stream['saved'] = True
        output = (stream.get('output') or '').strip()
        error = (stream.get('error') or '').strip()
        session_id = stream.get('session_id')
        exit_code = stream.get('exit_code')

    if exit_code == 0:
        return append_message(session_id, 'assistant', output)
    message_text = error or output or 'Codex 실행에 실패했습니다.'
    return append_message(session_id, 'error', message_text)


def stop_codex_stream(stream_id):
    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        if not stream:
            return None
        if stream.get('cancelled'):
            return {'status': 'already_cancelled'}
        stream['cancelled'] = True
        stream['updated_at'] = time.time()
        process = stream.get('process')
        session_id = stream.get('session_id')
        output = (stream.get('output') or '').strip()
        error = (stream.get('error') or '').strip()

    if process and process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass

    message_text = None
    if output or error:
        combined = output or error
        if output and error:
            combined = f"{output}\n{error}"
        message_text = f"{combined}\n\n[사용자 중지]"
    else:
        message_text = '사용자에 의해 중지되었습니다.'

    saved_message = append_message(session_id, 'error', message_text)

    with state.codex_streams_lock:
        stream = state.codex_streams.get(stream_id)
        if stream:
            stream['saved'] = True
            stream['done'] = True
            stream['exit_code'] = 130
            stream['updated_at'] = time.time()
    return {'status': 'stopped', 'saved_message': saved_message}


def cleanup_codex_streams():
    now = time.time()
    stale_ids = []
    with state.codex_streams_lock:
        for stream_id, stream in state.codex_streams.items():
            if not stream.get('done'):
                continue
            if now - stream.get('updated_at', now) > CODEX_STREAM_TTL_SECONDS:
                stale_ids.append(stream_id)
        for stream_id in stale_ids:
            state.codex_streams.pop(stream_id, None)
