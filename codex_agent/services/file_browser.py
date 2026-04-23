"""Filesystem browsing helpers for the Codex web UI."""

from __future__ import annotations

import io
import mimetypes
import shutil
import tempfile
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ..config import WORKSPACE_DIR

BROWSER_ROOT_SERVER = 'server'
BROWSER_ROOT_WORKSPACE = 'workspace'

_MAX_LIST_ENTRIES = 2000
_MAX_FILE_PREVIEW_BYTES = 512 * 1024
_MAX_FILE_RAW_BYTES = 5 * 1024 * 1024
_MAX_FILE_EDIT_BYTES = 512 * 1024
_MAX_FILE_DOWNLOAD_BYTES = 64 * 1024 * 1024
_MAX_MULTI_DOWNLOAD_TOTAL_BYTES = 128 * 1024 * 1024
_DELETE_QUARANTINE_PREFIX = '.codex-delete-'

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
_EDITABLE_TEXT_SUFFIXES = {
    '.bash',
    '.bat',
    '.c',
    '.cc',
    '.cfg',
    '.conf',
    '.cpp',
    '.css',
    '.csv',
    '.cxx',
    '.go',
    '.h',
    '.hpp',
    '.htm',
    '.html',
    '.ini',
    '.java',
    '.js',
    '.json',
    '.jsonl',
    '.jsx',
    '.kt',
    '.log',
    '.lua',
    '.md',
    '.mjs',
    '.php',
    '.ps1',
    '.py',
    '.rb',
    '.rs',
    '.scss',
    '.sh',
    '.sql',
    '.swift',
    '.toml',
    '.ts',
    '.tsx',
    '.txt',
    '.xml',
    '.yaml',
    '.yml',
    '.zsh',
}
_EDITABLE_TEXT_FILENAMES = {
    '.dockerignore',
    '.editorconfig',
    '.env',
    '.env.example',
    '.gitattributes',
    '.gitignore',
    'dockerfile',
    'makefile',
    'procfile',
}


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


def _normalize_relative_paths(values):
    if isinstance(values, str):
        source_values = [values]
    elif isinstance(values, (list, tuple, set)):
        source_values = list(values)
    else:
        raise FileBrowserError(
            '파일 경로 목록을 확인할 수 없습니다.',
            error_code='invalid_path',
            status_code=400,
        )

    normalized_paths = []
    seen = set()
    for value in source_values:
        normalized = _normalize_relative_path(value)
        if not normalized:
            raise FileBrowserError(
                '파일 경로를 입력해주세요.',
                error_code='invalid_path',
                status_code=400,
            )
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_paths.append(normalized)

    if not normalized_paths:
        raise FileBrowserError(
            '파일 경로를 입력해주세요.',
            error_code='invalid_path',
            status_code=400,
        )
    return normalized_paths


def _resolve_file_targets(root_key=None, relative_paths=None):
    normalized_root, root_path = _normalize_root_key(root_key)
    normalized_paths = _normalize_relative_paths(relative_paths)
    targets = []
    for relative_path in normalized_paths:
        target_path = _resolve_target_path(root_path, relative_path)
        if not target_path.exists():
            raise FileBrowserError(
                f'파일을 찾을 수 없습니다: {relative_path}',
                error_code='path_not_found',
                status_code=404,
            )
        if not target_path.is_file():
            raise FileBrowserError(
                f'파일만 대상으로 선택할 수 있습니다: {relative_path}',
                error_code='not_file',
                status_code=400,
            )
        try:
            size = int(target_path.stat().st_size)
        except OSError:
            size = None
        targets.append({
            'relative_path': relative_path,
            'target_path': target_path,
            'name': target_path.name,
            'size': size,
        })
    return normalized_root, root_path, targets


def _ensure_existing_directory(root_path, relative_path):
    normalized_directory = _normalize_relative_path(relative_path)
    target_directory = _resolve_target_path(root_path, normalized_directory)
    if not target_directory.exists():
        raise FileBrowserError(
            '대상 폴더를 찾을 수 없습니다.',
            error_code='path_not_found',
            status_code=404,
        )
    if not target_directory.is_dir():
        raise FileBrowserError(
            '대상 경로는 폴더여야 합니다.',
            error_code='not_directory',
            status_code=400,
        )
    return normalized_directory, target_directory


