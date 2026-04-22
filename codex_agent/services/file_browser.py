"""Filesystem browsing helpers for the Codex web UI."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from ..config import WORKSPACE_DIR

BROWSER_ROOT_SERVER = 'server'
BROWSER_ROOT_WORKSPACE = 'workspace'

_MAX_LIST_ENTRIES = 2000
_MAX_FILE_PREVIEW_BYTES = 512 * 1024
_MAX_FILE_RAW_BYTES = 5 * 1024 * 1024

_LANGUAGE_BY_SUFFIX = {
    '.bash': 'bash',
    '.bat': 'batch',
    '.c': 'c',
    '.cc': 'cpp',
    '.cpp': 'cpp',
    '.css': 'css',
    '.cjs': 'javascript',
    '.go': 'go',
    '.h': 'c',
    '.hpp': 'cpp',
    '.htm': 'html',
    '.html': 'html',
    '.ini': 'ini',
    '.java': 'java',
    '.js': 'javascript',
    '.json': 'json',
    '.jsx': 'javascript',
    '.kt': 'kotlin',
    '.log': 'text',
    '.lua': 'lua',
    '.mjs': 'javascript',
    '.md': 'markdown',
    '.php': 'php',
    '.ps1': 'powershell',
    '.py': 'python',
    '.rb': 'ruby',
    '.rs': 'rust',
    '.sh': 'bash',
    '.sql': 'sql',
    '.swift': 'swift',
    '.toml': 'toml',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.txt': 'text',
    '.xml': 'xml',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.zsh': 'bash',
}

_SCRIPT_LANGUAGES = {
    'bash',
    'batch',
    'go',
    'javascript',
    'kotlin',
    'lua',
    'php',
    'powershell',
    'python',
    'ruby',
    'rust',
    'sql',
    'swift',
    'typescript',
}

_HTML_LANGUAGES = {'html'}
_HTML_TEMPLATE_MARKERS = ('{%', '{{', '{#', '<%')


class FileBrowserError(RuntimeError):
    """Controlled error for file browsing API responses."""

    def __init__(self, message, *, error_code='file_browser_error', status_code=400):
        super().__init__(str(message))
        self.error_code = str(error_code or 'file_browser_error')
        self.status_code = int(status_code)


def _get_server_root():
    return Path.cwd().resolve()


def _get_browser_roots():
    return {
        BROWSER_ROOT_SERVER: _get_server_root(),
        BROWSER_ROOT_WORKSPACE: WORKSPACE_DIR.resolve(),
    }


def _normalize_root_key(value):
    root_key = str(value or '').strip().lower()
    if not root_key:
        root_key = BROWSER_ROOT_SERVER
    roots = _get_browser_roots()
    if root_key not in roots:
        raise FileBrowserError(
            '지원하지 않는 브라우징 루트입니다.',
            error_code='invalid_root',
            status_code=400,
        )
    return root_key, roots[root_key]


def _normalize_relative_path(value):
    source = str(value or '').strip().replace('\\', '/')
    if not source or source == '.':
        return ''
    if source.startswith('/') or source.startswith('~'):
        raise FileBrowserError(
            '상대 경로만 허용됩니다.',
            error_code='invalid_path',
            status_code=400,
        )
    normalized = source.strip('/')
    if not normalized:
        return ''
    if ':' in normalized:
        raise FileBrowserError(
            '드라이브/절대 경로 형식은 허용되지 않습니다.',
            error_code='invalid_path',
            status_code=400,
        )
    parts = []
    for part in normalized.split('/'):
        if not part or part == '.':
            continue
        if part == '..':
            raise FileBrowserError(
                '상위 경로(..)는 허용되지 않습니다.',
                error_code='invalid_path',
                status_code=400,
            )
        if '\x00' in part:
            raise FileBrowserError(
                '유효하지 않은 경로입니다.',
                error_code='invalid_path',
                status_code=400,
            )
        parts.append(part)
    return '/'.join(parts)


def _resolve_target_path(root_path, relative_path):
    target = root_path / relative_path if relative_path else root_path
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise FileBrowserError(
            '루트 경로 밖으로 이동할 수 없습니다.',
            error_code='path_out_of_root',
            status_code=400,
        ) from exc
    return resolved


def _to_relative_path(root_path, target_path):
    relative = target_path.resolve(strict=False).relative_to(root_path)
    text = relative.as_posix()
    return '' if text == '.' else text


def _to_parent_relative_path(relative_path):
    value = str(relative_path or '').strip()
    if not value:
        return ''
    if '/' not in value:
        return ''
    return value.rsplit('/', 1)[0]


def _is_binary_content(data):
    if not data:
        return False
    if b'\x00' in data:
        return True
    control_count = sum(1 for byte in data if byte < 9 or (13 < byte < 32))
    return (control_count / max(1, len(data))) > 0.3


def _guess_language(path):
    suffixes = [suffix.lower() for suffix in path.suffixes]
    for suffix in reversed(suffixes):
        language = _LANGUAGE_BY_SUFFIX.get(suffix)
        if language:
            return language

    name = path.name.lower()
    if name in {'dockerfile', 'makefile'}:
        return 'text'
    return ''


def _looks_like_templated_html(path: Path, *, text: str | None = None, raw: bytes | None = None) -> bool:
    if _guess_language(path) not in _HTML_LANGUAGES:
        return False

    sample = text
    if sample is None and raw:
        sample = raw[:64 * 1024].decode('utf-8', errors='ignore')
    if not sample:
        return False

    return any(marker in sample for marker in _HTML_TEMPLATE_MARKERS)


def list_directory(root_key=None, relative_path=''):
    normalized_root, root_path = _normalize_root_key(root_key)
    normalized_path = _normalize_relative_path(relative_path)
    target_path = _resolve_target_path(root_path, normalized_path)

    if not target_path.exists():
        raise FileBrowserError(
            '경로를 찾을 수 없습니다.',
            error_code='path_not_found',
            status_code=404,
        )
    if not target_path.is_dir():
        raise FileBrowserError(
            '디렉터리 경로만 조회할 수 있습니다.',
            error_code='not_directory',
            status_code=400,
        )

    entries = []
    for child in target_path.iterdir():
        try:
            resolved_child = child.resolve(strict=False)
            resolved_child.relative_to(root_path)
        except (OSError, ValueError):
            continue

        is_dir = resolved_child.is_dir()
        entry_relative_path = _to_relative_path(root_path, resolved_child)
        if not entry_relative_path:
            continue

        size = None
        modified_at = None
        try:
            stats = resolved_child.stat()
            modified_at = int(stats.st_mtime)
            if not is_dir:
                size = int(stats.st_size)
        except OSError:
            pass

        entries.append({
            'name': child.name,
            'path': entry_relative_path,
            'type': 'dir' if is_dir else 'file',
            'size': size,
            'modified_at': modified_at,
        })

    entries.sort(key=lambda item: (item.get('type') != 'dir', item.get('name', '').lower()))
    truncated = len(entries) > _MAX_LIST_ENTRIES
    if truncated:
        entries = entries[:_MAX_LIST_ENTRIES]

    return {
        'root': normalized_root,
        'root_path': str(root_path),
        'path': normalized_path,
        'parent_path': _to_parent_relative_path(normalized_path),
        'can_go_up': bool(normalized_path),
        'entries': entries,
        'truncated': truncated,
    }


def read_file(root_key=None, relative_path=''):
    normalized_root, root_path = _normalize_root_key(root_key)
    normalized_path = _normalize_relative_path(relative_path)
    if not normalized_path:
        raise FileBrowserError(
            '파일 경로를 입력해주세요.',
            error_code='invalid_path',
            status_code=400,
        )

    target_path = _resolve_target_path(root_path, normalized_path)
    if not target_path.exists():
        raise FileBrowserError(
            '파일을 찾을 수 없습니다.',
            error_code='path_not_found',
            status_code=404,
        )
    if not target_path.is_file():
        raise FileBrowserError(
            '파일만 열 수 있습니다.',
            error_code='not_file',
            status_code=400,
        )

    total_bytes = None
    try:
        total_bytes = int(target_path.stat().st_size)
    except OSError:
        total_bytes = None

    try:
        with target_path.open('rb') as file_handle:
            raw = file_handle.read(_MAX_FILE_PREVIEW_BYTES + 1)
    except OSError as exc:
        raise FileBrowserError(
            f'파일을 읽을 수 없습니다: {exc}',
            error_code='read_error',
            status_code=500,
        ) from exc

    truncated = len(raw) > _MAX_FILE_PREVIEW_BYTES
    if truncated:
        raw = raw[:_MAX_FILE_PREVIEW_BYTES]

    is_binary = _is_binary_content(raw)
    language = _guess_language(target_path)
    mime_type = mimetypes.guess_type(target_path.name)[0] or ''
    is_html = language in _HTML_LANGUAGES
    is_script = language in _SCRIPT_LANGUAGES

    if is_binary:
        content = ''
        line_count = 0
    else:
        content = raw.decode('utf-8', errors='replace')
        line_count = content.count('\n') + (1 if content else 0)
    html_previewable = is_html and not _looks_like_templated_html(target_path, text=content)

    return {
        'root': normalized_root,
        'root_path': str(root_path),
        'path': normalized_path,
        'name': target_path.name,
        'mime_type': mime_type,
        'language': language,
        'is_html': is_html,
        'html_previewable': html_previewable,
        'is_script': is_script,
        'is_binary': is_binary,
        'size': total_bytes,
        'truncated': truncated,
        'line_count': line_count,
        'content': content,
    }


def read_file_raw(root_key=None, relative_path=''):
    normalized_root, root_path = _normalize_root_key(root_key)
    normalized_path = _normalize_relative_path(relative_path)
    if not normalized_path:
        raise FileBrowserError(
            '파일 경로를 입력해주세요.',
            error_code='invalid_path',
            status_code=400,
        )

    target_path = _resolve_target_path(root_path, normalized_path)
    if not target_path.exists():
        raise FileBrowserError(
            '파일을 찾을 수 없습니다.',
            error_code='path_not_found',
            status_code=404,
        )
    if not target_path.is_file():
        raise FileBrowserError(
            '파일만 열 수 있습니다.',
            error_code='not_file',
            status_code=400,
        )

    try:
        total_bytes = int(target_path.stat().st_size)
    except OSError as exc:
        raise FileBrowserError(
            f'파일 정보를 확인할 수 없습니다: {exc}',
            error_code='read_error',
            status_code=500,
        ) from exc

    if total_bytes > _MAX_FILE_RAW_BYTES:
        raise FileBrowserError(
            '동적 미리보기 제공 크기 제한(5MB)을 초과했습니다.',
            error_code='file_too_large',
            status_code=413,
        )

    try:
        content = target_path.read_bytes()
    except OSError as exc:
        raise FileBrowserError(
            f'파일을 읽을 수 없습니다: {exc}',
            error_code='read_error',
            status_code=500,
        ) from exc

    mime_type = mimetypes.guess_type(target_path.name)[0] or 'application/octet-stream'
    if mime_type.startswith('text/html') and _looks_like_templated_html(target_path, raw=content):
        mime_type = 'text/plain'
    return {
        'root': normalized_root,
        'root_path': str(root_path),
        'path': normalized_path,
        'name': target_path.name,
        'mime_type': mime_type,
        'size': total_bytes,
        'content': content,
    }
