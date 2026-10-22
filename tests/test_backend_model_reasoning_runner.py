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


def test_environment_key_pool_validation_and_redaction(monkeypatch):
    monkeypatch.setenv('WORKBENCH_TEST_API_KEYS', '[" pool-secret-one ","pool-secret-two"]')
    assert runner.environment_api_keys() == ['pool-secret-one', 'pool-secret-two']
    assert runner.diagnostic_text('failed pool-secret-one / pool-secret-two') == 'failed [REDACTED] / [REDACTED]'
    for invalid in ('{"secret":"bad"}', '[]', '[""]', '[1]', 'private-malformed-key'):
        monkeypatch.setenv('WORKBENCH_TEST_API_KEYS', invalid)
        with pytest.raises(ValueError, match='must be a JSON array') as exc:
            runner.environment_api_keys()
        assert invalid not in str(exc.value)
    monkeypatch.delenv('WORKBENCH_TEST_API_KEYS')
    monkeypatch.setenv('DTGPT_API_KEY', 'legacy-secret')
    assert runner.environment_api_keys() == ['legacy-secret']


def test_missing_key_guidance_explains_both_shells(monkeypatch, capsys):
    monkeypatch.delenv('WORKBENCH_TEST_API_KEYS', raising=False)
    monkeypatch.delenv('DTGPT_API_KEY', raising=False)
    runner.print_key_guidance()
    output = capsys.readouterr().out
    assert '$env:WORKBENCH_TEST_API_KEYS = ' in output
    assert 'export WORKBENCH_TEST_API_KEYS=' in output
    assert 'Client API key variables do not change the running server' in output


def test_direct_rotates_per_execution_without_consuming_for_opencode(monkeypatch):
    monkeypatch.setenv('WORKBENCH_TEST_API_KEYS', '["first-secret","second-secret"]')
    monkeypatch.setattr(runner, '_direct_key_cursor', 0)
    calls = []

    def spawn(cmd, **kwargs):
        calls.append((cmd, kwargs['env']))
        return SimpleNamespace(returncode=0, communicate=lambda **_: (b'{"status":"PASS"}\n', b''))

    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    for backend in ('claude', 'opencode', 'dtgpt', 'claude'):
        assert runner.run_direct(dict(backend=backend, model='model', reasoning=''), 1)['status'] == 'PASS'
    assert [env.get('WORKBENCH_TEST_SELECTED_API_KEY') for _, env in calls] == [
        'first-secret', None, 'second-secret', 'first-secret']
    assert all('secret' not in ' '.join(cmd) for cmd, _ in calls)
    assert 'WORKBENCH_TEST_SELECTED_API_KEY' not in os.environ


@pytest.mark.parametrize('selected', ['', 'reserved-secret'])
def test_direct_worker_uses_production_environment(monkeypatch, capsys, tmp_path, selected):
    import sys
    import types

    monkeypatch.setenv('WORKBENCH_TEST_SELECTED_API_KEY', selected)
    monkeypatch.delenv('CODEX_CLAUDE_ENV_MODE', raising=False)
    calls = []
    credentials = types.ModuleType('codex_agent.services.company_credentials')
    credentials.company_key_pool_supported = lambda: True
    monkeypatch.setitem(sys.modules, 'codex_agent.services.company_credentials', credentials)
    service = SimpleNamespace(
        get_agent_backend_options=lambda: [{'id': b} for b in ('dtgpt', 'claude', 'opencode')],
        WORKSPACE_DIR=tmp_path,
        _build_agent_exec_env=lambda backend, **kw: calls.append(('build', backend, kw)) or {
            'runtime': 'ready', 'WORKBENCH_TEST_SELECTED_API_KEY': selected, 'WORKBENCH_TEST_API_KEYS': 'private'},
        _apply_agent_backend_exec_env=lambda env, backend, **kw: env.update(gateway='production', **kw),
        _build_agent_command=lambda *a, **kw: ('claude', ['claude', '--model', 'mapped', '--effort', 'low']),
        resolve_claude_cli_model_name=lambda model: 'mapped',
        resolve_claude_reasoning_effort=lambda **kw: 'low')
    package = types.ModuleType('codex_agent.services')
    package.codex_chat = service
    monkeypatch.setitem(sys.modules, 'codex_agent.services', package)

    def execute(cmd, **kwargs):
        assert kwargs['env'] == {'runtime': 'ready', 'gateway': 'production', 'model_override': 'catalog-model'}
        assert kwargs['cwd'] == str(tmp_path)
        return SimpleNamespace(returncode=0, stdout=kwargs['input'], stderr='')

    monkeypatch.setattr(runner.subprocess, 'run', execute)
    runner.direct_worker(dict(backend='claude', model='catalog-model', reasoning='low'))
    assert calls == [('build', 'claude', {'internal_api_key': {'secret': selected} if selected else None})]
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['status'] == 'PASS'


