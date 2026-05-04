"""Persistent PTY-backed terminal sessions for the Codex web UI."""

from __future__ import annotations

import atexit
import errno
import os
import pty
import select
import signal
import struct
import subprocess
import threading
import time
import uuid
from codecs import getincrementaldecoder
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import file_browser

_TERMINAL_DEFAULT_COLS = 120
_TERMINAL_DEFAULT_ROWS = 32
_TERMINAL_MIN_COLS = 40
_TERMINAL_MIN_ROWS = 10
_TERMINAL_MAX_COLS = 240
_TERMINAL_MAX_ROWS = 80
_TERMINAL_READ_CHUNK_BYTES = 32 * 1024
_TERMINAL_MAX_OUTPUT_CHARS = 1_000_000
_TERMINAL_CLOSE_WAIT_SECONDS = 1.2
_TERMINAL_SELECT_TIMEOUT_SECONDS = 0.2
_TERMINAL_STARTUP_GRACE_SECONDS = 0.2
_TERMINAL_STREAM_HEARTBEAT_SECONDS = 10.0

_ROOT_DISPLAY_LABELS = {
    file_browser.BROWSER_ROOT_SERVER: '$server',
    file_browser.BROWSER_ROOT_WORKSPACE: '$workspace',
}

_SESSIONS_LOCK = threading.Lock()
_TERMINAL_SESSIONS: dict[str, '_TerminalSession'] = {}


class TerminalSessionError(RuntimeError):
    """Controlled error for terminal API responses."""

    def __init__(self, message, *, error_code='terminal_session_error', status_code=400):
        super().__init__(str(message))
        self.error_code = str(error_code or 'terminal_session_error')
        self.status_code = int(status_code)


@dataclass
class _TerminalSession:
    id: str
    root: str
    root_path: str
    path: str
    cwd: str
    display_path: str
    title: str
    shell: str
    cols: int
    rows: int
    created_ts: float
    updated_ts: float
    last_output_ts: float
    output_base_offset: int = 0
    output_buffer: str = ''
    process_running: bool = True
    exit_code: int | None = None
    launcher_exit_code: int | None = None
    closing: bool = False
    stream_seq: int = 0
    master_fd: int | None = field(default=None, repr=False)
    process: subprocess.Popen | None = field(default=None, repr=False)
    reader_thread: threading.Thread | None = field(default=None, repr=False)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    stream_condition: threading.Condition = field(init=False, repr=False)

    def __post_init__(self):
        self.stream_condition = threading.Condition(self.lock)


def _format_timestamp(value):
    timestamp = float(value or 0)
    if timestamp <= 0:
        return ''
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().isoformat(timespec='seconds')


def _normalize_dimension(value, default, minimum, maximum):
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = int(default)
    return max(int(minimum), min(int(maximum), numeric))


def _normalize_cols(value):
    return _normalize_dimension(value, _TERMINAL_DEFAULT_COLS, _TERMINAL_MIN_COLS, _TERMINAL_MAX_COLS)


def _normalize_rows(value):
    return _normalize_dimension(value, _TERMINAL_DEFAULT_ROWS, _TERMINAL_MIN_ROWS, _TERMINAL_MAX_ROWS)


def _format_display_path(root_key, relative_path=''):
    prefix = _ROOT_DISPLAY_LABELS.get(root_key, '$workspace')
    normalized_path = file_browser._normalize_relative_path(relative_path)
    return f'{prefix}/{normalized_path}' if normalized_path else prefix


def _resolve_terminal_directory(root_key=None, relative_path=''):
    normalized_root, root_path = file_browser._normalize_root_key(root_key)
    normalized_path = file_browser._normalize_relative_path(relative_path)
    target_path = file_browser._resolve_target_path(root_path, normalized_path)
    if not target_path.exists():
        raise TerminalSessionError(
            '터미널을 열 폴더를 찾을 수 없습니다.',
            error_code='path_not_found',
            status_code=404,
        )
    if target_path.is_dir():
        directory_path = target_path
    elif target_path.is_file():
        directory_path = target_path.parent
    else:
        raise TerminalSessionError(
            '터미널은 폴더 기준으로만 열 수 있습니다.',
            error_code='not_directory',
            status_code=400,
        )
    relative_directory = file_browser._to_relative_path(root_path, directory_path)
    return normalized_root, root_path, relative_directory, directory_path


