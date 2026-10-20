import os
from pathlib import Path
import subprocess
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent.services import codex_chat


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    executable = tmp_path / 'runtime' / 'python'
    executable.parent.mkdir()
    executable.touch(mode=0o755)
    monkeypatch.setattr(sys, 'executable', str(executable))
    return str(executable)


@pytest.mark.parametrize('platform,version,accepted', [
    ('win32', '3.10', True),
    ('win32', '3.13', True),
    ('win32', '3.14', True),
    ('win32', '3.9', False),
    ('win32', '4.0', False),
    ('darwin', '3.14', True),
    ('darwin', '3.13', False),
    ('linux', '3.14', True),
    ('linux', '3.10', False),
])
def test_runtime_policy(monkeypatch, runtime, platform, version, accepted):
    monkeypatch.setattr(sys, 'platform', platform)
    monkeypatch.setattr(codex_chat.shutil, 'which', lambda *args, **kwargs: None)
    monkeypatch.setattr(codex_chat, '_WORKBENCH_PYTHON_DEFAULT', '/missing/python')
    calls = []

    def probe(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, version, '')

    monkeypatch.setattr(codex_chat.subprocess, 'run', probe)
    env = {'PATH': '/original/bin'}
    if accepted:
        assert codex_chat._apply_workbench_python_env(env) is env
        for key in ('CODEX_PYTHON_BIN', 'PYTHON_BIN', 'PYTHON'):
            assert env[key] == runtime
        assert env['PATH'].split(os.pathsep)[0] == str(Path(runtime).parent)
    else:
        with pytest.raises(RuntimeError, match=f'version={version}'):
            codex_chat._apply_workbench_python_env(env)
    assert len(calls) == 1
    assert calls[0][0][0] == runtime
    assert calls[0][1]['timeout'] == 5
    assert calls[0][1]['env'] is env


@pytest.mark.parametrize('failure', ['timeout', 'oserror', 'invalid', 'nonzero'])
def test_configured_runtime_failure_has_diagnostics(monkeypatch, runtime, failure):
    monkeypatch.setattr(sys, 'platform', 'win32')

    def probe(cmd, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(cmd, 5)
        if failure == 'oserror':
            raise OSError('cannot execute')
        return subprocess.CompletedProcess(cmd, 1 if failure == 'nonzero' else 0,
                                           'invalid' if failure == 'invalid' else '3.14', '')

    monkeypatch.setattr(codex_chat.subprocess, 'run', probe)
    expected = {'timeout': 'TimeoutExpired', 'oserror': 'OSError',
                'invalid': 'ValueError', 'nonzero': 'exit=1'}[failure]
    with pytest.raises(RuntimeError, match=expected):
        codex_chat._apply_workbench_python_env({'CODEX_PYTHON_BIN': runtime})


def test_explicit_missing_runtime_does_not_silently_fallback(runtime):
    with pytest.raises(RuntimeError, match='Configured Python executable is unavailable'):
        codex_chat._apply_workbench_python_env({'CODEX_PYTHON_BIN': '/missing/python'})


def test_fallback_uses_child_path(monkeypatch, runtime):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(sys, 'executable', '/missing/server-python')
    searches = []

    def which(command, path=None):
        searches.append((command, path))
        return runtime

    monkeypatch.setattr(codex_chat.shutil, 'which', which)
    monkeypatch.setattr(codex_chat.subprocess, 'run', lambda cmd, **kwargs:
                        subprocess.CompletedProcess(cmd, 0, '3.12', ''))
    env = codex_chat._apply_workbench_python_env({'PATH': '/child/bin'})
    assert searches == [('python', '/child/bin')]
    assert env['PYTHON'] == runtime


def test_automatic_probe_timeout_continues_to_next_candidate(monkeypatch, runtime, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'win32')
    fallback = tmp_path / 'fallback-python'
    fallback.touch(mode=0o755)
    monkeypatch.setattr(codex_chat.shutil, 'which', lambda *args, **kwargs: str(fallback))
    calls = []

    def probe(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == runtime:
            raise subprocess.TimeoutExpired(cmd, kwargs['timeout'])
        return subprocess.CompletedProcess(cmd, 0, '3.11', '')

    monkeypatch.setattr(codex_chat.subprocess, 'run', probe)
    env = codex_chat._apply_workbench_python_env({})
    assert calls == [runtime, str(fallback)]
    assert env['PYTHON'] == str(fallback)


def test_virtualenv_directory_is_preserved(monkeypatch, runtime, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    venv_python = tmp_path / 'venv' / 'bin' / 'python'
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(runtime)
    monkeypatch.setattr(codex_chat.subprocess, 'run', lambda cmd, **kwargs:
                        subprocess.CompletedProcess(cmd, 0, '3.14', ''))
    env = codex_chat._apply_workbench_python_env({'CODEX_PYTHON_BIN': str(venv_python)})
    assert env['PATH'] == str(venv_python.parent)
    assert env['PYTHON'] == str(venv_python)