@pytest.mark.parametrize('backend,requested,expected,actual,model,matches', [
    ('claude', 'high', 'low', 'low', 'mapped', True),
    ('claude', 'high', '', '', 'mapped', True),
    ('claude', '', 'medium', 'medium', 'mapped', True),
    ('dtgpt', 'high', 'low', 'low', 'catalog-model', True),
    ('dtgpt', '', 'medium', 'medium', 'catalog-model', True),
    ('claude', 'high', 'low', 'high', 'mapped', False),
    ('dtgpt', 'high', 'low', 'high', 'catalog-model', False),
    ('claude', 'high', 'low', 'low', 'wrong-model', False),
])
def test_direct_worker_validates_normalized_arguments(
        monkeypatch, capsys, tmp_path, backend, requested, expected, actual, model, matches):
    import sys
    import types

    monkeypatch.delenv('WORKBENCH_TEST_SELECTED_API_KEY', raising=False)
    cmd = [backend, '--model', model]
    if actual:
        cmd += ['--effort', actual] if backend == 'claude' else [
            '--config', 'model_reasoning_effort=' + json.dumps(actual)]
    resolver_calls = []
    executions = []

    def resolve(**kw):
        resolver_calls.append(kw)
        return expected or None

    service = SimpleNamespace(
        get_agent_backend_options=lambda: [{'id': b} for b in ('dtgpt', 'claude', 'opencode')],
        WORKSPACE_DIR=tmp_path,
        _build_agent_exec_env=lambda *a, **kw: {},
        _apply_agent_backend_exec_env=lambda *a, **kw: None,
        _build_agent_command=lambda *a, **kw: (backend, cmd),
        _wrap_codex_cli_command=lambda cmd: cmd,
        resolve_claude_cli_model_name=lambda model: 'mapped',
        resolve_claude_reasoning_effort=resolve,
        resolve_codex_reasoning_effort=resolve)
    package = types.ModuleType('codex_agent.services')
    package.codex_chat = service
    monkeypatch.setitem(sys.modules, 'codex_agent.services', package)

    def execute(cmd, **kw):
        executions.append(cmd)
        return SimpleNamespace(returncode=0, stdout=kw['input'], stderr='')

    monkeypatch.setattr(runner.subprocess, 'run', execute)
    runner.direct_worker(dict(backend=backend, model='catalog-model', reasoning=requested))
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    validation = next(r['cli_validation'] for r in records if r.get('event') == 'cli_validation')
    assert validation == {
        'requested': {'model': 'catalog-model', 'reasoning': requested},
        'expected': {'model': 'mapped' if backend == 'claude' else 'catalog-model', 'reasoning': expected},
        'actual': {'model': model, 'reasoning': actual},
        'matches': matches}
    assert resolver_calls == [{'model_name': 'catalog-model', 'reasoning_effort': requested}]
    assert records[-1]['status'] == ('PASS' if matches else 'FAIL')
    assert bool(executions) == matches
    if not matches:
        assert records[-1]['failure_phase'] == 'cli_argument_validation'


