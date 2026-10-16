"""No provider calls: exercise the runner over an actual local HTTP socket."""
import importlib.util
import json
import io
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location('backend_runner', Path(__file__).resolve().parents[1] / 'scripts' / 'test_backend_model_reasoning.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture
def fake_server():
    state = SimpleNamespace(settings={'agent_backend': 'dtgpt', 'model': 'model-a', 'reasoning_effort': 'low'},
                            sessions={}, streams={}, patches=[], failure=False, hanging=False, requests=[])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def do_PATCH(self):
            self.dispatch()

        def dispatch(self):
            path = self.path.removeprefix('/api/codex')
            payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or '{}')
            state.requests.append((self.command, path))
            code = 200
            if path == '/settings':
                if self.command == 'PATCH':
                    state.patches.append(payload)
                    state.settings.update(payload)
                result = {'settings': dict(state.settings), 'model_catalogs_by_agent_backend': {'dtgpt': [
                    {'slug': 'model-a', 'default_reasoning_effort': 'low', 'reasoning_options': ['low', 'high']}],
                    'claude': [{'slug': 'claude-a', 'default_reasoning_effort': 'low', 'reasoning_options': ['low', 'high']}],
                    'opencode': [{'slug': 'provider/model'}]}}
            elif path == '/streams':
                result = {'streams': []}
            elif path == '/sessions':
                sid = str(len(state.sessions) + 1)
                state.sessions[sid] = {'id': sid, 'messages': []}
                result = {'session': state.sessions[sid]}
            elif '/message' in path:
                sid = path.split('/')[2]
                token = re.search(r'WBTEST_[a-f0-9]+', payload['prompt'])[0]
                meta = {f'response_{k}': v for k, v in state.settings.items()}
                message = {'id': 'answer', 'role': 'assistant', 'content': 'wrong' if state.failure else token, 'metadata': meta}
                state.sessions[sid]['messages'].append(message)
                state.streams[sid] = dict(meta, done=not state.hanging, saved=not state.hanging,
                                          exit_code=0, assistant_message_id='answer')
                result = dict(meta, stream_id=sid, assistant_message_id='answer', assistant_message=message)
            elif path.startswith('/streams/'):
                sid = path.split('/')[2]
                if path.endswith('/stop'):
                    state.streams[sid].update(done=True, saved=True)
                result = state.streams[sid]
            elif path.startswith('/sessions/'):
                result = {'session': state.sessions[path.split('/')[2]]}
            else:
                code, result = 404, {}
            body = json.dumps(result).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f'http://127.0.0.1:{server.server_port}'
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


def test_matrix_uses_per_model_efforts_and_opencode_default():
    snapshot = {'settings': {}, 'model_catalogs_by_agent_backend': {
        'dtgpt': [{'slug': 'a', 'reasoning_options': ['low', 'high']}, {'slug': 'b', 'reasoning_options': ['high']}],
        'opencode': [{'slug': 'provider/model', 'reasoning_options': ['high']}]}}
    rows = runner.matrix(snapshot, ['codex', 'opencode'], [], [], True)
    assert [(r['model'], r['reasoning']) for r in rows] == [('a', 'low'), ('a', 'high'), ('b', 'high'), ('provider/model', '')]
    assert runner.matrix(snapshot, ['opencode'], [], ['high'], True)[0]['status'] == 'UNSUPPORTED'
    assert runner.matrix(snapshot, ['codex'], ['missing'], [], True)[0]['status'] == 'UNSUPPORTED'


@pytest.mark.parametrize('mode', ['stream', 'sync'])
def test_actual_http_matrix_persistence_and_restoration(fake_server, tmp_path, mode):
    before = dict(fake_server.settings)
    out = tmp_path / 'report'
    assert runner.main(['--base-url', fake_server.url, '--backend', 'codex', '--all', '--mode', mode,
                        '--output-directory', str(out)]) == 0
    results = json.loads((out / 'results.json').read_text())
    assert len(results) == 2
    assert all(r['status'] == 'PASS' for r in results)
    assert fake_server.settings == before
    assert (out / 'results.csv').exists()
    assert json.loads((out / 'summary.json').read_text())['settings_restored']


def test_failure_does_not_abort_next_case_and_restores(fake_server, tmp_path):
    fake_server.failure = True
    assert runner.main(['--base-url', fake_server.url, '--backend', 'codex', '--all',
                        '--output-directory', str(tmp_path / 'report')]) == 1
    results = json.loads((tmp_path / 'report' / 'results.json').read_text())
    assert [r['status'] for r in results] == ['FAIL', 'FAIL']
    assert fake_server.settings['reasoning_effort'] == 'low'


