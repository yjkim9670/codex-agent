"""Verify the installed Proc Manager's conversation links."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANAGER = Path('/Users/dinya/works/proc_manager_web.py')


@pytest.fixture
def manager_source():
    if not MANAGER.exists():
        pytest.skip('Local Proc Manager source is not installed')
    return MANAGER


def test_chat_backend_uses_common_tailnet_resolution(manager_source, monkeypatch):
    # The original directory contains the manager's own import dependencies.
    monkeypatch.syspath_prepend(str(MANAGER.parent))
    spec = importlib.util.spec_from_file_location('chat_link_manager_test', manager_source)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'TAILSCALE_HOSTNAME', 'chat.example.ts.net')
    task = module.Task(name='Workbench Chat - conversation server', workdir=str(ROOT),
                       commands=['bash run_conversation_server.sh --port 3101'],
                       open_url='http://127.0.0.1:3101', auto_start=True,
                       sequential=True, restart_on_exit=False)
    assert module.ProcManager._task_kind(task) == 'codex_chat'
    assert module.ProcManager._task_open_url(task) == 'http://chat.example.ts.net:3101'
    assert not module.ProcManager._can_sync_codex_workbench_task(task)


def test_chat_browser_link_matches_dashboard_context(manager_source):
    source = manager_source.read_text()
    functions = source.split('    function parseTaskPort(', 1)[1].split('    function taskCanOpen(', 1)[0]
    script = 'function parseTaskPort(' + functions + '''
const assert = require('node:assert/strict');
const task = {kind: 'codex_chat', port: '3101', open_url: 'http://chat.example.ts.net:3101'};
global.window = {location: {protocol: 'http:', hostname: '127.0.0.1'}};
assert.equal(taskUrl(task), 'http://127.0.0.1:3101');
window.location.hostname = 'chat.example.ts.net';
assert.equal(taskUrl(task), 'http://chat.example.ts.net:3101');
window.location.hostname = '100.80.1.1';
assert.equal(taskUrl(task), 'http://100.80.1.1:3101');
window.location.protocol = 'https:';
assert.equal(taskUrl(task), 'http://chat.example.ts.net:3101');
task.funnel_open_url = 'https://chat.example.ts.net:8443';
assert.equal(taskUrl(task), 'https://chat.example.ts.net:8443');
window.location.protocol = 'http:';
assert.equal(taskUrl(task), 'http://100.80.1.1:3101');
task.open_url = 'http://127.0.0.1:3101/path?q=1#part';
assert.equal(taskUrl(task), 'http://100.80.1.1:3101/path?q=1#part');
task.kind = 'codex_agent';
assert.equal(taskUrl(task), 'http://100.80.1.1:3101/path?q=1#part');
'''
    result = subprocess.run(['node', '-e', script], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