@pytest.mark.parametrize('enabled,actual', [
    (['dtgpt'], 'dtgpt'),
    (['dtgpt', 'claude'], 'dtgpt'),
])
def test_direct_worker_rejects_disabled_or_substituted_backend(monkeypatch, capsys, enabled, actual):
    import sys
    import types

    monkeypatch.delenv('WORKBENCH_TEST_SELECTED_API_KEY', raising=False)
    built = []

    def build(*args, **kwargs):
        built.append(True)
        return actual, ['codex', '--model', 'mapped', '--effort', 'low']

    service = SimpleNamespace(
        get_agent_backend_options=lambda: [{'id': b} for b in enabled],
        _build_agent_command=build)
    package = types.ModuleType('codex_agent.services')
    package.codex_chat = service
    monkeypatch.setitem(sys.modules, 'codex_agent.services', package)
    monkeypatch.setattr(runner.shutil, 'which', lambda cmd: '/resolved/codex')
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: pytest.fail('CLI must not execute'))
    runner.direct_worker(dict(backend='claude', model='mapped', reasoning='low'))
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    result = records[-1]
    assert result['status'] == 'FAIL'
    assert result['failure_phase'] == 'backend_validation'
    execution = result['execution']
    assert execution['requested_backend'] == 'claude'
    assert execution['enabled_backends'] == sorted(enabled)
    assert execution['actual_backend'] == (actual if built else None)
    assert bool(built) == ('claude' in enabled)
    assert records[0]['execution'] == execution
    if built:
        assert execution['executable'] == 'codex'
        assert execution['resolved_executable'] == '/resolved/codex'


@pytest.mark.parametrize('outcome', ['success', 'failure', 'timeout', 'invalid'])
def test_run_direct_preserves_preflight_validation(monkeypatch, outcome):
    validation = {'requested': {'reasoning': 'high'}, 'expected': {'reasoning': ''},
                  'actual': {'reasoning': ''}, 'matches': True}
    execution = {'requested_backend': 'claude', 'actual_backend': 'dtgpt',
                 'enabled_backends': ['dtgpt'], 'resolved_executable': '/bin/codex'}
    output = json.dumps({'event': 'execution_preflight', 'execution': execution}) + '\n'
    output += json.dumps({'event': 'cli_validation', 'cli_validation': validation}) + '\n'
    output += '{"status":"PASS"}\n' if outcome == 'success' else 'not-json\n'
    calls = []

    def communicate(**kw):
        calls.append(kw)
        if outcome == 'timeout' and len(calls) == 1:
            raise runner.subprocess.TimeoutExpired('worker', 1)
        return output.encode(), b'worker stderr'

    monkeypatch.delenv('WORKBENCH_TEST_API_KEYS', raising=False)
    monkeypatch.setattr(runner.subprocess, 'Popen', lambda *a, **kw: SimpleNamespace(
        returncode=1 if outcome == 'failure' else 0, pid=123, communicate=communicate))
    monkeypatch.setattr(runner.os, 'killpg', lambda *a: None, raising=False)
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **kw: None)
    result = runner.run_direct(dict(backend='claude', model='a', reasoning='high'), 1)
    assert result['cli_validation'] == validation
    assert result['execution'] == execution
    assert result['status'] == {'success': 'PASS', 'failure': 'FAIL',
                                'timeout': 'TIMEOUT', 'invalid': 'FAIL'}[outcome]


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
                    'claude': [{'slug': 'Qwen3.8-27B', 'default_reasoning_effort': 'low', 'reasoning_options': ['low', 'high']}],
                    'opencode': [{'slug': 'provider/model'}]}}
            elif path == '/streams':
                result = {'streams': []}
            elif path == '/sessions':
                assert payload.get('internal') is True
                sid = str(len(state.sessions) + 1)
                state.sessions[sid] = {'id': sid, 'messages': []}
                result = {'session': state.sessions[sid]}
            elif '/message' in path:
                sid = path.split('/')[2]
                token = re.search(r'WBTEST_[a-f0-9]+', payload['prompt'])[0]
                meta = {f'response_{k}': v for k, v in state.settings.items()}
                # append_message stores response fields on the message itself.
                message = dict(meta, id='answer', role='assistant', content='wrong' if state.failure else token)
                state.sessions[sid]['messages'].append(message)
                state.streams[sid] = dict(meta, done=not state.hanging, saved=not state.hanging,
                                          exit_code=0, assistant_message_id='answer')
                state.streams[sid]['agent_backend'] = state.streams[sid].pop('response_agent_backend')
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


