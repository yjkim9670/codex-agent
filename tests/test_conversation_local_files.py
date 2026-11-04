"""Real filesystem boundaries for Chat PC reads; no model or account needed."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'conversation-app'))
from services.local_files import LocalFiles, TOOL_NAME, READ_LIMIT, PAGE_SIZE


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
        assert page['offset'] == offset
        assert page['bytes_read'] == len(page['content'].encode('utf-8')) <= READ_LIMIT
        assert page['total_bytes'] == len(text.encode('utf-8'))
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
    names, offset = [], 0
    while True:
        page = value(call(reader, 'list', offset=offset))
        assert 0 < len(page['entries']) <= PAGE_SIZE
        names.extend(entry['name'] for entry in page['entries'])
        offset = page['next_offset']
        if offset is None:
            break
    assert len(names) == len(set(names)) == 205


def test_registry_inventory_and_details_survive_small_pages(files):
    reader, root = files
    items = [{'id': f'item-{i}', 'details': '한글😀\\"\n' * 400} for i in range(17)]
    original = json.dumps(items, ensure_ascii=False)
    (root / 'registry.json').write_text(original, encoding='utf-8')
    chunks, versions, offset = [], set(), 0
    while True:
        page = value(call(reader, 'read', 'registry.json', offset=offset))
        chunks.append(page['content'])
        versions.add(page['file_version'])
        end = offset + page['bytes_read']
        if page['next_offset'] is None:
            assert end == page['total_bytes']
            break
        assert page['next_offset'] == end > offset
        offset = end
    assert len(chunks) > 1 and len(versions) == 1
    assert json.loads(''.join(chunks)) == items
    retry = value(call(reader, 'read', 'registry.json', offset=0, limit=64))
    assert retry['bytes_read'] <= 64
    assert original.startswith(retry['content'])


@pytest.mark.parametrize('limit', [0, 3, 2049, True, '64', None])
def test_invalid_read_limits(files, limit):
    reader, root = files
    (root / 'text').write_text('hello')
    assert not call(reader, 'read', 'text', limit=limit)['success']


def test_utf8_minimum_limit_eof_and_change_detection(files):
    reader, root = files
    path = root / 'text'
    path.write_text('😀한글', encoding='utf-8')
    first = value(call(reader, 'read', 'text', limit=4))
    assert first['content'] == '😀' and first['next_offset'] == 4
    second = value(call(reader, 'read', 'text', offset=4, limit=4))
    assert second['content'] == '한' and second['next_offset'] == 7
    last = value(call(reader, 'read', 'text', offset=7, limit=4))
    assert last['content'] == '글' and last['next_offset'] is None
    path.write_text('changed', encoding='utf-8')
    assert value(call(reader, 'read', 'text'))['file_version'] != first['file_version']
    path.write_text('', encoding='utf-8')
    empty = value(call(reader, 'read', 'text'))
    assert empty['bytes_read'] == empty['total_bytes'] == 0
    assert empty['next_offset'] is None


def test_long_directory_names_are_bounded_and_all_returned(files):
    reader, root = files
    expected = {str(i) + '가' * 70 for i in range(25)}
    for name in expected:
        (root / name).write_text('text')
    actual, offset = [], 0
    while True:
        page = value(call(reader, 'list', offset=offset))
        assert sum(len(json.dumps(entry, ensure_ascii=False).encode('utf-8'))
                   for entry in page['entries']) <= READ_LIMIT
        actual.extend(entry['name'] for entry in page['entries'])
        offset = page['next_offset']
        if offset is None:
            break
    assert set(actual) == expected and len(actual) == len(expected)
