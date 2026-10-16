"""No provider calls: exercise the runner over an actual local HTTP socket."""
import importlib.util
import json
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
                    {'slug': 'model-a', 'default_reasoning_effort': 'low', 'reasoning_options': ['low', 'high']}]}}
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
