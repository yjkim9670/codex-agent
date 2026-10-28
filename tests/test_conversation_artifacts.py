"""Exercise filesystem boundaries with real files; no Codex credentials needed."""
import io
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'conversation-app'))
from services.artifacts import Artifacts, TOOL_NAME
from services.codex_provider import RPC


@pytest.fixture
def artifacts():
    value = Artifacts()
    yield value
    value.close()
    shutil.rmtree(value.root)


def call(artifacts, operation, path, **extra):
    return artifacts.call({'tool': TOOL_NAME, 'arguments': {'operation': operation, 'path': path, **extra}})


def test_artifact_lifecycle(artifacts):
    assert str(artifacts.root).startswith('/tmp/workbench-chat-')
    for text in ('hello', '수정한 산출물'):
        assert call(artifacts, 'write', 'docs/result.md', content=text)['success']
        result = call(artifacts, 'read', 'docs/result.md')
        assert json.loads(result['contentItems'][0]['text'])['content'] == text
    path = artifacts.root / 'docs/result.md'
    assert path.stat().st_mode & 0o777 == 0o600
    assert call(artifacts, 'delete', 'docs/result.md')['success']
    assert not path.exists()


@pytest.mark.parametrize('path', ['/tmp/other', '../repository/file', 'dir/../../escape', '', '.', 'dir//file', 'dir/../file', 'x\x00y', 'dir\\file'])
def test_path_escape_is_rejected(artifacts, path):
    for operation in ('write', 'read', 'delete'):
        assert not call(artifacts, operation, path, content='changed')['success']


def test_links_and_special_files_cannot_access_local_repository(artifacts, tmp_path):
    outside = tmp_path / 'repository'
    outside.mkdir()
    target = outside / 'source.txt'
    target.write_text('unchanged')
    (artifacts.root / 'symlink').symlink_to(target)
    (artifacts.root / 'directory').symlink_to(outside, target_is_directory=True)
    os.link(target, artifacts.root / 'hardlink')
    os.mkfifo(artifacts.root / 'fifo')
    for path in ('symlink', 'hardlink', 'directory/source.txt', 'fifo'):
        for operation in ('write', 'read', 'delete'):
            assert not call(artifacts, operation, path, content='changed')['success']
    assert target.read_text() == 'unchanged'


def test_unregistered_tool_and_size_limit(artifacts):
    assert not artifacts.call({'tool': 'shell', 'arguments': {'command': 'touch file'}})['success']
    assert not call(artifacts, 'write', 'big.txt', content='x' * (1024 * 1024 + 1))['success']
    assert not call(artifacts, 'execute', 'file.py')['success']


def test_rpc_dispatches_only_artifact_calls_and_denies_approvals(artifacts):
    # Exercise the real JSON-RPC reader without spawning a worker or model.
    requests = [
        {'id': 1, 'method': 'item/tool/call', 'params': {'tool': TOOL_NAME, 'arguments': {'operation': 'write', 'path': 'result.txt', 'content': 'saved'}}},
        {'id': 2, 'method': 'item/tool/call', 'params': {'tool': 'shell', 'arguments': {}}},
        {'id': 3, 'method': 'item/commandExecution/requestApproval', 'params': {}},
    ]
    rpc = RPC.__new__(RPC)
    rpc.process = type('Process', (), {'stdout': io.StringIO('\n'.join(map(json.dumps, requests)))})()
    rpc.pending, rpc.events, rpc.lock = {}, queue.Queue(), threading.Lock()
    rpc.artifact_handler = artifacts.call
    replies = []
    rpc.send = replies.append
    rpc._read()
    assert replies[0]['result']['success']
    assert not replies[1]['result']['success']
    assert replies[2]['error']['code'] == -32601
    assert (artifacts.root / 'result.txt').read_text() == 'saved'


def test_followup_can_reopen_only_the_same_private_artifacts(artifacts):
    assert call(artifacts, 'write', 'result.txt', content='first')['success']
    followup = Artifacts(artifacts.root)
    try:
        assert call(followup, 'write', 'result.txt', content='second')['success']
        assert (artifacts.root / 'result.txt').read_text() == 'second'
    finally:
        followup.close()