def _build_download_archive_name():
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    return f'codex-files-{timestamp}.zip'


def _extract_file_metadata(target_path: Path):
    try:
        stats = target_path.stat()
    except OSError as exc:
        raise FileBrowserError(
            f'파일 정보를 확인할 수 없습니다: {exc}',
            error_code='read_error',
            status_code=500,
        ) from exc

    modified_ns = getattr(stats, 'st_mtime_ns', None)
    if modified_ns is None:
        modified_ns = int(stats.st_mtime * 1_000_000_000)
    return {
        'size': int(stats.st_size),
        'modified_at': int(stats.st_mtime),
        'modified_ns': str(int(modified_ns)),
    }


def _decode_utf8_preview(raw: bytes):
    if not raw:
        return '', 0, True
    try:
        content = raw.decode('utf-8')
        is_utf8_text = True
    except UnicodeDecodeError:
        content = raw.decode('utf-8', errors='replace')
        is_utf8_text = False
    line_count = content.count('\n') + (1 if content else 0)
    return content, line_count, is_utf8_text


def _is_editable_text_path(path: Path):
    lowered_name = path.name.lower()
    if lowered_name in _EDITABLE_TEXT_FILENAMES:
        return True
    for suffix in reversed(path.suffixes):
        if suffix.lower() in _EDITABLE_TEXT_SUFFIXES:
            return True
    return False


def _normalize_expected_modified_ns(value):
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    if not text.isdigit():
        raise FileBrowserError(
            '파일 버전 정보가 올바르지 않습니다.',
            error_code='invalid_version',
            status_code=400,
        )
    return text


def _build_move_operations(root_path, targets, *, destination_path=None, destination_directory=None):
    operations = []
    source_relative_paths = {item['relative_path'] for item in targets}
    destination_relative_paths = set()

    if len(targets) == 1:
        if destination_path is None:
            raise FileBrowserError(
                '새 파일 경로를 입력해주세요.',
                error_code='invalid_path',
                status_code=400,
            )
        normalized_destination = _normalize_relative_path(destination_path)
        if not normalized_destination:
            raise FileBrowserError(
                '새 파일 경로를 입력해주세요.',
                error_code='invalid_path',
                status_code=400,
            )
        destination_target = _resolve_target_path(root_path, normalized_destination)
        source_target = targets[0]['target_path']
        if destination_target == source_target:
            raise FileBrowserError(
                '기존 경로와 다른 대상 경로를 입력해주세요.',
                error_code='invalid_path',
                status_code=400,
            )
        if not destination_target.parent.exists() or not destination_target.parent.is_dir():
            raise FileBrowserError(
                '대상 폴더를 찾을 수 없습니다.',
                error_code='path_not_found',
                status_code=404,
            )
        operations.append({
            'source_relative_path': targets[0]['relative_path'],
            'source_path': source_target,
            'destination_relative_path': normalized_destination,
            'destination_path': destination_target,
        })
    else:
        if destination_directory is None:
            raise FileBrowserError(
                '대상 폴더 경로를 입력해주세요.',
                error_code='invalid_path',
                status_code=400,
            )
        normalized_directory, destination_directory_path = _ensure_existing_directory(
            root_path,
            destination_directory,
        )
        for target in targets:
            destination_target = destination_directory_path / target['name']
            destination_relative_path = _to_relative_path(root_path, destination_target)
            if destination_target == target['target_path']:
                raise FileBrowserError(
                    '같은 폴더로는 여러 파일을 이동할 수 없습니다.',
                    error_code='invalid_path',
                    status_code=400,
                )
            operations.append({
                'source_relative_path': target['relative_path'],
                'source_path': target['target_path'],
                'destination_relative_path': destination_relative_path,
                'destination_path': destination_target,
                'destination_directory': normalized_directory,
            })

    for operation in operations:
        destination_relative_path = operation['destination_relative_path']
        destination_path = operation['destination_path']
        if destination_relative_path in destination_relative_paths:
            raise FileBrowserError(
                '이동 대상 파일명이 서로 충돌합니다.',
                error_code='path_conflict',
                status_code=400,
            )
        destination_relative_paths.add(destination_relative_path)
        if destination_relative_path in source_relative_paths:
            raise FileBrowserError(
                '기존 파일 경로와 충돌하는 대상이 있습니다.',
                error_code='path_conflict',
                status_code=400,
            )
        if destination_path.exists():
            raise FileBrowserError(
                f'대상 파일이 이미 존재합니다: {destination_relative_path}',
                error_code='path_conflict',
                status_code=409,
            )

    return operations


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

    metadata = _extract_file_metadata(target_path)

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
        is_utf8_text = False
    else:
        content, line_count, is_utf8_text = _decode_utf8_preview(raw)
    html_previewable = is_html and not _looks_like_templated_html(target_path, text=content)
    editable = (
        not is_binary
        and not truncated
        and is_utf8_text
        and _is_editable_text_path(target_path)
    )

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
        'size': metadata['size'],
        'modified_at': metadata['modified_at'],
        'modified_ns': metadata['modified_ns'],
        'truncated': truncated,
        'editable': editable,
        'line_count': line_count,
        'content': content,
    }