def _iter_shell_paths():
    candidates = [os.environ.get('SHELL'), '/bin/bash', '/bin/sh']
    seen: set[str] = set()
    for candidate in candidates:
        text = str(candidate or '').strip()
        if not text:
            continue
        path = Path(text)
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        shell_path = str(path)
        if shell_path in seen:
            continue
        seen.add(shell_path)
        yield shell_path
    if seen:
        return
    raise TerminalSessionError(
        '실행 가능한 shell을 찾을 수 없습니다.',
        error_code='shell_not_found',
        status_code=500,
    )


def _build_shell_commands(shell_path):
    shell_name = Path(shell_path).name.lower()
    commands = []
    seen: set[tuple[str, ...]] = set()

    def append_command(*args):
        command = [shell_path, *args]
        command_key = tuple(command)
        if command_key in seen:
            return
        seen.add(command_key)
        commands.append(command)

    if shell_name == 'bash':
        bashrc_path = _ensure_shell_startup_files() / 'bashrc'
        append_command('--noprofile', '--rcfile', str(bashrc_path), '-i')
        append_command('--noprofile', '--norc', '-i')
        append_command('-i')
        append_command('--login', '-i')
        return commands
    if shell_name == 'zsh':
        append_command('-i')
        append_command('-i', '-l')
        return commands
    append_command('-i')
    return commands


def _iter_shell_launches():
    for shell_path in _iter_shell_paths():
        for command in _build_shell_commands(shell_path):
            yield shell_path, command


def _apply_window_size(fd, rows, cols):
    packed = struct.pack('HHHH', int(rows), int(cols), 0, 0)
    try:
        import fcntl
        import termios

        fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)
    except Exception as exc:  # noqa: BLE001
        raise TerminalSessionError(
            f'터미널 크기를 설정하지 못했습니다: {exc}',
            error_code='resize_failed',
            status_code=500,
        ) from exc


_TERMINAL_COLOR_ANSI = '38;5;67'
_TERMINAL_COLOR_ZSH = '67'
_BASH_DIRECTORY_PROMPT = rf'\[\033[{_TERMINAL_COLOR_ANSI}m\]\w\[\033[0m\]> '
_ZSH_DIRECTORY_PROMPT = f'%F{{{_TERMINAL_COLOR_ZSH}}}%~%f> '
_SH_DIRECTORY_PROMPT = f'\033[{_TERMINAL_COLOR_ANSI}m${{PWD}}\033[0m> '
_LS_DIRECTORY_COLORS = f'di={_TERMINAL_COLOR_ANSI}'
_BSD_LS_COLORS = 'exfxcxdxbxegedabagacad'
_SHELL_STARTUP_LOCK = threading.Lock()
_SHELL_STARTUP_READY = False
_SHELL_STARTUP_PATH: Path | None = None


def _terminal_startup_directory():
    return Path(os.environ.get('CODEX_TERMINAL_STARTUP_DIR') or '/tmp/codex-web-terminal')


def _common_shell_startup_script():
    return f"""export LS_COLORS="${{LS_COLORS:-{_LS_DIRECTORY_COLORS}}}"
export CLICOLOR="${{CLICOLOR:-1}}"
export LSCOLORS="${{LSCOLORS:-{_BSD_LS_COLORS}}}"
if ls --color=auto -d . >/dev/null 2>&1; then
    alias ls='ls --color=auto'
elif ls -G -d . >/dev/null 2>&1; then
    alias ls='ls -G'
fi
"""


