"""Real filesystem boundaries for Chat PC reads; no model or account needed."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'conversation-app'))
from services.local_files import LocalFiles, TOOL_NAME, READ_LIMIT


@pytest.fixture
def files(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    monkeypatch.setenv('CHAT_READ_ONLY_ROOTS', str(root))
    return LocalFiles(excluded=(root / 'private-state',)), root


def call(files, operation, path='', **extra):
    return files.call({'tool': TOOL_NAME, 'arguments': {
        'operation': operation, 'root': '0', 'path': path, **extra}})


def value(reply):
    assert reply['success'], reply
    return json.loads(reply['contentItems'][0]['text'])


def test_reads_listing_and_utf8_pages(files):
    reader, root = files
    (root / 'docs').mkdir()
    text = '한' * READ_LIMIT
    (root / 'docs/file.txt').write_text(text)
    assert value(call(reader, 'roots'))['roots'] == [{'id': '0', 'path': str(root)}]
    assert value(call(reader, 'list'))['entries'] == [{'name': 'docs', 'type': 'directory'}]
    content, offset = '', 0
    while True:
        page = value(call(reader, 'read', 'docs/file.txt', offset=offset))
        content += page['content']
        offset = page['next_offset']
        if offset is None:
            break
    assert content == text
    assert (root / 'docs/file.txt').read_text() == text


@pytest.mark.parametrize('path', ['../outside', '/etc/passwd', 'docs/../secret', '.', '.env',
                                  'x/.git/config', 'auth.json', 'secret.pem', 'x\\file', 'x\x00y'])
def test_rejects_traversal_and_secret_paths(files, path):
    reader, root = files
    for operation in ('read', 'list', 'write', 'delete', 'execute'):
        assert not call(reader, operation, path)['success']


def test_links_special_files_state_and_binary_are_blocked(files, tmp_path):
    reader, root = files
    outside = tmp_path / 'outside'
    outside.write_text('secret')
    (root / 'link').symlink_to(outside)
    (root / 'dirlink').symlink_to(tmp_path, target_is_directory=True)
    os.link(outside, root / 'hardlink')
    os.mkfifo(root / 'pipe')
    (root / 'private-state').mkdir()
    (root / 'private-state/data.txt').write_text('internal')
    (root / 'binary').write_bytes(b'\x00\xff')
    (root / '.env').write_text('secret')
    for path in ('link', 'dirlink/outside', 'hardlink', 'pipe', 'private-state/data.txt', 'binary'):
        assert not call(reader, 'read', path)['success']
    names = {entry['name'] for entry in value(call(reader, 'list'))['entries']}
    assert names == {'binary'}
    assert outside.read_text() == 'secret'
    assert not reader.call({'tool': 'shell', 'arguments': {}})['success']
    assert not call(reader, 'read', 'binary', content='overwrite')['success']
    assert not call(reader, 'read', 'binary', root='other')['success']


def test_root_scope_disabled_and_multi_root_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv('CHAT_READ_ONLY_ROOTS', '')
    reader = LocalFiles()
    assert value(call(reader, 'roots')) == {'roots': []}
    assert not call(reader, 'list')['success']
    monkeypatch.setenv('CHAT_READ_ONLY_ROOTS', os.pathsep.join([str(tmp_path / 'one'), str(tmp_path / 'two')]))
    assert len(LocalFiles().roots) == 2
    monkeypatch.setenv('CHAT_READ_ONLY_ROOTS', '/')
    with pytest.raises(ValueError):
        LocalFiles()
    account_home = tmp_path / 'account-home'
    monkeypatch.setattr('services.local_files.pwd.getpwuid', lambda uid: SimpleNamespace(pw_dir=str(account_home)))
    monkeypatch.setenv('CHAT_READ_ONLY_ROOTS', str(account_home))
    with pytest.raises(ValueError):
        LocalFiles()


def test_default_scope_includes_sibling_work_folders(tmp_path, monkeypatch):
    monkeypatch.delenv('CHAT_READ_ONLY_ROOTS', raising=False)
    works = tmp_path / 'works'
    monkeypatch.setenv('HOME', str(works))
    source = works / 'dev_workspace/codex_workbench/conversation-app/services/local_files.py'
    source.parent.mkdir(parents=True)
    monkeypatch.setattr('services.local_files.__file__', str(source))
    sibling = works / 'another-project'
    sibling.mkdir()
    (sibling / 'notes.txt').write_text('read-only reference')
    reader = LocalFiles()
    assert value(call(reader, 'roots'))['roots'] == [{'id': '0', 'path': str(works)}]
    assert value(call(reader, 'read', 'another-project/notes.txt'))['content'] == 'read-only reference'
    assert not call(reader, 'read', '../outside.txt')['success']
    assert not call(reader, 'write', 'another-project/notes.txt')['success']
    assert (sibling / 'notes.txt').read_text() == 'read-only reference'


def test_directory_pagination(files):
    reader, root = files
    for n in range(205):
        (root / str(n)).write_text('text')
    first = value(call(reader, 'list'))
    second = value(call(reader, 'list', offset=first['next_offset']))
    assert len(first['entries']) == 200
    assert len(second['entries']) == 5 and second['next_offset'] is None