def write_file(root_key=None, relative_path='', content='', expected_modified_ns=None):
    normalized_root, root_path = _normalize_root_key(root_key)
    normalized_path = _normalize_relative_path(relative_path)
    if not normalized_path:
        raise FileBrowserError(
            '파일 경로를 입력해주세요.',
            error_code='invalid_path',
            status_code=400,
        )
    if not isinstance(content, str):
        raise FileBrowserError(
            '저장할 파일 내용이 올바르지 않습니다.',
            error_code='invalid_content',
            status_code=400,
        )

    current_state = read_file(
        root_key=normalized_root,
        relative_path=normalized_path,
    )
    if not current_state.get('editable'):
        raise FileBrowserError(
            '이 파일 형식은 편집 저장을 지원하지 않습니다.',
            error_code='not_editable',
            status_code=400,
        )

    normalized_expected_modified_ns = _normalize_expected_modified_ns(expected_modified_ns)
    current_modified_ns = str(current_state.get('modified_ns') or '').strip()
    if normalized_expected_modified_ns and normalized_expected_modified_ns != current_modified_ns:
        raise FileBrowserError(
            '파일이 다른 변경으로 업데이트되었습니다. 다시 열어 최신 내용을 확인해주세요.',
            error_code='modified_conflict',
            status_code=409,
        )

    encoded = content.encode('utf-8')
    if len(encoded) > _MAX_FILE_EDIT_BYTES:
        raise FileBrowserError(
            '편집 저장 크기 제한(512KB)을 초과했습니다.',
            error_code='file_too_large',
            status_code=413,
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
            '파일만 저장할 수 있습니다.',
            error_code='not_file',
            status_code=400,
        )
    try:
        target_mode = int(target_path.stat().st_mode) & 0o7777
    except OSError:
        target_mode = None

    temp_handle = None
    temp_path = None
    try:
        temp_handle = tempfile.NamedTemporaryFile(
            mode='wb',
            delete=False,
            dir=target_path.parent,
            prefix=f'.{target_path.name}.codex-save-',
        )
        temp_path = Path(temp_handle.name)
        temp_handle.write(encoded)
        temp_handle.flush()
        temp_handle.close()
        temp_handle = None
        if target_mode is not None:
            temp_path.chmod(target_mode)
        temp_path.replace(target_path)
    except OSError as exc:
        raise FileBrowserError(
            f'파일을 저장하지 못했습니다: {exc}',
            error_code='write_error',
            status_code=500,
        ) from exc
    finally:
        if temp_handle is not None:
            try:
                temp_handle.close()
            except OSError:
                pass
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    saved_state = read_file(
        root_key=normalized_root,
        relative_path=normalized_path,
    )
    saved_state['saved'] = True
    return saved_state


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