def _build_shell_startup_files():
    common_setup = _common_shell_startup_script()
    return {
        'bashrc': f'{common_setup}PS1=\'{_BASH_DIRECTORY_PROMPT}\'\nPROMPT_COMMAND=\n',
        '.zshrc': f'{common_setup}PS1=\'{_ZSH_DIRECTORY_PROMPT}\'\nPROMPT="${{PS1}}"\n',
        'shrc': f'{common_setup}PS1=\'{_SH_DIRECTORY_PROMPT}\'\nPROMPT_COMMAND=\n',
    }


def _ensure_shell_startup_files():
    global _SHELL_STARTUP_PATH, _SHELL_STARTUP_READY

    startup_directory = _terminal_startup_directory()
    with _SHELL_STARTUP_LOCK:
        if _SHELL_STARTUP_READY and _SHELL_STARTUP_PATH == startup_directory and startup_directory.exists():
            return startup_directory
        startup_directory.mkdir(parents=True, exist_ok=True)
        os.chmod(startup_directory, 0o700)
        for filename, content in _build_shell_startup_files().items():
            startup_file = startup_directory / filename
            startup_file.write_text(content, encoding='utf-8')
            os.chmod(startup_file, 0o600)
        _SHELL_STARTUP_PATH = startup_directory
        _SHELL_STARTUP_READY = True
    return startup_directory


def _build_prompt_environment(shell_path=''):
    shell_name = Path(str(shell_path or '')).name.lower()
    if shell_name == 'zsh':
        return {
            'PS1': _ZSH_DIRECTORY_PROMPT,
            'PROMPT': _ZSH_DIRECTORY_PROMPT,
        }
    if shell_name == 'bash':
        return {
            'PS1': _BASH_DIRECTORY_PROMPT,
            'PROMPT_COMMAND': '',
        }
    return {
        'PS1': _SH_DIRECTORY_PROMPT,
        'PROMPT_COMMAND': '',
    }


def _build_shell_color_environment(shell_path=''):
    shell_name = Path(str(shell_path or '')).name.lower()
    startup_directory = _ensure_shell_startup_files()
    environment = {
        'LS_COLORS': _LS_DIRECTORY_COLORS,
        'CLICOLOR': '1',
        'LSCOLORS': _BSD_LS_COLORS,
    }
    if shell_name == 'zsh':
        environment['ZDOTDIR'] = str(startup_directory)
    elif shell_name not in {'bash'}:
        environment['ENV'] = str(startup_directory / 'shrc')
    return environment


def _build_environment(shell_path=''):
    environment = os.environ.copy()
    environment.update({
        'TERM': 'xterm-256color',
        'COLORTERM': 'truecolor',
        'BASH_SILENCE_DEPRECATION_WARNING': '1',
        'PYTHONUNBUFFERED': '1',
        'CODEX_AGENT_TERMINAL': '1',
    })
    environment.update(_build_shell_color_environment(shell_path))
    environment.update(_build_prompt_environment(shell_path))
    return environment


def _spawn_terminal_process(command, directory_path, cols, rows):
    try:
        master_fd, slave_fd = pty.openpty()
    except OSError as exc:
        raise TerminalSessionError(
            f'PTY를 생성하지 못했습니다: {exc}',
            error_code='pty_open_failed',
            status_code=500,
        ) from exc

    process = None
    try:
        _apply_window_size(slave_fd, rows, cols)
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=str(directory_path),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=_build_environment(command[0] if command else ''),
            close_fds=True,
            start_new_session=True,
        )
        return master_fd, process
    except OSError as exc:
        try:
            os.close(master_fd)
        except OSError:
            pass
        raise TerminalSessionError(
            f'터미널 shell을 시작하지 못했습니다: {exc}',
            error_code='shell_start_failed',
            status_code=500,
        ) from exc
    finally:
        try:
            os.close(slave_fd)
        except OSError:
            pass


def _safe_close_fd(fd):
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _close_spawned_process(master_fd, process):
    _terminate_process(process)
    _safe_close_fd(master_fd)