@pytest.mark.parametrize('exhaustive', [False, True])
def test_simplified_model_selection_and_explicit_override(exhaustive):
    snapshot = {'settings': {'model': 'other-claude'}, 'model_catalogs_by_agent_backend': {
        'claude': [
            {'slug': 'other-claude', 'reasoning_options': ['high']},
            {'slug': 'Qwen3.8-27B', 'default_reasoning_effort': 'low', 'reasoning_options': ['low', 'high']}],
        'opencode': [{'slug': 'provider/one'}, {'slug': 'provider/two'}]}}
    rows = runner.matrix(snapshot, ['opencode', 'claude'], [], [], exhaustive)
    assert [(r['backend'], r['model'], r['reasoning']) for r in rows] == [
        ('opencode', 'provider/one', ''), ('opencode', 'provider/two', ''),
        ('claude', 'Qwen3.8-27B', 'low')
    ] + ([('claude', 'Qwen3.8-27B', 'high')] if exhaustive else [])
    assert all(r['status'] == 'PLANNED' for r in rows)
    override = runner.matrix(snapshot, ['claude'], ['other-claude'], [], exhaustive)
    assert [r['model'] for r in override] == ['other-claude']
    snapshot['model_catalogs_by_agent_backend']['claude'].pop()
    assert runner.matrix(snapshot, ['claude'], [], [], exhaustive) == [dict(
        backend='claude', model='Qwen3.8-27B', reasoning='', status='UNSUPPORTED')]


def test_matrix_uses_per_model_efforts_and_opencode_default():
    snapshot = {'settings': {}, 'model_catalogs_by_agent_backend': {
        'dtgpt': [{'slug': 'a', 'reasoning_options': ['low', 'high']}, {'slug': 'b', 'reasoning_options': ['high']}],
        'opencode': [{'slug': 'provider/model', 'reasoning_options': ['high']}]}}
    rows = runner.matrix(snapshot, ['codex', 'opencode'], [], [], True)
    assert [(r['model'], r['reasoning']) for r in rows] == [('a', 'low'), ('a', 'high'), ('b', 'high'), ('provider/model', '')]
    assert runner.matrix(snapshot, ['opencode'], [], ['high'], True)[0]['status'] == 'UNSUPPORTED'
    assert runner.matrix(snapshot, ['codex'], ['missing'], [], True)[0]['status'] == 'UNSUPPORTED'


@pytest.mark.parametrize('mode', ['stream', 'sync'])
@pytest.mark.parametrize('backend,count', [('codex', 2), ('claude', 2), ('opencode', 1)])
def test_actual_http_matrix_persistence_and_restoration(fake_server, tmp_path, mode, backend, count):
    before = dict(fake_server.settings)
    out = tmp_path / 'report'
    assert runner.main(['--base-url', fake_server.url, '--backend', backend, '--all', '--mode', mode,
                        '--output-directory', str(out)]) == 0
    results = json.loads((out / 'results.json').read_text())
    assert len(results) == count
    assert all(r['status'] == 'PASS' for r in results)
    assert all(r['metadata_source'] == 'persisted_message' for r in results)
    trace = [json.loads(line) for line in (out / results[0]['trace_file']).read_text().splitlines()]
    checks = [entry for entry in trace if entry['event'] == 'metadata_check']
    assert checks[-1]['source'] == 'persisted_message'
    assert checks[-1]['actual']['response_model'] == results[0]['model']
    assert fake_server.settings == before
    assert (out / 'results.csv').exists()
    assert json.loads((out / 'summary.json').read_text())['settings_restored']


def test_failure_does_not_abort_next_case_and_restores(fake_server, tmp_path):
    fake_server.failure = True
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--backend', 'codex', '--all',
                        '--output-directory', str(tmp_path / 'report')]) == 1
    results = json.loads((tmp_path / 'report' / 'results.json').read_text())
    assert [r['status'] for r in results] == ['FAIL', 'FAIL']
    assert fake_server.settings['reasoning_effort'] == 'low'


