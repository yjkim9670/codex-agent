import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_agent import config, state
from codex_agent.services import codex_chat as chat


@pytest.fixture(autouse=True)
def isolated_streams():
    with state.codex_streams_lock:
        state.codex_streams.clear()
    yield
    with state.codex_streams_lock:
        state.codex_streams.clear()


def test_duplex_pipes_drain_before_large_prompt_is_written():
    script = 'import sys; sys.stdout.write("x"*262144+"\\n"); sys.stdout.flush(); sys.stderr.write("y"*262144+"\\n"); sys.stderr.flush(); print(len(sys.stdin.read()))'
    state.codex_streams['duplex'] = {'json_output': False, 'output': '', 'error': ''}
    process = subprocess.Popen([sys.executable, '-c', script], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        readers, written = chat._start_stream_io('duplex', process, 'p' * 524288)
        assert written.wait(5), 'prompt write deadlocked behind child output'
        assert process.wait(timeout=5) == 0
        for reader in readers:
            reader.join(timeout=2)
            assert not reader.is_alive()
        assert '524288' in state.codex_streams['duplex']['output']
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_native_claude_preserves_credentials_endpoint_and_models(monkeypatch):
    monkeypatch.setenv('CODEX_CLAUDE_ENV_MODE', 'native')
    values = {'ANTHROPIC_AUTH_TOKEN': 'private-test-token', 'ANTHROPIC_BASE_URL': 'https://native.test',
              'ANTHROPIC_DEFAULT_OPUS_MODEL': 'opus-native', 'CLAUDE_CODE_SUBAGENT_MODEL': 'sub-native'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('CODEX_DTGPT_HEALTH_URL', 'https://company.test/health')
    monkeypatch.setenv('CODEX_CLAUDE_BASE_URL', 'https://company.test')
    monkeypatch.setattr(chat, '_build_codex_exec_env', lambda **kw: pytest.fail('Codex setup invoked'))
    monkeypatch.setattr(chat, '_apply_spreadsheet_runtime_env', lambda env: env)
    env = chat._build_agent_exec_env('claude', queued_execution=True)
    chat._apply_claude_company_exec_env(env, model_override='company-model')
    assert all(env[key] == value for key, value in values.items())
    monkeypatch.setattr(config, '_read_claude_model_catalog', lambda: [{'slug': 'native-model'}])
    assert config.get_claude_model_catalog() == [{'slug': 'native-model'}]
    cmd = chat._build_claude_command('hello')
    assert '--model' not in cmd
    assert '--effort' not in cmd


def test_claude_company_environment_avoids_codex_setup(monkeypatch):
    monkeypatch.delenv('CODEX_CLAUDE_ENV_MODE', raising=False)
    monkeypatch.setattr(chat, '_apply_workbench_python_env', lambda env: pytest.fail('Python probe invoked'))
    monkeypatch.setattr(chat, '_prepare_codex_home_extensions', lambda *args: pytest.fail('extensions invoked'))
    monkeypatch.setattr(chat, '_apply_spreadsheet_runtime_env', lambda env: env)
    env = chat._build_agent_exec_env('claude', queued_execution=True)
    assert chat._WORKBENCH_WORKSPACE_DIR_ENV in env


def test_claude_partial_text_is_not_duplicated_by_complete_message():
    state.codex_streams['partial'] = {'output': '', 'error': ''}
    events = [
        {'type': 'stream_event', 'event': {'type': 'message_start'}},
        {'type': 'stream_event', 'event': {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'hello '}}},
        {'type': 'stream_event', 'event': {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'world'}}},
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hello world'}]}},
        {'type': 'result', 'result': 'hello world'},
    ]
    for event in events:
        chat._handle_claude_stream_json_output_line('partial', json.dumps(event))
    assert state.codex_streams['partial']['output'] == 'hello world'
    assert state.codex_streams['partial']['task_complete_seen']


def test_manifest_compaction_keeps_notes_and_trailing_instructions():
    record = {'version': 1, 'context_sha256': 'a' * 64, 'memory': [{'text': 'constraint ' * 100}]}
    prefix = '## Source-linked Context Notes\nconstraint\n'
    prompt = prefix + '## Context Selection Record\n' + json.dumps(record) + '\n## Instructions\nkeep me'
    result = chat._compact_context_manifest(prompt)
    assert result.startswith(prefix)
    assert result.endswith('\n## Instructions\nkeep me')
    assert len(result) < len(prompt)