def _open_terminal_process(directory_path, cols, rows):
    attempts = []
    for shell_path, command in _iter_shell_launches():
        master_fd, process = _spawn_terminal_process(command, directory_path, cols, rows)
        time.sleep(_TERMINAL_STARTUP_GRACE_SECONDS)
        if process.poll() is None:
            return shell_path, command, master_fd, process
        attempts.append(f'{" ".join(command)} -> {process.returncode}')
        _close_spawned_process(master_fd, process)

    attempted_commands = '; '.join(attempts[:4])
    raise TerminalSessionError(
        f'터미널 shell이 즉시 종료되었습니다. {attempted_commands}',
        error_code='shell_exited_immediately',
        status_code=500,
    )


def _build_session_title(relative_path='', root_key=file_browser.BROWSER_ROOT_WORKSPACE):
    normalized_path = file_browser._normalize_relative_path(relative_path)
    if not normalized_path:
        return _ROOT_DISPLAY_LABELS.get(root_key, '$workspace')
    return Path(normalized_path).name or normalized_path


def _trim_output_buffer(session):
    buffer_length = len(session.output_buffer)
    overflow = buffer_length - _TERMINAL_MAX_OUTPUT_CHARS
    if overflow <= 0:
        return
    session.output_buffer = session.output_buffer[overflow:]
    session.output_base_offset += overflow


def _append_output(session, text):
    if not text:
        return
    session.output_buffer += text
    session.last_output_ts = time.time()
    session.updated_ts = session.last_output_ts
    _trim_output_buffer(session)
    _notify_session_update_locked(session)


def _capture_launcher_exit_code(session):
    process = session.process
    if process is None:
        return session.launcher_exit_code
    exit_code = process.poll()
    if exit_code is None:
        return session.launcher_exit_code
    session.launcher_exit_code = int(exit_code)
    return session.launcher_exit_code


def _notify_session_update_locked(session):
    session.stream_seq += 1
    session.stream_condition.notify_all()


def _mark_session_stopped(session, exit_code=None, *, close_master=False):
    resolved_exit_code = int(exit_code) if exit_code is not None else _capture_launcher_exit_code(session)
    session.process_running = False
    if resolved_exit_code is not None:
        session.exit_code = int(resolved_exit_code)
    session.updated_ts = time.time()
    master_fd = None
    if close_master:
        master_fd = session.master_fd
        session.master_fd = None
    _notify_session_update_locked(session)
    return master_fd


def _sync_process_state(session):
    observed_exit_code = _capture_launcher_exit_code(session)
    if not session.process_running and session.exit_code is None and observed_exit_code is not None:
        session.exit_code = int(observed_exit_code)


def _build_session_summary(session):
    output_length = session.output_base_offset + len(session.output_buffer)
    return {
        'id': session.id,
        'root': session.root,
        'root_path': session.root_path,
        'path': session.path,
        'cwd': session.cwd,
        'display_path': session.display_path,
        'title': session.title,
        'shell': session.shell,
        'cols': session.cols,
        'rows': session.rows,
        'process_running': session.process_running,
        'exit_code': session.exit_code,
        'created_at': _format_timestamp(session.created_ts),
        'updated_at': _format_timestamp(session.updated_ts),
        'last_output_at': _format_timestamp(session.last_output_ts),
        'output_base_offset': session.output_base_offset,
        'output_length': output_length,
    }


def _build_session_snapshot(session, offset=None):
    summary = _build_session_summary(session)
    base_offset = session.output_base_offset
    output_buffer = session.output_buffer
    output_length = summary['output_length']

    reset = False
    start_offset = base_offset
    if offset is None:
        reset = True
    else:
        try:
            requested_offset = int(offset)
        except (TypeError, ValueError):
            requested_offset = base_offset
        if requested_offset < base_offset or requested_offset > output_length:
            reset = True
        else:
            start_offset = requested_offset
    if reset:
        output = output_buffer
        start_offset = base_offset
    else:
        output = output_buffer[start_offset - base_offset:]

    summary.update({
        'reset': reset,
        'output_offset': start_offset,
        'output': output,
    })
    return summary