def build_download_payload(root_key=None, relative_paths=None):
    normalized_root, root_path, targets = _resolve_file_targets(root_key, relative_paths)

    total_bytes = sum(max(0, int(item.get('size') or 0)) for item in targets)
    if len(targets) == 1 and total_bytes > _MAX_FILE_DOWNLOAD_BYTES:
        raise FileBrowserError(
            '단일 파일 다운로드 크기 제한(64MB)을 초과했습니다.',
            error_code='file_too_large',
            status_code=413,
        )
    if len(targets) > 1 and total_bytes > _MAX_MULTI_DOWNLOAD_TOTAL_BYTES:
        raise FileBrowserError(
            '선택한 파일의 전체 다운로드 크기 제한(128MB)을 초과했습니다.',
            error_code='file_too_large',
            status_code=413,
        )

    if len(targets) == 1:
        target = targets[0]
        try:
            content = target['target_path'].read_bytes()
        except OSError as exc:
            raise FileBrowserError(
                f'파일을 읽을 수 없습니다: {exc}',
                error_code='read_error',
                status_code=500,
            ) from exc
        mime_type = mimetypes.guess_type(target['name'])[0] or 'application/octet-stream'
        return {
            'root': normalized_root,
            'root_path': str(root_path),
            'paths': [target['relative_path']],
            'count': 1,
            'mime_type': mime_type,
            'download_name': target['name'],
            'content': content,
            'is_archive': False,
        }

    buffer = io.BytesIO()
    try:
        with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as archive:
            for target in targets:
                archive.write(target['target_path'], arcname=target['relative_path'])
    except OSError as exc:
        raise FileBrowserError(
            f'압축 파일을 만들지 못했습니다: {exc}',
            error_code='download_error',
            status_code=500,
        ) from exc

    return {
        'root': normalized_root,
        'root_path': str(root_path),
        'paths': [item['relative_path'] for item in targets],
        'count': len(targets),
        'mime_type': 'application/zip',
        'download_name': _build_download_archive_name(),
        'content': buffer.getvalue(),
        'is_archive': True,
    }


def delete_files(root_key=None, relative_paths=None):
    normalized_root, root_path, targets = _resolve_file_targets(root_key, relative_paths)
    quarantine_directory = Path(tempfile.mkdtemp(prefix=_DELETE_QUARANTINE_PREFIX, dir=root_path))
    moved_targets = []

    try:
        for target in targets:
            quarantine_target = quarantine_directory / target['relative_path']
            quarantine_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target['target_path']), str(quarantine_target))
            moved_targets.append((target['target_path'], quarantine_target))
        shutil.rmtree(quarantine_directory)
    except Exception as exc:  # noqa: BLE001
        rollback_errors = []
        for source_path, quarantine_target in reversed(moved_targets):
            try:
                if quarantine_target.exists() and not source_path.exists():
                    source_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(quarantine_target), str(source_path))
            except Exception as rollback_exc:  # noqa: BLE001
                rollback_errors.append(str(rollback_exc))
        if quarantine_directory.exists():
            shutil.rmtree(quarantine_directory, ignore_errors=True)
        message = f'파일을 삭제하지 못했습니다: {exc}'
        if rollback_errors:
            message = f'{message} (일부 롤백 실패)'
        raise FileBrowserError(
            message,
            error_code='delete_error',
            status_code=500,
        ) from exc

    return {
        'root': normalized_root,
        'root_path': str(root_path),
        'deleted_paths': [item['relative_path'] for item in targets],
        'count': len(targets),
    }


def move_files(root_key=None, relative_paths=None, *, destination_path=None, destination_directory=None):
    normalized_root, root_path, targets = _resolve_file_targets(root_key, relative_paths)
    operations = _build_move_operations(
        root_path,
        targets,
        destination_path=destination_path,
        destination_directory=destination_directory,
    )

    completed_moves = []
    try:
        for operation in operations:
            destination_parent = operation['destination_path'].parent
            destination_parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(operation['source_path']), str(operation['destination_path']))
            completed_moves.append(operation)
    except Exception as exc:  # noqa: BLE001
        for operation in reversed(completed_moves):
            try:
                if operation['destination_path'].exists() and not operation['source_path'].exists():
                    operation['source_path'].parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(operation['destination_path']), str(operation['source_path']))
            except Exception:
                continue
        raise FileBrowserError(
            f'파일을 이동하지 못했습니다: {exc}',
            error_code='move_error',
            status_code=500,
        ) from exc

    return {
        'root': normalized_root,
        'root_path': str(root_path),
        'count': len(operations),
        'moved': [
            {
                'source_path': operation['source_relative_path'],
                'destination_path': operation['destination_relative_path'],
            }
            for operation in operations
        ],
    }
