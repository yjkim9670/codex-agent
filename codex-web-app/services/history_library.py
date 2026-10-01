"""Read-only federation of Workbench histories; SQLite execution state stays local."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile


class HistoryLibraryError(ValueError):
    pass


def library_path():
    from ..config import CODEX_SHARED_ACCOUNT_STATE_DIR
    override = os.environ.get('CODEX_WORKBENCH_HISTORY_LIBRARY')
    return Path(override).expanduser() if override else CODEX_SHARED_ACCOUNT_STATE_DIR / 'history' / 'library.json'


def read_object(path):
    try:
        payload = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise HistoryLibraryError(f'{path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise HistoryLibraryError(f'{path}: expected a JSON object')
    return payload


def read_sessions(path):
    payload = read_object(path)
    sessions = payload.get('sessions')
    if not isinstance(sessions, list):
        raise HistoryLibraryError(f'{path}: sessions must be a list')
    for session in sessions:
        if not isinstance(session, dict) or not isinstance(session.get('id'), str) or not session['id'].strip():
            raise HistoryLibraryError(f'{path}: each session needs an ID')
        if not isinstance(session.get('messages', []), list) or any(not isinstance(m, dict) for m in session.get('messages', [])):
            raise HistoryLibraryError(f'{path}: invalid messages')
    return sessions


def source_id(workspace):
    return hashlib.sha256(str(Path(workspace).resolve()).encode()).hexdigest()[:20]


def merge_sessions(groups):
    # Use Workbench's existing ID/message/timestamp merge rules, rather than
    # dropping older copies that may contain messages absent from a newer copy.
    from .codex_chat import _merge_session_store_payloads
    return _merge_session_store_payloads([{'sessions': sessions} for sessions in groups])['sessions']


def collect_source(workbench, workspace=None):
    root = Path(workbench).expanduser().resolve()
    project = Path(workspace).expanduser().resolve() if workspace else root.parent
    candidates = [root / 'workspace/.agent_state/codex_chat_sessions.json',
                  root / '.agent_state/codex_chat_sessions.json',
                  project / '.agent_state/codex_chat_sessions.json',
                  project / 'codex_chat_sessions.json']
    stores = list(dict.fromkeys(str(path) for path in candidates if path.is_file()))
    if not stores:
        raise HistoryLibraryError(f'{root}: no history stores found; use --store for a custom layout')
    return build_source(project, stores, root.name)


def build_source(workspace, stores, label=None):
    project = str(Path(workspace).expanduser().resolve())
    stores = list(dict.fromkeys(str(Path(p).expanduser().resolve()) for p in stores))
    sessions = merge_sessions([read_sessions(path) for path in stores])
    return source_id(project), {'label': label or Path(project).name, 'workspace_path': project,
                               'store_paths': stores, 'sessions': sessions,
                               'imported_at': datetime.now(timezone.utc).isoformat()}


def load_library(path=None):
    path = Path(path) if path is not None else library_path()
    if not path.exists():
        return {'version': 1, 'sources': {}}
    payload = read_object(path)
    if payload.get('version') != 1 or not isinstance(payload.get('sources'), dict):
        raise HistoryLibraryError(f'{path}: unsupported history library')
    for key, source in payload['sources'].items():
        if (not isinstance(source, dict) or not isinstance(source.get('workspace_path'), str)
                or not isinstance(source.get('store_paths'), list)
                or not all(isinstance(p, str) for p in source['store_paths'])
                or not isinstance(source.get('sessions'), list)
                or key != source_id(source['workspace_path'])):
            raise HistoryLibraryError(f'{path}: invalid source record')
    return payload


def import_sources(sources, path=None, apply=False):
    """Dry-run by default; lock, back up and atomically replace only the library."""
    import fcntl
    path = Path(path) if path is not None else library_path()
    sources = list(sources)
    if any(path.resolve() == Path(store).resolve()
           for _, source in sources for store in source['store_paths']):
        raise HistoryLibraryError('The library cannot overwrite an original history store')
    if not apply:
        return _merge_sources(load_library(path), sources)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.with_name(f'.{path.name}.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        payload = _merge_sources(load_library(path), sources)
        if path.exists():
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
            backup = path.with_name(f'{path.name}.backup-{stamp}')
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(path.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
        fd, tmp = tempfile.mkstemp(prefix='.history-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return payload


def _merge_sources(payload, sources):
    payload = deepcopy(payload)
    for key, incoming in sources:
        old = payload['sources'].get(key)
        if old:
            incoming = deepcopy(incoming)
            incoming['sessions'] = merge_sessions([old['sessions'], incoming['sessions']])
            incoming['store_paths'] = list(dict.fromkeys(old['store_paths'] + incoming['store_paths']))
        payload['sources'][key] = incoming
    return payload


def get_sources():
    sources = load_library()['sources']
    # The current workspace remains available before the first import.
    from ..config import WORKSPACE_DIR, CODEX_CHAT_STORE_PATH
    key = source_id(WORKSPACE_DIR)
    if key not in sources:
        sources[key] = {'label': Path(WORKSPACE_DIR).name, 'workspace_path': str(WORKSPACE_DIR),
                        'store_paths': [str(CODEX_CHAT_STORE_PATH)], 'sessions': [], 'imported_at': None}
    return sources


def source_sessions(source):
    groups = []
    warnings = []
    for path in source['store_paths']:
        try:
            groups.append(read_sessions(path))
        except HistoryLibraryError:
            warnings.append('원본 기록을 읽을 수 없어 가져온 사본을 표시합니다.')
    # Live histories are authoritative, including intentional deletions. Use
    # the archive only when any original is unavailable, and disclose this.
    if warnings:
        groups.insert(0, source['sessions'])
    return merge_sessions(groups), list(dict.fromkeys(warnings))


def list_history(project=None):
    sources = get_sources()
    if project and project not in sources:
        raise KeyError(project)
    projects, sessions, warnings = [], [], []
    for key, source in sources.items():
        projects.append({'id': key, 'label': source['label'], 'workspace_path': source['workspace_path'],
                         'imported_at': source.get('imported_at')})
        if project and key != project:
            continue
        records, notices = source_sessions(source)
        warnings.extend(f"{source['workspace_path']}: {notice}" for notice in notices)
        for record in records:
            if record.get('internal'):
                continue
            sessions.append({'id': record['id'], 'project_id': key, 'project': source['workspace_path'],
                             'title': record.get('title') or 'New session',
                             'updated_at': record.get('updated_at') or record.get('created_at') or '',
                             'message_count': len(record.get('messages', []))})
    sessions.sort(key=lambda s: s['updated_at'], reverse=True)
    return {'projects': projects, 'sessions': sessions, 'warnings': warnings}


def get_history_session(project, session_id):
    source = get_sources().get(project)
    if source is None:
        raise KeyError(project)
    sessions, warnings = source_sessions(source)
    record = next((s for s in sessions if s['id'] == session_id and not s.get('internal')), None)
    if record is None:
        raise KeyError(session_id)
    return {'session': record, 'workspace_path': source['workspace_path'], 'warnings': warnings}