def iter_terminal_session_events(session_id, offset=None, heartbeat_seconds=_TERMINAL_STREAM_HEARTBEAT_SECONDS):
    terminal_id = str(session_id or '').strip()
    if not terminal_id:
        raise TerminalSessionError(
            '터미널 세션 ID가 비어 있습니다.',
            error_code='invalid_session_id',
            status_code=400,
        )

    with _SESSIONS_LOCK:
        existing_session = _TERMINAL_SESSIONS.get(terminal_id)
    if existing_session is None:
        raise TerminalSessionError(
            '터미널 세션을 찾을 수 없습니다.',
            error_code='session_not_found',
            status_code=404,
        )

    try:
        requested_offset = int(offset)
    except (TypeError, ValueError):
        requested_offset = 0
    requested_offset = max(0, requested_offset)
    heartbeat_timeout = max(0.5, float(heartbeat_seconds or _TERMINAL_STREAM_HEARTBEAT_SECONDS))

    def _event_iterator():
        last_offset = requested_offset
        last_stream_seq = -1
        emit_initial_snapshot = True
        while True:
            with _SESSIONS_LOCK:
                session = _TERMINAL_SESSIONS.get(terminal_id)
            if session is None:
                yield {
                    'event': 'end',
                    'data': {
                        'id': terminal_id,
                        'closed': True,
                        'error_code': 'session_not_found',
                    },
                }
                return

            payload = None
            end_payload = None
            heartbeat_payload = None

            with session.stream_condition:
                snapshot = _build_session_snapshot(session, offset=last_offset)
                current_stream_seq = session.stream_seq
                should_emit = (
                    emit_initial_snapshot
                    or snapshot['reset']
                    or bool(snapshot['output'])
                    or current_stream_seq != last_stream_seq
                )
                if should_emit:
                    emit_initial_snapshot = False
                    last_stream_seq = current_stream_seq
                    last_offset = snapshot['output_length']
                    payload = {'data': snapshot}
                    if not session.process_running:
                        end_payload = {
                            'event': 'end',
                            'data': _build_session_summary(session),
                        }
                else:
                    session.stream_condition.wait(timeout=heartbeat_timeout)
                    if session.stream_seq == current_stream_seq:
                        heartbeat_payload = {
                            'event': 'ping',
                            'data': {
                                'id': terminal_id,
                                'ts': _format_timestamp(time.time()),
                            },
                        }

            if payload is not None:
                yield payload
                if end_payload is not None:
                    yield end_payload
                    return
                continue

            if heartbeat_payload is not None:
                yield heartbeat_payload

    return _event_iterator()


def _read_terminal_output(session_id):
    decoder = getincrementaldecoder('utf-8')('replace')
    while True:
        with _SESSIONS_LOCK:
            session = _TERMINAL_SESSIONS.get(session_id)
        if session is None:
            return

        with session.lock:
            master_fd = session.master_fd
            process = session.process
            closing = session.closing
        if master_fd is None:
            return
        if closing and process is None:
            return

        try:
            ready, _, _ = select.select([master_fd], [], [], _TERMINAL_SELECT_TIMEOUT_SECONDS)
        except (OSError, ValueError):
            ready = []

        if not ready:
            with session.lock:
                _sync_process_state(session)
                process_running = session.process_running
                closing = session.closing
            if closing and not process_running:
                return
            continue

        try:
            chunk = os.read(master_fd, _TERMINAL_READ_CHUNK_BYTES)
        except OSError as exc:
            if exc.errno in (errno.EINTR, errno.EAGAIN):
                continue
            with session.lock:
                _append_output(session, decoder.decode(b'', final=True))
                closed_fd = _mark_session_stopped(session, close_master=True)
            _safe_close_fd(closed_fd)
            return

        if chunk:
            decoded = decoder.decode(chunk)
            with session.lock:
                _append_output(session, decoded)
                _sync_process_state(session)
            continue

        with session.lock:
            _append_output(session, decoder.decode(b'', final=True))
            closed_fd = _mark_session_stopped(session, close_master=True)
        _safe_close_fd(closed_fd)
        return