def test_timeout_stops_only_owned_stream_then_next_case(fake_server, tmp_path):
    fake_server.hanging = True
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--backend', 'codex', '--all', '--timeout', '0.08',
                        '--output-directory', str(tmp_path / 'report')]) == 1
    results = json.loads((tmp_path / 'report' / 'results.json').read_text())
    assert [r['status'] for r in results] == ['TIMEOUT', 'TIMEOUT']
    assert ('POST', '/streams/1/stop') in fake_server.requests
    assert ('POST', '/streams/2/stop') in fake_server.requests
    assert fake_server.settings['reasoning_effort'] == 'low'
    assert results[0]['failure_phase'] == 'waiting-response'
    assert results[0]['failure_stream_snapshot']['done'] is False
    trace = [json.loads(line) for line in (tmp_path / 'report' / results[0]['trace_file']).read_text().splitlines()]
    snapshots = [entry['snapshot'] for entry in trace if entry['event'] == 'stream_snapshot']
    assert snapshots[0]['saved'] is False
    assert snapshots[-1]['saved'] is True  # Cleanup must not overwrite failure evidence.
    assert any(entry['event'] == 'http_complete' and entry['seconds'] >= 0 for entry in trace)
    assert trace[-1]['event'] == 'case_finished'


def test_stream_diagnostics_exclude_response_bodies_and_credentials():
    snapshot = runner.stream_snapshot(dict(done=False, output='private answer', error='secret token',
        exec_details={'env': 'password'}, diagnostic_timeline=[{'phase': 'starting_process', 'at': 42, 'secret': 'key'}]))
    assert snapshot == {'done': False, 'diagnostic_timeline': [{'phase': 'starting_process', 'at': 42}]}


def test_list_only_never_mutates(fake_server):
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--backend', 'codex', '--list-only']) == 0
    assert fake_server.requests == [('GET', '/settings')]


def test_default_execution_uses_server_streams_and_retains_sessions(fake_server, tmp_path, monkeypatch):
    original_init = runner.Client.__init__
    original_case = runner.run_case
    before = dict(fake_server.settings)

    def connect(self, url, timeout):
        assert url == 'http://localhost:3000'
        original_init(self, fake_server.url, timeout)

    def check_case(client, row, args, scenario):
        assert (args.mode, args.direct, args.timeout, args.all) == ('stream', 'off', 300, True)
        return original_case(client, row, args, scenario)

    monkeypatch.setattr(runner.Client, '__init__', connect)
    monkeypatch.setattr(runner, 'run_case', check_case)
    monkeypatch.setattr(runner, 'run_direct', lambda *a, **kw: pytest.fail('unexpected local provider call'))
    out = tmp_path / 'defaults'
    assert runner.main(['--output-directory', str(out)]) == 0
    results = json.loads((out / 'results.json').read_text())
    assert len(results) == len(fake_server.sessions) == 3
    assert all(r['session_id'] in fake_server.sessions for r in results)
    assert sum(method == 'POST' and path.endswith('/message/stream')
               for method, path in fake_server.requests) == 3
    assert fake_server.settings == before


@pytest.mark.parametrize('extra_args', [[], ['--all'], ['--no-all']])
def test_default_backends_exclude_codex_even_when_current(fake_server, tmp_path, monkeypatch, extra_args):
    before = dict(fake_server.settings)
    original = runner.run_case

    def check_candidates(client, row, args, scenario):
        assert {r['backend'] for r in args.queue_candidates} == {'claude', 'opencode'}
        assert args.queue_candidates[0]['backend'] == 'opencode'
        return original(client, row, args, scenario)

    monkeypatch.setattr(runner, 'run_case', check_candidates)
    out = tmp_path / 'report'
    assert runner.main(['--base-url', fake_server.url, '--output-directory', str(out), *extra_args]) == 0
    results = json.loads((out / 'results.json').read_text())
    assert {r['backend'] for r in results} == {'claude', 'opencode'}
    assert [r['backend'] for r in results] == ['opencode'] + ['claude'] * (1 if '--no-all' in extra_args else 2)
    assert len(results) == (2 if '--no-all' in extra_args else 3)
    assert all(r['status'] == 'PASS' for r in results)
    assert all(p['agent_backend'] != 'dtgpt' for p in fake_server.patches[:-1])
    assert fake_server.settings == before


def test_restore_backup_and_redaction(fake_server, tmp_path, monkeypatch):
    backup = tmp_path / 'backup.json'
    backup.write_text(json.dumps({'base_url': fake_server.url, 'settings': dict(fake_server.settings)}))
    fake_server.settings['reasoning_effort'] = 'high'
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--restore-settings', str(backup)]) == 0
    assert fake_server.settings['reasoning_effort'] == 'low'
    monkeypatch.setenv('WORKBENCH_TEST_COOKIE', 'private-cookie')
    assert runner.safe_detail('error private-cookie') == 'error [REDACTED]'


