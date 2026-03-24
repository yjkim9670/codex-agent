from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codex_agent.services import file_browser


@pytest.fixture
def isolated_browser_roots(tmp_path, monkeypatch):
    server_root = (tmp_path / 'server').resolve()
    workspace_root = (tmp_path / 'workspace').resolve()
    server_root.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(file_browser, '_get_server_root', lambda: server_root)
    monkeypatch.setattr(file_browser, 'WORKSPACE_DIR', workspace_root)

    return {
        'server_root': server_root,
        'workspace_root': workspace_root,
    }


def test_list_directory_returns_sorted_entries(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'src').mkdir(parents=True, exist_ok=True)
    (server_root / 'README.md').write_text('hello', encoding='utf-8')

    result = file_browser.list_directory(root_key='server', relative_path='')

    assert result['root'] == 'server'
    assert result['path'] == ''
    assert len(result['entries']) == 2
    assert result['entries'][0]['type'] == 'dir'
    assert result['entries'][0]['path'] == 'src'
    assert result['entries'][1]['type'] == 'file'
    assert result['entries'][1]['path'] == 'README.md'


def test_read_file_detects_html_and_script(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'index.html').write_text('<html><body>ok</body></html>', encoding='utf-8')
    (server_root / 'script.js').write_text('const answer = 42;', encoding='utf-8')

    html_result = file_browser.read_file(root_key='server', relative_path='index.html')
    script_result = file_browser.read_file(root_key='server', relative_path='script.js')

    assert html_result['is_html'] is True
    assert html_result['is_script'] is False
    assert html_result['language'] == 'html'
    assert '<html>' in html_result['content']

    assert script_result['is_html'] is False
    assert script_result['is_script'] is True
    assert script_result['language'] == 'javascript'
    assert 'answer = 42' in script_result['content']


def test_read_file_marks_binary_content(isolated_browser_roots):
    server_root = isolated_browser_roots['server_root']
    (server_root / 'raw.bin').write_bytes(b'\x00\x01\x02\x03')

    result = file_browser.read_file(root_key='server', relative_path='raw.bin')

    assert result['is_binary'] is True
    assert result['content'] == ''
    assert result['line_count'] == 0


def test_list_directory_blocks_parent_path_escape(isolated_browser_roots):
    with pytest.raises(file_browser.FileBrowserError) as exc_info:
        file_browser.list_directory(root_key='server', relative_path='../')

    assert exc_info.value.error_code == 'invalid_path'