def _start_reader_thread(session):
    thread = threading.Thread(
        target=_read_terminal_output,
        args=(session.id,),
        name=f'codex-terminal-{session.id[:8]}',
        daemon=True,
    )
    session.reader_thread = thread
    thread.start()


def create_terminal_session(root_key=None, relative_path='', cols=None, rows=None):
    normalized_root, root_path, resolved_path, directory_path = _resolve_terminal_directory(
        root_key=root_key,
        relative_path=relative_path,
    )
    normalized_cols = _normalize_cols(cols)
    normalized_rows = _normalize_rows(rows)
    shell_path, _command, master_fd, process = _open_terminal_process(
        directory_path,
        normalized_cols,
        normalized_rows,
    )

    now = time.time()
    session = _TerminalSession(
        id=uuid.uuid4().hex,
        root=normalized_root,
        root_path=str(root_path),
        path=resolved_path,
        cwd=str(directory_path),
        display_path=_format_display_path(normalized_root, resolved_path),
        title=_build_session_title(resolved_path, normalized_root),
        shell=Path(shell_path).name,
        cols=normalized_cols,
        rows=normalized_rows,
        created_ts=now,
        updated_ts=now,
        last_output_ts=now,
        master_fd=master_fd,
        process=process,
    )

    with _SESSIONS_LOCK:
        _TERMINAL_SESSIONS[session.id] = session

    _start_reader_thread(session)
    return _build_session_snapshot(session)


def list_terminal_sessions():
    with _SESSIONS_LOCK:
        sessions = list(_TERMINAL_SESSIONS.values())
    sessions.sort(key=lambda item: item.created_ts)
    summaries = []
    for session in sessions:
        with session.lock:
            _sync_process_state(session)
            summaries.append(_build_session_summary(session))
    return {'sessions': summaries}


def read_terminal_session(session_id, offset=None):
    terminal_id = str(session_id or '').strip()
    if not terminal_id:
        raise TerminalSessionError(
            '터미널 세션 ID가 비어 있습니다.',
            error_code='invalid_session_id',
            status_code=400,
        )
    with _SESSIONS_LOCK:
        session = _TERMINAL_SESSIONS.get(terminal_id)
    if session is None:
        raise TerminalSessionError(
            '터미널 세션을 찾을 수 없습니다.',
            error_code='session_not_found',
            status_code=404,
        )
    with session.lock:
        _sync_process_state(session)
        return _build_session_snapshot(session, offset=offset)


def write_terminal_input(session_id, data=''):
    terminal_id = str(session_id or '').strip()
    text = str(data or '')
    if not terminal_id:
        raise TerminalSessionError(
            '터미널 세션 ID가 비어 있습니다.',
            error_code='invalid_session_id',
            status_code=400,
        )
    if not text:
        raise TerminalSessionError(
            '전송할 입력이 비어 있습니다.',
            error_code='empty_input',
            status_code=400,
        )

    with _SESSIONS_LOCK:
        session = _TERMINAL_SESSIONS.get(terminal_id)
    if session is None:
        raise TerminalSessionError(
            '터미널 세션을 찾을 수 없습니다.',
            error_code='session_not_found',
            status_code=404,
        )

    terminal_error = None
    closed_fd = None
    with session.lock:
        _sync_process_state(session)
        if not session.process_running:
            raise TerminalSessionError(
                '종료된 터미널에는 입력할 수 없습니다.',
                error_code='session_not_running',
                status_code=409,
            )
        master_fd = session.master_fd
        if master_fd is None:
            raise TerminalSessionError(
                '터미널 연결이 이미 닫혔습니다.',
                error_code='session_closed',
                status_code=409,
            )
        try:
            os.write(master_fd, text.encode('utf-8', errors='replace'))
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.EBADF):
                closed_fd = _mark_session_stopped(session, close_master=True)
                if exc.errno == errno.EBADF:
                    terminal_error = TerminalSessionError(
                        '터미널 연결이 이미 닫혔습니다.',
                        error_code='session_closed',
                        status_code=409,
                    )
                else:
                    terminal_error = TerminalSessionError(
                        '종료된 터미널에는 입력할 수 없습니다.',
                        error_code='session_not_running',
                        status_code=409,
                    )
            else:
                raise TerminalSessionError(
                    f'터미널 입력 전송에 실패했습니다: {exc}',
                    error_code='input_write_failed',
                    status_code=500,
                ) from exc
        if terminal_error is not None:
            pass
        else:
            session.updated_ts = time.time()
            return _build_session_summary(session)
    _safe_close_fd(closed_fd)
    if terminal_error is not None:
        raise terminal_error
    raise RuntimeError('unexpected terminal input state')


