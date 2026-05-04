from __future__ import annotations

import errno
import io
import os
import sys
import time
from pathlib import Path
from zipfile import ZipFile

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent import codex_app
from codex_agent.blueprints import codex_chat as codex_chat_blueprint
from codex_agent.services import file_browser, terminal_sessions

CODEX_APP_ROOT = Path(codex_app.__file__).resolve().parent


@pytest.fixture(autouse=True)
def _cleanup_terminal_sessions():
    terminal_sessions.shutdown_terminal_sessions()
    yield
    terminal_sessions.shutdown_terminal_sessions()


@pytest.fixture
def isolated_browser_roots(tmp_path, monkeypatch):
    server_root = (tmp_path / 'server').resolve()
    workspace_root = (tmp_path / 'workspace').resolve()
    server_root.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(file_browser, '_get_server_root', lambda: server_root)
    monkeypatch.setattr(file_browser, 'WORKSPACE_DIR', workspace_root)

    return {
        'server_root': server_root,
        'workspace_root': workspace_root,
    }


@pytest.fixture
def browser_test_client(isolated_browser_roots, monkeypatch):
    monkeypatch.setattr(codex_app, 'ensure_usage_snapshot_background_worker', lambda: None)
    monkeypatch.setattr(codex_app, 'ensure_pending_queue_background_worker', lambda: None)
    monkeypatch.setattr(codex_chat_blueprint, 'CODEX_ENABLE_FILES_API', True)
    app = codex_app.create_codex_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def _wait_for_terminal_snapshot(fetch_snapshot, predicate, timeout_seconds=6.0):
    deadline = time.time() + timeout_seconds
    last_snapshot = None
    while time.time() < deadline:
        last_snapshot = fetch_snapshot()
        if predicate(last_snapshot):
            return last_snapshot
        time.sleep(0.05)
    raise AssertionError(f'terminal condition not met before timeout; last snapshot={last_snapshot!r}')


def test_list_directory_returns_sorted_entries(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'src').mkdir(parents=True, exist_ok=True)
    (server_root / 'README.md').write_text('hello', encoding='utf-8')

    result = file_browser.list_directory(root_key='server', relative_path='')

    assert result['root'] == 'server'
    assert result['path'] == ''
    assert len(result['entries']) == 2
    assert result['entries'][0]['type'] == 'dir'
    assert result['entries'][0]['path'] == 'src'
    assert result['entries'][1]['type'] == 'file'
    assert result['entries'][1]['path'] == 'README.md'


def test_read_file_detects_html_and_script(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'index.html').write_text('<html><body>ok</body></html>', encoding='utf-8')
    (server_root / 'script.js').write_text('const answer = 42;', encoding='utf-8')

    html_result = file_browser.read_file(root_key='server', relative_path='index.html')
    script_result = file_browser.read_file(root_key='server', relative_path='script.js')

    assert html_result['is_html'] is True
    assert html_result['is_script'] is False
    assert html_result['language'] == 'html'
    assert '<html>' in html_result['content']

    assert script_result['is_html'] is False
    assert script_result['is_script'] is True
    assert script_result['language'] == 'javascript'
    assert 'answer = 42' in script_result['content']


def test_read_file_marks_binary_content(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'raw.bin').write_bytes(b'\x00\x01\x02\x03')

    result = file_browser.read_file(root_key='server', relative_path='raw.bin')

    assert result['is_binary'] is True
    assert result['content'] == ''
    assert result['line_count'] == 0