def test_metadata_mismatch_is_not_a_pass():
    with pytest.raises(AssertionError, match='response_model mismatch'):
        runner.check_metadata({'response_agent_backend': 'dtgpt', 'response_model': 'wrong'},
                              {'backend': 'dtgpt', 'model': 'a', 'reasoning': ''})


def test_nested_message_metadata_compatibility_keeps_top_level_authoritative():
    row = {'backend': 'claude', 'model': 'selected-model', 'reasoning': 'low'}
    metadata = {'response_agent_backend': 'claude', 'response_model': 'selected-model',
                'response_reasoning_effort': 'low'}
    runner.check_metadata({'metadata': metadata}, row)
    with pytest.raises(AssertionError, match='response_model mismatch'):
        runner.check_metadata({'metadata': metadata, 'response_model': 'claude-default'}, row)


def test_unconfirmed_stop_aborts_remaining_cases_but_restores(fake_server, tmp_path, monkeypatch):
    fake_server.hanging = True

    def failed_stop(*args):
        raise RuntimeError('stop unreachable')

    monkeypatch.setattr(runner, 'stop_owned', failed_stop)
    out = tmp_path / 'report'
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--backend', 'codex', '--all', '--timeout', '0.08',
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
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--backend', 'codex', '--all',
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
    assert '[1/2] backend=claude model=Qwen3.8-27B reasoning=low scenario=echo' in output
    assert 'phase=submitting session=1 elapsed=' in output
    assert 'phase=verifying' in output
    assert 'timeout=300s' in output
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
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--backend', 'claude', '--direct', 'all',
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


def test_failed_exit_collects_error_and_persisted_message(fake_server, tmp_path, monkeypatch):
    original = runner.Client._request
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'private-provider-key')

    def failed_stream(self, method, path, *args, **kwargs):
        result = original(self, method, path, *args, **kwargs)
        if path.startswith('/streams/'):
            result.update(exit_code=1, error='gateway rejected private-provider-key',
                          output='provider partial answer', events=[{'type': 'error', 'message': 'bad model'}])
        return result

    monkeypatch.setattr(runner.Client, '_request', failed_stream)
    out = tmp_path / 'report'
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--backend', 'claude',
                        '--output-directory', str(out)]) == 1
    result = json.loads((out / 'results.json').read_text())[0]
    assert result['failure_stream_diagnostics']['error'] == 'gateway rejected [REDACTED]'
    assert result['failure_stream_diagnostics']['exit_code'] == 1
    assert result['failure_assistant_messages'][0]['id'] == 'answer'
    assert 'AssertionError: Stream exited unsuccessfully' in result['exception_traceback']
    trace = [json.loads(line) for line in (out / result['trace_file']).read_text().splitlines()]
    assert any(e['event'] == 'failure_assistant_messages' for e in trace)
    assert len([e for e in trace if e['event'] == 'stream_diagnostics']) == 1
    assert 'private-provider-key' not in ''.join(p.read_text(encoding='utf-8-sig') for p in out.iterdir())
    assert fake_server.settings['agent_backend'] == 'dtgpt'


def test_http_error_body_is_logged_and_redacted(monkeypatch):
    from urllib.error import HTTPError
    client = runner.Client('http://localhost')
    entries = []
    client.trace = lambda event, **fields: entries.append(dict(event=event, **fields))

    def reject(*args, **kwargs):
        raise HTTPError('http://localhost', 502, 'Bad Gateway', {},
                        io.BytesIO(b'{"error":"unsupported model", "api_key":"private-value"}'))

    monkeypatch.setattr(client.opener, 'open', reject)
    with pytest.raises(RuntimeError, match='HTTP 502'):
        client.request('GET', '/streams/test')
    status = next(e for e in entries if e['event'] == 'http_status')
    assert status['status'] == 502
    assert 'unsupported model' in status['body']
    assert 'private-value' not in status['body']