def resize_terminal_session(session_id, cols=None, rows=None):
    terminal_id = str(session_id or '').strip()
    if not terminal_id:
        raise TerminalSessionError(
            '터미널 세션 ID가 비어 있습니다.',
            error_code='invalid_session_id',
            status_code=400,
        )

    with _SESSIONS_LOCK:
        session = _TERMINAL_SESSIONS.get(terminal_id)
    if session is None:
        raise TerminalSessionError(
            '터미널 세션을 찾을 수 없습니다.',
            error_code='session_not_found',
            status_code=404,
        )

    normalized_cols = _normalize_cols(cols)
    normalized_rows = _normalize_rows(rows)
    with session.lock:
        master_fd = session.master_fd
        if master_fd is None:
            raise TerminalSessionError(
                '터미널 연결이 이미 닫혔습니다.',
                error_code='session_closed',
                status_code=409,
            )
        _apply_window_size(master_fd, normalized_rows, normalized_cols)
        process = session.process
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGWINCH)
            except OSError:
                pass
        session.cols = normalized_cols
        session.rows = normalized_rows
        session.updated_ts = time.time()
        _sync_process_state(session)
        _notify_session_update_locked(session)
        return _build_session_summary(session)


def _terminate_process(process):
    if process is None:
        return None
    exit_code = process.poll()
    if exit_code is not None:
        return int(exit_code)

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        return int(process.wait(timeout=_TERMINAL_CLOSE_WAIT_SECONDS))
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        return int(process.wait(timeout=_TERMINAL_CLOSE_WAIT_SECONDS))
    except subprocess.TimeoutExpired:
        return process.poll()


def _close_terminal_session_object(session):
    with session.lock:
        if session.closing:
            process = session.process
            reader_thread = session.reader_thread
            master_fd = session.master_fd
        else:
            session.closing = True
            _notify_session_update_locked(session)
            process = session.process
            reader_thread = session.reader_thread
            master_fd = session.master_fd

    exit_code = _terminate_process(process)
    _safe_close_fd(master_fd)

    if reader_thread is not None and reader_thread.is_alive():
        reader_thread.join(timeout=_TERMINAL_CLOSE_WAIT_SECONDS)

    with session.lock:
        session.master_fd = None
        session.process = None
        session.reader_thread = None
        session.process_running = False
        if exit_code is not None:
            session.launcher_exit_code = int(exit_code)
            session.exit_code = int(exit_code)
        session.updated_ts = time.time()
        _notify_session_update_locked(session)
        return _build_session_summary(session)


def close_terminal_session(session_id):
    terminal_id = str(session_id or '').strip()
    if not terminal_id:
        raise TerminalSessionError(
            '터미널 세션 ID가 비어 있습니다.',
            error_code='invalid_session_id',
            status_code=400,
        )

    with _SESSIONS_LOCK:
        session = _TERMINAL_SESSIONS.pop(terminal_id, None)
    if session is None:
        raise TerminalSessionError(
            '터미널 세션을 찾을 수 없습니다.',
            error_code='session_not_found',
            status_code=404,
        )

    summary = _close_terminal_session_object(session)
    summary['closed'] = True
    return summary


def shutdown_terminal_sessions():
    with _SESSIONS_LOCK:
        sessions = list(_TERMINAL_SESSIONS.values())
        _TERMINAL_SESSIONS.clear()
    for session in sessions:
        try:
            _close_terminal_session_object(session)
        except Exception:  # noqa: BLE001
            continue


atexit.register(shutdown_terminal_sessions)