def test_read_file_reports_editable_text_metadata(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    target = server_root / 'notes.md'
    target.write_text('# hello\nworld\n', encoding='utf-8')

    result = file_browser.read_file(root_key='server', relative_path='notes.md')

    assert result['editable'] is True
    assert result['modified_at'] >= 0
    assert str(result['modified_ns']).isdigit()


def test_write_file_updates_content_and_returns_latest_metadata(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    target = server_root / 'script.py'
    target.write_text('print("before")\n', encoding='utf-8')

    original = file_browser.read_file(root_key='server', relative_path='script.py')
    updated = file_browser.write_file(
        root_key='server',
        relative_path='script.py',
        content='print("after")\n',
        expected_modified_ns=original['modified_ns'],
    )

    assert updated['saved'] is True
    assert updated['editable'] is True
    assert 'after' in updated['content']
    assert target.read_text(encoding='utf-8') == 'print("after")\n'
    assert str(updated['modified_ns']).isdigit()


def test_write_file_rejects_non_editable_extension(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'diagram.svg').write_text('<svg></svg>', encoding='utf-8')

    with pytest.raises(file_browser.FileBrowserError) as exc_info:
        file_browser.write_file(
            root_key='server',
            relative_path='diagram.svg',
            content='<svg><rect /></svg>',
        )

    assert exc_info.value.error_code == 'not_editable'


def test_list_directory_blocks_parent_path_escape(isolated_browser_roots):
    with pytest.raises(file_browser.FileBrowserError) as exc_info:
        file_browser.list_directory(root_key='server', relative_path='../')

    assert exc_info.value.error_code == 'invalid_path'


def test_build_download_payload_returns_zip_for_multiple_files(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'docs').mkdir(parents=True, exist_ok=True)
    (server_root / 'docs' / 'guide.txt').write_text('guide', encoding='utf-8')
    (server_root / 'README.md').write_text('# hello', encoding='utf-8')

    result = file_browser.build_download_payload(
        root_key='server',
        relative_paths=['README.md', 'docs/guide.txt'],
    )

    assert result['is_archive'] is True
    assert result['mime_type'] == 'application/zip'
    with ZipFile(io.BytesIO(result['content'])) as archive:
        assert sorted(archive.namelist()) == ['README.md', 'docs/guide.txt']
        assert archive.read('README.md').decode('utf-8') == '# hello'
        assert archive.read('docs/guide.txt').decode('utf-8') == 'guide'


def test_delete_files_rolls_back_when_move_fails(isolated_browser_roots, monkeypatch):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'a.txt').write_text('alpha', encoding='utf-8')
    (server_root / 'b.txt').write_text('beta', encoding='utf-8')

    original_move = file_browser.shutil.move
    call_count = {'value': 0}

    def flaky_move(source, destination):
        call_count['value'] += 1
        if call_count['value'] == 2:
            raise OSError('simulated delete failure')
        return original_move(source, destination)

    monkeypatch.setattr(file_browser.shutil, 'move', flaky_move)

    with pytest.raises(file_browser.FileBrowserError) as exc_info:
        file_browser.delete_files(root_key='server', relative_paths=['a.txt', 'b.txt'])

    assert exc_info.value.error_code == 'delete_error'
    assert (server_root / 'a.txt').read_text(encoding='utf-8') == 'alpha'
    assert (server_root / 'b.txt').read_text(encoding='utf-8') == 'beta'


def test_move_files_supports_rename_and_bulk_move(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'docs').mkdir(parents=True, exist_ok=True)
    (server_root / 'archive').mkdir(parents=True, exist_ok=True)
    (server_root / 'docs' / 'draft.txt').write_text('draft', encoding='utf-8')
    (server_root / 'docs' / 'note.txt').write_text('note', encoding='utf-8')

    renamed = file_browser.move_files(
        root_key='server',
        relative_paths=['docs/draft.txt'],
        destination_path='docs/final.txt',
    )
    assert renamed['moved'][0]['destination_path'] == 'docs/final.txt'
    assert not (server_root / 'docs' / 'draft.txt').exists()
    assert (server_root / 'docs' / 'final.txt').read_text(encoding='utf-8') == 'draft'

    moved = file_browser.move_files(
        root_key='server',
        relative_paths=['docs/final.txt', 'docs/note.txt'],
        destination_directory='archive',
    )
    assert moved['count'] == 2
    assert sorted(item['destination_path'] for item in moved['moved']) == [
        'archive/final.txt',
        'archive/note.txt',
    ]
    assert (server_root / 'archive' / 'final.txt').read_text(encoding='utf-8') == 'draft'
    assert (server_root / 'archive' / 'note.txt').read_text(encoding='utf-8') == 'note'


def test_download_route_returns_attachment(browser_test_client, isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'report.txt').write_text('report body', encoding='utf-8')

    response = browser_test_client.post(
        '/api/codex/files/download',
        json={'root': 'server', 'paths': ['report.txt']},
    )

    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('text/plain')
    assert 'attachment;' in response.headers['Content-Disposition']
    assert response.data == b'report body'


def test_write_route_updates_file(browser_test_client, isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'notes.txt').write_text('before', encoding='utf-8')

    read_response = browser_test_client.post(
        '/api/codex/files/read',
        json={'root': 'server', 'path': 'notes.txt'},
    )
    assert read_response.status_code == 200
    read_payload = read_response.get_json()

    write_response = browser_test_client.post(
        '/api/codex/files/write',
        json={
            'root': 'server',
            'path': 'notes.txt',
            'content': 'after',
            'expected_modified_ns': read_payload['modified_ns'],
        },
    )

    assert write_response.status_code == 200
    payload = write_response.get_json()
    assert payload['saved'] is True
    assert payload['content'] == 'after'
    assert payload['editable'] is True
    assert (server_root / 'notes.txt').read_text(encoding='utf-8') == 'after'


def test_write_route_returns_conflict_when_file_changed(browser_test_client, isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    target = server_root / 'notes.txt'
    target.write_text('before', encoding='utf-8')

    read_response = browser_test_client.post(
        '/api/codex/files/read',
        json={'root': 'server', 'path': 'notes.txt'},
    )
    assert read_response.status_code == 200
    read_payload = read_response.get_json()

    target.write_text('changed elsewhere', encoding='utf-8')
    bumped_modified_ns = int(read_payload['modified_ns']) + 1_000_000_000
    os.utime(target, ns=(bumped_modified_ns, bumped_modified_ns))

    write_response = browser_test_client.post(
        '/api/codex/files/write',
        json={
            'root': 'server',
            'path': 'notes.txt',
            'content': 'after',
            'expected_modified_ns': read_payload['modified_ns'],
        },
    )

    assert write_response.status_code == 409
    payload = write_response.get_json()
    assert payload['error_code'] == 'modified_conflict'


def test_create_file_creates_blank_text_file(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'docs').mkdir(parents=True, exist_ok=True)

    created = file_browser.create_file(
        root_key='server',
        relative_path='docs/new-note.txt',
    )

    assert created['created'] is True
    assert created['path'] == 'docs/new-note.txt'
    assert created['content'] == ''
    assert created['editable'] is True
    assert (server_root / 'docs' / 'new-note.txt').read_text(encoding='utf-8') == ''


def test_delete_directory_removes_nested_folder(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    target = server_root / 'docs' / 'nested'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'guide.md').write_text('# guide\n', encoding='utf-8')

    result = file_browser.delete_directory(
        root_key='server',
        relative_path='docs/nested',
    )

    assert result['deleted_path'] == 'docs/nested'
    assert not target.exists()
    assert (server_root / 'docs').exists()


def test_create_route_creates_file(browser_test_client, isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'docs').mkdir(parents=True, exist_ok=True)

    response = browser_test_client.post(
        '/api/codex/files/create',
        json={'root': 'server', 'path': 'docs/from-route.py', 'content': 'print("ok")\n'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['created'] is True
    assert payload['content'] == 'print("ok")\n'
    assert (server_root / 'docs' / 'from-route.py').read_text(encoding='utf-8') == 'print("ok")\n'


def test_upload_route_saves_files_to_current_folder(browser_test_client, isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'docs').mkdir(parents=True, exist_ok=True)

    response = browser_test_client.post(
        '/api/codex/files/upload',
        data={
            'root': 'server',
            'path': 'docs',
            'files': [
                (io.BytesIO(b'alpha'), 'alpha.txt'),
                (io.BytesIO(b'beta'), 'beta.bin'),
            ],
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['count'] == 2
    assert sorted(item['path'] for item in payload['uploaded']) == ['docs/alpha.txt', 'docs/beta.bin']
    assert (server_root / 'docs' / 'alpha.txt').read_bytes() == b'alpha'
    assert (server_root / 'docs' / 'beta.bin').read_bytes() == b'beta'


def test_upload_route_rejects_existing_file(browser_test_client, isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'docs').mkdir(parents=True, exist_ok=True)
    (server_root / 'docs' / 'alpha.txt').write_text('existing', encoding='utf-8')

    response = browser_test_client.post(
        '/api/codex/files/upload',
        data={
            'root': 'server',
            'path': 'docs',
            'files': (io.BytesIO(b'new'), 'alpha.txt'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 409
    assert response.get_json()['error_code'] == 'path_conflict'
    assert (server_root / 'docs' / 'alpha.txt').read_text(encoding='utf-8') == 'existing'


def test_delete_directory_route_removes_folder(browser_test_client, isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    target = server_root / 'docs' / 'remove-me'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'child.txt').write_text('hello', encoding='utf-8')

    response = browser_test_client.post(
        '/api/codex/files/delete-directory',
        json={'root': 'server', 'path': 'docs/remove-me'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['deleted_path'] == 'docs/remove-me'
    assert not target.exists()


def test_terminal_session_supports_input_resize_and_close(isolated_browser_roots):
    workspace_root = isolated_browser_roots['workspace_root']
    terminal_dir = workspace_root / 'docs'
    terminal_dir.mkdir(parents=True, exist_ok=True)

    created = terminal_sessions.create_terminal_session(
        root_key='workspace',
        relative_path='docs',
        cols=90,
        rows=24,
    )

    assert created['path'] == 'docs'
    assert created['cwd'] == str(terminal_dir)
    assert created['cols'] == 90
    assert created['rows'] == 24
    session_id = created['id']

    terminal_sessions.write_terminal_input(session_id, 'printf "__terminal_ok__\\n"\n')

    snapshot = _wait_for_terminal_snapshot(
        lambda: terminal_sessions.read_terminal_session(session_id),
        lambda payload: '__terminal_ok__' in str(payload.get('output') or ''),
    )
    assert snapshot['process_running'] is True

    resized = terminal_sessions.resize_terminal_session(session_id, cols=110, rows=30)
    assert resized['cols'] == 110
    assert resized['rows'] == 30

    terminal_sessions.write_terminal_input(session_id, 'exit\n')
    exited = _wait_for_terminal_snapshot(
        lambda: terminal_sessions.read_terminal_session(session_id),
        lambda payload: payload.get('process_running') is False,
    )
    assert exited['exit_code'] == 0

    closed = terminal_sessions.close_terminal_session(session_id)
    assert closed['closed'] is True

    with pytest.raises(terminal_sessions.TerminalSessionError) as exc_info:
        terminal_sessions.read_terminal_session(session_id)
    assert exc_info.value.error_code == 'session_not_found'


def test_terminal_environment_uses_current_path_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv('CODEX_TERMINAL_STARTUP_DIR', str(tmp_path / 'terminal-startup'))

    bash_environment = terminal_sessions._build_environment('/bin/bash')
    zsh_environment = terminal_sessions._build_environment('/bin/zsh')
    sh_environment = terminal_sessions._build_environment('/bin/sh')

    assert bash_environment['PS1'] == r'\[\033[38;5;67m\]\w\[\033[0m\]> '
    assert bash_environment['PROMPT_COMMAND'] == ''
    assert zsh_environment['PS1'] == '%F{67}%~%f> '
    assert zsh_environment['PROMPT'] == '%F{67}%~%f> '
    assert sh_environment['PS1'] == '\033[38;5;67m${PWD}\033[0m> '
    assert sh_environment['PROMPT_COMMAND'] == ''
    assert bash_environment['LS_COLORS'] == 'di=38;5;67'
    assert bash_environment['CLICOLOR'] == '1'
    assert bash_environment['LSCOLORS'] == 'exfxcxdxbxegedabagacad'
    assert zsh_environment['ZDOTDIR'] == str(tmp_path / 'terminal-startup')
    assert sh_environment['ENV'] == str(tmp_path / 'terminal-startup' / 'shrc')
    assert bash_environment['CODEX_AGENT_TERMINAL'] == '1'

    startup_files = terminal_sessions._build_shell_startup_files()
    assert "alias ls='ls --color=auto'" in startup_files['bashrc']
    assert "alias ls='ls -G'" in startup_files['bashrc']

    bash_commands = terminal_sessions._build_shell_commands('/bin/bash')
    assert bash_commands[0][:3] == ['/bin/bash', '--noprofile', '--rcfile']


def test_open_terminal_process_retries_when_first_shell_exits_immediately(monkeypatch):
    class FakeProcess:
        def __init__(self, pid, poll_results):
            self.pid = pid
            self.returncode = None
            self._poll_results = list(poll_results)

        def poll(self):
            if self._poll_results:
                result = self._poll_results.pop(0)
            else:
                result = self.returncode
            if result is not None:
                self.returncode = int(result)
            return result

    launches = [
        ('/bin/bash', ['/bin/bash', '--noprofile', '--norc', '-i']),
        ('/bin/sh', ['/bin/sh', '-i']),
    ]
    attempts = []
    closed_attempts = []
    fake_processes = [
        FakeProcess(101, [0]),
        FakeProcess(202, [None]),
    ]
    fake_master_fds = [91, 92]

    monkeypatch.setattr(terminal_sessions, '_iter_shell_launches', lambda: iter(launches))
    monkeypatch.setattr(terminal_sessions.time, 'sleep', lambda *_args, **_kwargs: None)

    def fake_spawn(command, directory_path, cols, rows):
        attempt_index = len(attempts)
        attempts.append((command, Path(directory_path), cols, rows))
        return fake_master_fds[attempt_index], fake_processes[attempt_index]

    monkeypatch.setattr(terminal_sessions, '_spawn_terminal_process', fake_spawn)
    monkeypatch.setattr(
        terminal_sessions,
        '_close_spawned_process',
        lambda master_fd, process: closed_attempts.append((master_fd, process.pid, process.returncode)),
    )

    shell_path, command, master_fd, process = terminal_sessions._open_terminal_process(Path('/tmp'), 96, 28)

    assert shell_path == '/bin/sh'
    assert command == ['/bin/sh', '-i']
    assert master_fd == 92
    assert process.pid == 202
    assert attempts == [
        (['/bin/bash', '--noprofile', '--norc', '-i'], Path('/tmp'), 96, 28),
        (['/bin/sh', '-i'], Path('/tmp'), 96, 28),
    ]
    assert closed_attempts == [(91, 101, 0)]


def test_terminal_input_keeps_running_when_launcher_process_has_already_exited(monkeypatch):
    now = time.time()
    captured_writes = []

    class FakeProcess:
        def __init__(self):
            self.pid = 333
            self.returncode = 0

        def poll(self):
            return 0

    session = terminal_sessions._TerminalSession(
        id='launcher-exit-still-alive',
        root='workspace',
        root_path='/tmp/workspace',
        path='',
        cwd='/tmp/workspace',
        display_path='$workspace',
        title='$workspace',
        shell='bash',
        cols=96,
        rows=28,
        created_ts=now,
        updated_ts=now,
        last_output_ts=now,
        master_fd=87,
        process=FakeProcess(),
    )

    monkeypatch.setattr(
        terminal_sessions.os,
        'write',
        lambda fd, data: captured_writes.append((fd, data)) or len(data),
    )

    with terminal_sessions._SESSIONS_LOCK:
        terminal_sessions._TERMINAL_SESSIONS[session.id] = session
    try:
        summary = terminal_sessions.write_terminal_input(session.id, 'printf "__alive__\\n"\n')
    finally:
        with terminal_sessions._SESSIONS_LOCK:
            terminal_sessions._TERMINAL_SESSIONS.pop(session.id, None)

    assert summary['process_running'] is True
    assert summary['exit_code'] is None
    assert session.launcher_exit_code == 0
    assert captured_writes == [(87, b'printf "__alive__\\n"\n')]


def test_terminal_input_marks_session_stopped_when_pty_write_reports_eio(monkeypatch):
    now = time.time()
    closed_fds = []

    class FakeProcess:
        def __init__(self):
            self.pid = 444
            self.returncode = 0

        def poll(self):
            return 0

    session = terminal_sessions._TerminalSession(
        id='pty-eio-stop',
        root='workspace',
        root_path='/tmp/workspace',
        path='',
        cwd='/tmp/workspace',
        display_path='$workspace',
        title='$workspace',
        shell='bash',
        cols=96,
        rows=28,
        created_ts=now,
        updated_ts=now,
        last_output_ts=now,
        master_fd=88,
        process=FakeProcess(),
    )

    def fail_write(_fd, _data):
        raise OSError(errno.EIO, 'pty closed')

    monkeypatch.setattr(terminal_sessions.os, 'write', fail_write)
    monkeypatch.setattr(terminal_sessions, '_safe_close_fd', lambda fd: closed_fds.append(fd))

    with terminal_sessions._SESSIONS_LOCK:
        terminal_sessions._TERMINAL_SESSIONS[session.id] = session
    try:
        with pytest.raises(terminal_sessions.TerminalSessionError) as exc_info:
            terminal_sessions.write_terminal_input(session.id, 'printf "__closed__\\n"\n')
        snapshot = terminal_sessions.read_terminal_session(session.id)
    finally:
        with terminal_sessions._SESSIONS_LOCK:
            terminal_sessions._TERMINAL_SESSIONS.pop(session.id, None)

    assert exc_info.value.error_code == 'session_not_running'
    assert snapshot['process_running'] is False
    assert snapshot['exit_code'] == 0
    assert snapshot['output'] == ''
    assert closed_fds == [88]


def test_terminal_stream_events_follow_output_and_stop_transitions():
    now = time.time()
    session = terminal_sessions._TerminalSession(
        id='stream-events-session',
        root='workspace',
        root_path='/tmp/workspace',
        path='docs',
        cwd='/tmp/workspace/docs',
        display_path='$workspace/docs',
        title='docs',
        shell='bash',
        cols=100,
        rows=28,
        created_ts=now,
        updated_ts=now,
        last_output_ts=now,
        output_buffer='hello\n',
        process_running=True,
    )

    with terminal_sessions._SESSIONS_LOCK:
        terminal_sessions._TERMINAL_SESSIONS[session.id] = session
    try:
        events = terminal_sessions.iter_terminal_session_events(session.id, offset=0, heartbeat_seconds=0.5)

        first_event = next(events)
        assert first_event.get('event') in (None, 'message')
        assert first_event['data']['output'] == 'hello\n'
        assert first_event['data']['process_running'] is True

        with session.lock:
            terminal_sessions._append_output(session, 'world\n')

        second_event = next(events)
        assert second_event.get('event') in (None, 'message')
        assert second_event['data']['output'] == 'world\n'
        assert second_event['data']['process_running'] is True

        with session.lock:
            terminal_sessions._mark_session_stopped(session, exit_code=0)

        third_event = next(events)
        assert third_event.get('event') in (None, 'message')
        assert third_event['data']['output'] == ''
        assert third_event['data']['process_running'] is False

        end_event = next(events)
        assert end_event['event'] == 'end'
        assert end_event['data']['exit_code'] == 0
    finally:
        with terminal_sessions._SESSIONS_LOCK:
            terminal_sessions._TERMINAL_SESSIONS.pop(session.id, None)


def test_terminal_routes_open_and_list_sessions(browser_test_client, isolated_browser_roots):
    workspace_root = isolated_browser_roots['workspace_root']
    (workspace_root / 'scripts').mkdir(parents=True, exist_ok=True)

    create_response = browser_test_client.post(
        '/api/codex/terminals',
        json={
            'root': 'workspace',
            'path': 'scripts',
            'cols': 88,
            'rows': 22,
        },
    )
    assert create_response.status_code == 200
    created = create_response.get_json()
    session_id = created['id']
    assert created['path'] == 'scripts'
    assert created['cols'] == 88
    assert created['rows'] == 22

    list_response = browser_test_client.get('/api/codex/terminals')
    assert list_response.status_code == 200
    sessions = list_response.get_json()['sessions']
    assert any(session['id'] == session_id for session in sessions)

    input_response = browser_test_client.post(
        f'/api/codex/terminals/{session_id}/input',
        json={'data': 'printf "__api_terminal__\\n"\n'},
    )
    assert input_response.status_code == 200

    snapshot = _wait_for_terminal_snapshot(
        lambda: browser_test_client.get(f'/api/codex/terminals/{session_id}').get_json(),
        lambda payload: '__api_terminal__' in str(payload.get('output') or ''),
    )
    assert snapshot['process_running'] is True

    close_response = browser_test_client.post(f'/api/codex/terminals/{session_id}/close')
    assert close_response.status_code == 200
    assert close_response.get_json()['closed'] is True


def test_terminal_events_route_streams_sse_payload(browser_test_client):
    now = time.time()
    session = terminal_sessions._TerminalSession(
        id='route-stream-session',
        root='workspace',
        root_path='/tmp/workspace',
        path='',
        cwd='/tmp/workspace',
        display_path='$workspace',
        title='$workspace',
        shell='bash',
        cols=96,
        rows=28,
        created_ts=now,
        updated_ts=now,
        last_output_ts=now,
        output_buffer='ready\n',
        process_running=False,
        exit_code=0,
    )

    with terminal_sessions._SESSIONS_LOCK:
        terminal_sessions._TERMINAL_SESSIONS[session.id] = session
    try:
        response = browser_test_client.get(
            f'/api/codex/terminals/{session.id}/events?offset=0',
            buffered=True,
        )
    finally:
        with terminal_sessions._SESSIONS_LOCK:
            terminal_sessions._TERMINAL_SESSIONS.pop(session.id, None)

    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'
    payload = response.get_data(as_text=True)
    assert 'retry: 1000' in payload
    assert '"output": "ready\\n"' in payload
    assert 'event: end' in payload


def test_terminal_vendor_assets_are_available_locally(browser_test_client):
    app_js = (CODEX_APP_ROOT / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')

    assert "/static/vendor/xterm-5.5.0.js" in app_js
    assert "/static/vendor/xterm-5.5.0.css" in app_js
    assert "/static/vendor/xterm-addon-fit-0.10.0.js" in app_js

    for asset_path in (
        '/static/vendor/xterm-5.5.0.js',
        '/static/vendor/xterm-5.5.0.css',
        '/static/vendor/xterm-addon-fit-0.10.0.js',
    ):
        response = browser_test_client.get(asset_path)
        assert response.status_code == 200