def test_diagnostic_redaction_and_tail_limits(monkeypatch):
    monkeypatch.setenv('WORKBENCH_TEST_AUTHORIZATION', 'Bearer private-auth')
    text = 'Bearer private-auth\nAuthorization: Bearer other-auth\nCookie: session=private-cookie\n'
    redacted = runner.diagnostic_text(text)
    assert 'private-auth' not in redacted
    assert 'other-auth' not in redacted
    assert 'private-cookie' not in redacted
    assert runner.diagnostic_text('x' * 20000 + 'failure tail').endswith('failure tail')
    assert runner.diagnostic_text('x' * 20000).startswith('[TRUNCATED:')
    assert runner.response_diagnostics({'prompt': 'private prompt', 'account_id': 'private account',
                                        'error': 'bad model'}) == {'error': 'bad model'}


def test_diagnostic_collection_failure_preserves_original_failure(fake_server, tmp_path, monkeypatch):
    original = runner.Client._request

    def broken_session(self, method, path, *args, **kwargs):
        if method == 'GET' and path.startswith('/sessions/'):
            raise RuntimeError('Session diagnostics unavailable')
        result = original(self, method, path, *args, **kwargs)
        if path.startswith('/streams/'):
            result['exit_code'] = 1
        return result

    monkeypatch.setattr(runner.Client, '_request', broken_session)
    out = tmp_path / 'report'
    assert runner.main(['--mode', 'stream', '--base-url', fake_server.url, '--backend', 'claude',
                        '--output-directory', str(out)]) == 1
    result = json.loads((out / 'results.json').read_text())[0]
    assert result['detail'] == 'Stream exited unsuccessfully'
    assert 'diagnostic_collection_error' in (out / result['trace_file']).read_text()
    assert json.loads((out / 'summary.json').read_text())['settings_restored']


@pytest.mark.parametrize('verdict,exit_code', [('PASS', 0), ('FAIL', 1), ('TIMEOUT', 1)])
def test_explicit_direct_is_read_only_even_with_active_work(fake_server, tmp_path, monkeypatch, verdict, exit_code):
    original = runner.Client._request

    def only_catalog(self, method, path, *a, **kw):
        # An active production task must never be inspected, cancelled, or changed.
        assert (method, path) == ('GET', '/settings')
        return original(self, method, path, *a, **kw)

    monkeypatch.setattr(runner.Client, '_request', only_catalog)
    calls = []
    monkeypatch.setattr(runner, 'run_direct', lambda row, timeout:
        calls.append(row['backend']) or dict(status=verdict, diagnostics={'output': 'test output'}))
    before = dict(fake_server.settings)
    out = tmp_path / 'standalone'
    assert runner.main(['--mode', 'direct', '--no-all', '--base-url', fake_server.url, '--output-directory', str(out)]) == exit_code
    assert calls == ['opencode', 'claude']
    assert fake_server.requests == [('GET', '/settings')]
    assert fake_server.settings == before
    assert not fake_server.sessions and not fake_server.patches
    assert not (out / 'restore-settings.json').exists()
    summary = json.loads((out / 'summary.json').read_text())
    assert summary['workbench_sessions_created'] == 0
    results = json.loads((out / 'results.json').read_text())
    assert all('session_id' not in r for r in results)
    trace = [json.loads(line) for line in (out / results[0]['trace_file']).read_text().splitlines()]
    assert trace[-1]['result']['diagnostics']['output'] == 'test output'


@pytest.mark.parametrize('flag', ['--queue-check', '--worktree-check', '--context-checks'])
def test_direct_rejects_http_only_checks_without_requests(monkeypatch, flag):
    monkeypatch.setattr(runner.Client, 'request', lambda *a, **kw: pytest.fail('unexpected HTTP request'))
    with pytest.raises(SystemExit) as exc:
        runner.main(['--mode', 'direct', flag])
    assert exc.value.code == 2


def test_standalone_worker_error_is_reported_and_next_case_runs(fake_server, tmp_path, monkeypatch):
    calls = []

    def execute(row, timeout):
        calls.append(row['backend'])
        raise RuntimeError('worker unavailable')

    monkeypatch.setattr(runner, 'run_direct', execute)
    out = tmp_path / 'errors'
    assert runner.main(['--mode', 'direct', '--no-all', '--base-url', fake_server.url, '--output-directory', str(out)]) == 1
    assert calls == ['opencode', 'claude']
    results = json.loads((out / 'results.json').read_text())
    assert all(r['status'] == 'FAIL' and 'worker unavailable' in r['exception_traceback'] for r in results)
