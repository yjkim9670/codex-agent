"""Versioned, read-only RTL knowledge snapshots for internal deployments."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import uuid

from ..config import CODEX_SHARED_KNOWLEDGE_DIR, WORKSPACE_DIR
from .multiuser import get_active_user

_ALLOWED_SUFFIXES = {'.v', '.vh', '.sv', '.svh', '.vhd', '.vhdl', '.md', '.markdown'}
_MAX_FILE_BYTES = 16 * 1024 * 1024
_MAX_FILES = 1000
_REVISION_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{0,63}$')
_MODULE_RE = re.compile(r'^\s*module\s+([a-zA-Z_][\w$]*)', re.MULTILINE)
_HEADING_RE = re.compile(r'^#{1,6}\s+(.+?)\s*$', re.MULTILINE)


class SharedKnowledgeError(RuntimeError):
    def __init__(self, message, status_code=400, error_code='shared_knowledge_error'):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def _root() -> Path:
    return Path(CODEX_SHARED_KNOWLEDGE_DIR) / 'revisions'


def _validate_revision_id(value: object) -> str:
    revision_id = str(value or '').strip().lower()
    if not _REVISION_RE.fullmatch(revision_id):
        raise SharedKnowledgeError('revision_id는 영문 소문자, 숫자, ., _, - 로 된 1-64자여야 합니다.', error_code='invalid_revision_id')
    return revision_id


def _safe_relative_path(value: object) -> PurePosixPath:
    path = PurePosixPath(str(value or '').replace('\\', '/'))
    if not path.parts or path.is_absolute() or '..' in path.parts or path.name in {'', '.', '..'}:
        raise SharedKnowledgeError('안전하지 않은 파일 경로입니다.', error_code='invalid_knowledge_path')
    if path.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise SharedKnowledgeError('RTL 또는 Markdown 파일만 등록할 수 있습니다.', error_code='unsupported_knowledge_file')
    return path


def _read_manifest(revision_id: str) -> dict:
    manifest_path = _root() / revision_id / 'manifest.json'
    try:
        return json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise SharedKnowledgeError('지식 revision을 찾을 수 없습니다.', 404, 'knowledge_revision_not_found')


def _audit(action: str, revision_id: str, **details) -> None:
    user = get_active_user()
    record = {
        'at': datetime.now(timezone.utc).isoformat(), 'action': action,
        'revision_id': revision_id, 'username': user.username if user else None,
        'client_ip': user.client_ip if user else None, **details,
    }
    path = Path(CODEX_SHARED_KNOWLEDGE_DIR).parent / 'audit-log.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')


def list_revisions() -> list[dict]:
    root = _root()
    if not root.exists():
        return []
    revisions = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            manifest = _read_manifest(child.name)
        except SharedKnowledgeError:
            continue
        revisions.append({key: manifest.get(key) for key in ('revision_id', 'title', 'description', 'created_at', 'created_by', 'file_count', 'module_count')})
    return sorted(revisions, key=lambda item: item.get('created_at') or '', reverse=True)


def get_revision(revision_id: object) -> dict:
    revision_id = _validate_revision_id(revision_id)
    manifest = _read_manifest(revision_id)
    try:
        index = json.loads((_root() / revision_id / 'index.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        index = {'modules': [], 'documents': []}
    return {'manifest': manifest, 'index': index}


def create_revision(revision_id: object, title: object, description: object, file_storages) -> dict:
    revision_id = _validate_revision_id(revision_id)
    files = list(file_storages or [])
    if not files or len(files) > _MAX_FILES:
        raise SharedKnowledgeError('1개 이상, 최대 1000개의 파일을 등록할 수 있습니다.', error_code='invalid_knowledge_files')
    root = _root(); target = root / revision_id
    if target.exists():
        raise SharedKnowledgeError('같은 revision_id가 이미 있습니다.', 409, 'knowledge_revision_exists')
    temporary = root / f'.creating-{revision_id}-{uuid.uuid4().hex}'
    source_root = temporary / 'source'
    modules, documents, entries = [], [], []
    try:
        source_root.mkdir(parents=True)
        seen = set()
        for storage in files:
            relative = _safe_relative_path(getattr(storage, 'filename', ''))
            if str(relative) in seen:
                raise SharedKnowledgeError('중복된 파일 경로가 있습니다.', error_code='duplicate_knowledge_path')
            seen.add(str(relative))
            content = storage.read(_MAX_FILE_BYTES + 1)
            if len(content) > _MAX_FILE_BYTES:
                raise SharedKnowledgeError(f'{relative} 파일이 16MB를 초과합니다.', error_code='knowledge_file_too_large')
            destination = source_root.joinpath(*relative.parts); destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            entries.append({'path': str(relative), 'bytes': len(content), 'sha256': digest})
            text = content.decode('utf-8', errors='replace')
            if relative.suffix.lower() in {'.v', '.vh', '.sv', '.svh', '.vhd', '.vhdl'}:
                modules.extend({'name': name, 'path': str(relative)} for name in _MODULE_RE.findall(text))
            else:
                documents.append({'path': str(relative), 'headings': _HEADING_RE.findall(text)[:40]})
        user = get_active_user()
        manifest = {'version': 1, 'revision_id': revision_id, 'title': str(title or revision_id).strip()[:200] or revision_id,
                    'description': str(description or '').strip()[:2000], 'created_at': datetime.now(timezone.utc).isoformat(),
                    'created_by': user.username if user else None, 'file_count': len(entries), 'module_count': len(modules), 'files': entries}
        (temporary / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (temporary / 'index.json').write_text(json.dumps({'modules': modules, 'documents': documents}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        root.mkdir(parents=True, exist_ok=True); os.replace(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _audit('shared_knowledge_created', revision_id, file_count=len(entries))
    return get_revision(revision_id)


def import_revision_to_workspace(revision_id: object) -> dict:
    revision_id = _validate_revision_id(revision_id); manifest = _read_manifest(revision_id)
    source = _root() / revision_id / 'source'
    destination = Path(WORKSPACE_DIR) / '.codex-knowledge' / revision_id
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    _audit('shared_knowledge_imported', revision_id, destination=str(destination))
    return {'revision_id': revision_id, 'workspace_path': str(destination.relative_to(Path(WORKSPACE_DIR))), 'file_count': manifest.get('file_count', 0)}


def build_knowledge_prompt_context(revision_id: object) -> tuple[str, dict]:
    revision_id = _validate_revision_id(revision_id); manifest = _read_manifest(revision_id)
    import_revision_to_workspace(revision_id)
    return (f"\n\n[공용 RTL 지식 revision: {revision_id}]\n"
            f"공용 원본의 개인 사본은 workspace/.codex-knowledge/{revision_id}/ 에 있습니다. "
            "분석 시 해당 파일과 manifest/index를 확인하고, 답변에는 파일 경로와 모듈명을 근거로 제시하세요. "
            "이 사본의 수정은 개인 workspace에만 적용되며 공용 revision에는 반영되지 않습니다.\n", manifest)