def test_windows_lock_timeout_uses_nonblocking_lock(monkeypatch, tmp_path):
    class WindowsLock:
        LK_NBLCK = 2
        @staticmethod
        def locking(fd, mode, size):
            assert mode == WindowsLock.LK_NBLCK
            raise OSError('busy')
    monkeypatch.setattr(chat, 'fcntl', None)
    monkeypatch.setattr(chat, 'msvcrt', WindowsLock)
    with (tmp_path / 'lock').open('a+') as handle:
        with pytest.raises(TimeoutError):
            chat._lock_file_handle(handle, timeout_seconds=0.05)


@pytest.mark.skipif(chat.fcntl is None, reason='requires POSIX flock')
def test_gate_wait_can_be_cancelled_without_erasing_owner(tmp_path):
    path = tmp_path / 'gate'
    with chat._acquire_codex_exec_lock(path):
        owner = path.read_text()
        with pytest.raises(RuntimeError, match='cancelled'):
            with chat._acquire_codex_exec_lock(path, cancelled=lambda: True):
                pytest.fail('cancelled waiter acquired gate')
        assert path.read_text() == owner


def test_gate_timeout_is_saved_with_specific_reason(monkeypatch):
    stream = {'output': '', 'error': ''}
    state.codex_streams['waiting'] = stream
    def wait_for_gate(*args):
        chat._record_stream_diagnostic('waiting', 'waiting_execution_gate')
        raise TimeoutError('gate busy')
    saved = []
    monkeypatch.setattr(chat, '_run_codex_stream_impl', wait_for_gate)
    monkeypatch.setattr(chat, 'finalize_codex_stream', saved.append)
    chat._run_codex_stream('waiting', 'hello')
    assert stream['finalize_reason'] == 'execution_gate_timeout'
    assert saved == ['waiting']


@pytest.mark.parametrize('limit,reason,prompt', [
    ('CODEX_CLI_STDIN_TIMEOUT_SECONDS', 'stdin_timeout', 'p' * 1048576),
    ('CODEX_CLI_PROGRESS_TIMEOUT_SECONDS', 'progress_timeout', 'hello'),
    ('CODEX_CLI_EXEC_TIMEOUT_SECONDS', 'execution_timeout', 'hello'),
], ids=['stdin', 'progress', 'execution'])
def test_stream_limits_terminate_running_child(monkeypatch, tmp_path, limit, reason, prompt):
    monkeypatch.setenv(limit, '0.1')
    monkeypatch.setattr(chat, 'WORKSPACE_DIR', tmp_path)
    monkeypatch.setattr(chat, 'CODEX_STORAGE_DIR', tmp_path)
    monkeypatch.setattr(chat, 'CODEX_CLI_EXEC_LOCK', False)
    monkeypatch.setattr(chat, 'CODEX_STREAM_POLL_INTERVAL_SECONDS', 0.05)
    monkeypatch.setattr(chat, '_prepare_agent_execution', lambda text, stream: (text, {
        'agent_backend': 'claude', 'execution_cwd': str(tmp_path), 'environment': 'test'}))
    monkeypatch.setattr(chat, '_build_agent_exec_env', lambda *a, **kw: os.environ.copy())
    monkeypatch.setattr(chat, '_apply_agent_backend_exec_env', lambda *a, **kw: None)
    monkeypatch.setattr(chat, '_build_agent_command', lambda *a, **kw: ('claude', [sys.executable, '-c', 'import time; time.sleep(30)']))
    monkeypatch.setattr(chat, '_wrap_codex_cli_command', lambda cmd, **kw: cmd)
    monkeypatch.setattr(chat, '_prepare_imagegen_workbench_dirs', lambda *a: None)
    monkeypatch.setattr(chat, 'finalize_codex_stream', lambda *a, **kw: None)
    monkeypatch.setattr(chat, '_copy_imagegen_workbench_outputs_for_stream', lambda *a: [])
    stream = {'agent_backend': 'claude', 'started_at': time.time(), 'question_only': True,
              'output_path': str(tmp_path / 'output'), 'json_output': True, 'output': '', 'error': ''}
    state.codex_streams['limited'] = stream
    started = time.monotonic()
    chat._run_codex_stream('limited', prompt)
    assert time.monotonic() - started < 5
    assert stream['finalize_reason'] == reason
    assert stream['exit_code'] == 124
    assert stream['process'] is None