def test_timeout_stops_only_owned_stream_then_next_case(fake_server, tmp_path):
    fake_server.hanging = True
    assert runner.main(['--base-url', fake_server.url, '--backend', 'codex', '--all', '--timeout', '0.08',
                        '--output-directory', str(tmp_path / 'report')]) == 1
    results = json.loads((tmp_path / 'report' / 'results.json').read_text())
    assert [r['status'] for r in results] == ['TIMEOUT', 'TIMEOUT']
    assert ('POST', '/streams/1/stop') in fake_server.requests
    assert ('POST', '/streams/2/stop') in fake_server.requests
    assert fake_server.settings['reasoning_effort'] == 'low'


def test_list_only_never_mutates(fake_server):
    assert runner.main(['--base-url', fake_server.url, '--backend', 'codex', '--list-only']) == 0
    assert fake_server.requests == [('GET', '/settings')]


@pytest.mark.parametrize('extra_args', [[], ['--all']])
def test_default_backends_exclude_codex_even_when_current(fake_server, tmp_path, monkeypatch, extra_args):
    before = dict(fake_server.settings)
    original = runner.run_case

    def check_candidates(client, row, args, scenario):
        assert {r['backend'] for r in args.queue_candidates} == {'claude', 'opencode'}
        return original(client, row, args, scenario)

    monkeypatch.setattr(runner, 'run_case', check_candidates)
    out = tmp_path / 'report'
    assert runner.main(['--base-url', fake_server.url, '--output-directory', str(out), *extra_args]) == 0
    results = json.loads((out / 'results.json').read_text())
    assert {r['backend'] for r in results} == {'claude', 'opencode'}
    assert len(results) == (3 if extra_args else 2)
    assert all(r['status'] == 'PASS' for r in results)
    assert all(p['agent_backend'] != 'dtgpt' for p in fake_server.patches[:-1])
    assert fake_server.settings == before


def test_restore_backup_and_redaction(fake_server, tmp_path, monkeypatch):
    backup = tmp_path / 'backup.json'
    backup.write_text(json.dumps({'base_url': fake_server.url, 'settings': dict(fake_server.settings)}))
    fake_server.settings['reasoning_effort'] = 'high'
    assert runner.main(['--base-url', fake_server.url, '--restore-settings', str(backup)]) == 0
    assert fake_server.settings['reasoning_effort'] == 'low'
    monkeypatch.setenv('WORKBENCH_TEST_COOKIE', 'private-cookie')
    assert runner.safe_detail('error private-cookie') == 'error [REDACTED]'


def test_metadata_mismatch_is_not_a_pass():
    with pytest.raises(AssertionError, match='response_model mismatch'):
        runner.check_metadata({'response_agent_backend': 'dtgpt', 'response_model': 'wrong'},
                              {'backend': 'dtgpt', 'model': 'a', 'reasoning': ''})


def test_unconfirmed_stop_aborts_remaining_cases_but_restores(fake_server, tmp_path, monkeypatch):
    fake_server.hanging = True

    def failed_stop(*args):
        raise RuntimeError('stop unreachable')

    monkeypatch.setattr(runner, 'stop_owned', failed_stop)
    out = tmp_path / 'report'
    assert runner.main(['--base-url', fake_server.url, '--backend', 'codex', '--all', '--timeout', '0.08',
                        '--output-directory', str(out)]) == 1
    results = json.loads((out / 'results.json').read_text())
    assert len(results) == 1
    assert results[0]['cleanup_error']
    assert fake_server.settings['reasoning_effort'] == 'low'


def test_failed_restore_produces_recovery_summary(fake_server, tmp_path, monkeypatch):
    original = runner.Client.request

    def fail_restore(self, method, path, payload=None, **kwargs):
        if method == 'PATCH' and len(fake_server.patches) >= 2:
            raise RuntimeError('server unavailable during restore')
        return original(self, method, path, payload, **kwargs)

    monkeypatch.setattr(runner.Client, 'request', fail_restore)
    out = tmp_path / 'report'
    assert runner.main(['--base-url', fake_server.url, '--backend', 'codex', '--all',
                        '--output-directory', str(out)]) == 1
    assert not json.loads((out / 'summary.json').read_text())['settings_restored']
    assert json.loads((out / 'restore-settings.json').read_text())['settings']['reasoning_effort'] == 'low'


