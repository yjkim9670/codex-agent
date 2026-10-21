import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codex_agent import state
from codex_agent.services import codex_chat
from codex_agent.services.claude_diagnostics import observed_lines, summarize_debug_log

spec = importlib.util.spec_from_file_location('startup_probe', ROOT / 'scripts' / 'compare_claude_startup.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_observed_lines_preserves_split_unicode_crlf_and_eof():
    class Chunks:
        def __init__(self):
            self.chunks = iter([b'\xed', b'\x95\x9c\r', b'\nsecond\rthird', b''])

        def read1(self, size):
            return next(self.chunks)

    first = []
    assert list(observed_lines(Chunks(), lambda: first.append(True))) == ['한\n', 'second\n', 'third']
    assert first == [True]
    assert list(observed_lines(io.StringIO('text\n'), lambda: pytest.fail('No byte observation'))) == ['text\n']


def test_reader_observes_byte_before_line(monkeypatch):
    monkeypatch.setenv('CODEX_CLAUDE_STARTUP_DIAGNOSTICS', '1')
    stream_id = 'startup-byte-test'
    state.codex_streams[stream_id] = {
        'claude_startup_diagnostics': True, 'json_output': False, 'output': '',
    }
    monkeypatch.setattr(codex_chat, '_persist_stream_progress', lambda *args, **kwargs: None)
    seen_byte = threading.Event()
    record = codex_chat._record_stream_diagnostic

    def observed(sid, phase):
        record(sid, phase)
        if phase == 'first_stdout_byte':
            seen_byte.set()

    monkeypatch.setattr(codex_chat, '_record_stream_diagnostic', observed)
    read_fd, write_fd = os.pipe()
    pipe = os.fdopen(read_fd, 'r', encoding='utf-8')
    reader = threading.Thread(target=codex_chat._stream_reader, args=(stream_id, pipe, 'output'))
    reader.start()
    try:
        os.write(write_fd, '한'.encode())
        assert seen_byte.wait(3)
        phases = [entry['phase'] for entry in state.codex_streams[stream_id]['diagnostic_timeline']]
        assert 'first_stdout_byte' in phases
        assert 'first_stdout_line' not in phases
        os.write(write_fd, b'\nlast')
    finally:
        os.close(write_fd)
        reader.join(3)
        stream = state.codex_streams.pop(stream_id)
    assert not reader.is_alive()
    assert stream['output'] == '한\nlast'
    assert [entry['phase'] for entry in stream['diagnostic_timeline']].count('first_stdout_byte') == 1


@pytest.mark.parametrize(('company_mode', 'diagnostics', 'expected'), [
    (None, None, False),
    ('0', None, False),
    ('1', None, True),
    (' true ', '', True),
    ('1', '0', False),
    ('1', 'false', False),
    ('0', '1', True),
    (None, ' ON ', True),
])
def test_startup_diagnostics_defaults_to_company_mode(monkeypatch, company_mode, diagnostics, expected):
    for name, value in [('CODEX_COMPANY_MODE', company_mode),
                        ('CODEX_CLAUDE_STARTUP_DIAGNOSTICS', diagnostics)]:
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert codex_chat._claude_startup_diagnostics_enabled() is expected


def test_debug_file_defaults_to_company_mode_and_is_isolated(tmp_path, monkeypatch):
    stream_id = 'startup-debug-test'
    state.codex_streams[stream_id] = {}
    try:
        monkeypatch.delenv('CODEX_CLAUDE_STARTUP_DIAGNOSTICS', raising=False)
        monkeypatch.delenv('CODEX_COMPANY_MODE', raising=False)
        command = ['claude', '-p']
        assert codex_chat._prepare_claude_startup_diagnostics(stream_id, command, tmp_path / 'output') is None
        assert command == ['claude', '-p']
        assert not list(tmp_path.iterdir())
        monkeypatch.setenv('CODEX_COMPANY_MODE', '1')
        path = codex_chat._prepare_claude_startup_diagnostics(stream_id, command, tmp_path / 'output')
        assert path.is_file()
        assert command[-2:] == ['--debug-file', str(path)]
        if os.name != 'nt':
            assert path.stat().st_mode & 0o777 == 0o600
        assert state.codex_streams[stream_id]['claude_startup_diagnostics'] is True
    finally:
        state.codex_streams.pop(stream_id)


def test_debug_summary_is_bounded_and_excludes_raw_payload(tmp_path):
    path = tmp_path / 'debug.log'
    path.write_text('2026-01-01T00:00:00.000Z [DEBUG] mcp secret-key\n'
                    '2026-01-01T00:00:10.720Z [DEBUG] hook private-url\n', encoding='utf-8')
    summary = summarize_debug_log(path)
    assert summary['longest_gaps'] == [{'gap_ms': 10720.0, 'before': 'mcp', 'after': 'hook'}]
    assert summary['categories'] == {'mcp': 1, 'hook': 1}
    assert 'secret-key' not in json.dumps(summary)
    assert 'private-url' not in json.dumps(summary)
    assert summarize_debug_log(path, limit=20)['truncated'] is True
    assert summarize_debug_log(tmp_path / 'absent')['status'] == 'missing'


def test_comparison_changes_one_condition_and_excludes_warmup(tmp_path):
    baseline = ['claude', '-p', '--output-format', 'stream-json', '--verbose']
    assert probe.command_for_case(baseline, 'baseline', tmp_path) == baseline
    debug = probe.command_for_case(baseline, 'baseline_debug', tmp_path)
    assert probe.command_for_case(baseline, 'user_settings', tmp_path) == debug + ['--setting-sources', 'user']
    assert probe.command_for_case(baseline, 'no_commands', tmp_path) == debug + ['--disable-slash-commands']
    command = probe.command_for_case(baseline, 'no_mcp', tmp_path)
    assert '--strict-mcp-config' in command
    assert json.loads((tmp_path / 'empty-mcp.json').read_text()) == {'mcpServers': {}}
    rows = [dict(case='baseline', warmup=warmup, status=status, spawn_to_init_ms=value)
            for warmup, status, value in ((True, 'ok', 999), (False, 'ok', 10),
                                          (False, 'ok', 20), (False, 'failed', 1000))]
    assert probe.summarize(rows)['baseline']['spawn_to_init_ms'] == {'median': 15, 'min': 10, 'max': 20}


def test_probe_collects_synthetic_process_without_model_call(tmp_path):
    command = [sys.executable, '-c',
               'import sys; sys.stdin.buffer.read(); '
               'print(\'{"type":"system","subtype":"init"}\', flush=True); '
               'print(\'{"type":"result"}\', flush=True)']
    result = probe.run_probe(command, '한글'.encode(), str(tmp_path), tmp_path / 'probe', 5, 'synthetic')
    assert result['status'] == 'ok'
    assert result['spawn_to_init_ms'] >= 0
    assert result['byte_to_line_ms'] >= 0
    assert result['exit_code'] == 0


def test_probe_timeout_and_failed_result_are_not_successes(tmp_path):
    result = probe.run_probe([sys.executable, '-c', 'import time; time.sleep(30)'],
                             b'', str(tmp_path), tmp_path / 'timeout', 0.1, 'timeout')
    assert result['status'] == 'timeout'
    result = probe.run_probe([sys.executable, '-c', 'print(\'{"type":"result","is_error":true}\')'],
                             b'', str(tmp_path), tmp_path / 'failed', 3, 'failed')
    assert result['status'] == 'failed'