@pytest.mark.parametrize('mode', ['stream', 'sync'])
def test_live_progress_during_blocking_submit(fake_server, tmp_path, monkeypatch, capsys, mode):
    original_request = runner.Client.request
    original_emit = runner.Progress._emit
    heartbeat = threading.Event()
    submitting_lines = []
    monitors = []

    class FastProgress(runner.Progress):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, interval=0.01)
            monitors.append(self)

        def _emit(self):
            original_emit(self)
            if self.state['phase'] == 'submitting':
                submitting_lines.append(self.started)
                if len(submitting_lines) >= 2:
                    heartbeat.set()

    def blocking_submit(self, method, path, *args, **kwargs):
        if method == 'POST' and '/message' in path:
            # A second refresh must happen before the blocking request returns.
            assert heartbeat.wait(2), 'No live elapsed update during HTTP submission'
        return original_request(self, method, path, *args, **kwargs)

    monkeypatch.setattr(runner, 'Progress', FastProgress)
    monkeypatch.setattr(runner.Client, 'request', blocking_submit)
    assert runner.main(['--base-url', fake_server.url, '--backend', 'claude', '--mode', mode,
                        '--output-directory', str(tmp_path / 'report')]) == 0
    output = capsys.readouterr().out
    assert '[1/1] backend=claude model=claude-a reasoning=low scenario=echo' in output
    assert 'phase=submitting session=1 elapsed=' in output
    assert 'phase=verifying' in output
    assert 'timeout=90s' in output
    assert 'PASS elapsed=' in output
    if mode == 'stream':
        assert 'phase=waiting-response session=1 stream=1' in output
    assert all(not monitor.thread.is_alive() for monitor in monitors)


def test_direct_progress_and_monitor_cleanup(fake_server, tmp_path, monkeypatch, capsys):
    original_emit = runner.Progress._emit
    heartbeat = threading.Event()
    direct_lines = []
    monitors = []

    class FastProgress(runner.Progress):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, interval=0.01)
            monitors.append(self)

        def _emit(self):
            original_emit(self)
            if self.state['phase'] == 'running-direct':
                direct_lines.append(self.started)
                if len(direct_lines) >= 2:
                    heartbeat.set()

    def blocking_direct(row, timeout):
        assert heartbeat.wait(2), 'No live elapsed update during direct comparison'
        return {'status': 'PASS'}

    monkeypatch.setattr(runner, 'Progress', FastProgress)
    monkeypatch.setattr(runner, 'run_direct', blocking_direct)
    assert runner.main(['--base-url', fake_server.url, '--backend', 'claude', '--direct', 'all',
                        '--output-directory', str(tmp_path / 'report')]) == 0
    output = capsys.readouterr().out
    assert 'scenario=echo/direct phase=running-direct elapsed=' in output
    assert 'phase=finished-direct status=PASS' in output
    assert all(not monitor.thread.is_alive() for monitor in monitors)


def test_progress_thread_stops_on_exception():
    progress = runner.Progress({'backend': 'claude', 'model': 'a', 'reasoning': ''}, 'echo', 1, 1, 90)
    with pytest.raises(RuntimeError, match='interrupted'):
        with progress:
            raise RuntimeError('interrupted')
    assert not progress.thread.is_alive()


def test_progress_rewrites_one_terminal_line(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(output, 'isatty', lambda: True)
    monkeypatch.setattr(runner.sys, 'stdout', output)
    monkeypatch.setattr(runner.shutil, 'get_terminal_size', lambda: os.terminal_size((80, 24)))
    progress = runner.Progress({'backend': 'claude', 'model': '모델' * 80, 'reasoning': ''}, 'echo', 1, 1, 90)
    with progress:
        progress.update('submitting', session=1)
        progress._emit()
        progress.label = ''
        progress.update('done')
    rendered = output.getvalue()
    assert rendered.count('\n') == 1
    assert rendered.count('\r') == 4
    assert 'elapsed=' in rendered
    assert 'phase=submitting' in rendered
    frames = rendered.rstrip('\n').split('\r')[1:]
    for frame in frames:
        assert sum(2 if runner.unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in frame) <= 79
    assert len(frames[-1]) > len(frames[-1].rstrip(' '))


def test_redirected_progress_only_logs_state_changes(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(runner.sys, 'stdout', output)
    progress = runner.Progress({'backend': 'claude', 'model': 'a', 'reasoning': ''}, 'echo', 1, 1, 90)
    with progress:
        progress._emit()
        progress.update('submitting', session=1)
        progress._emit()
        progress.update('submitting', session=1)
    assert output.getvalue().count('\n') == 2
    assert '\r' not in output.getvalue()
