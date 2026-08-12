"""Secure company API credential storage and resolution."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hmac
import os
from pathlib import Path
import sys
import threading
from datetime import datetime, timezone
import urllib.error
import urllib.request
import uuid

from ..config import CODEX_INTERNAL_DATA_DIR, CODEX_INTERNAL_USER_MAP_PATH, CODEX_STORAGE_DIR, is_internal_multiuser_mode
from .multiuser import get_active_user, load_ip_user_map, storage_key_for_ip


class CompanyCredentialError(RuntimeError):
    def __init__(self, message, *, error_code='company_credential_error', status_code=400):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


_lock = threading.RLock()
# Kept for standalone backward compatibility (including existing deployments
# which set this module attribute directly).  Internal mode never reads it.
_session_api_key = ''
_session_api_keys = {}
_DPAPI_ENTROPY = b'CodexWorkbench.CompanyApiKey.v1'
_MAX_API_KEY_CHARS = 8192
_MAX_INTERNAL_KEYS = 64


def _internal_pool_path() -> Path:
    """The administrator-owned, DPAPI-protected internal key pool."""
    return Path(CODEX_INTERNAL_DATA_DIR) / 'organization' / 'credentials' / 'api_key_pool.dpapi'


def _internal_selection_audit_path() -> Path:
    return _internal_pool_path().with_name('api_key_selection_audit.jsonl')


def _read_internal_pool() -> dict:
    path = _internal_pool_path()
    if not path.is_file():
        return {'version': 2, 'keys': [], 'next_key_index': 0, 'stats': {}}
    try:
        decoded = _unprotect_windows(path.read_bytes()).decode('utf-8')
        payload = __import__('json').loads(decoded)
    except CompanyCredentialError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise CompanyCredentialError('내부 API Key 풀을 읽지 못했습니다.', error_code='internal_credential_read_failed', status_code=500) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get('keys'), list):
        raise CompanyCredentialError('내부 API Key 풀 형식이 올바르지 않습니다.', error_code='internal_credential_invalid', status_code=500)
    # Version 1 stored user-to-key assignments.  Keep it readable so existing
    # installations upgrade without manual credential migration.
    payload.setdefault('version', 1)
    payload.setdefault('next_key_index', 0)
    payload.setdefault('stats', {})
    if not isinstance(payload['stats'], dict):
        payload['stats'] = {}
    try:
        payload['next_key_index'] = max(0, int(payload['next_key_index']))
    except (TypeError, ValueError):
        payload['next_key_index'] = 0
    return payload


def _write_internal_pool(payload: dict) -> None:
    if sys.platform != 'win32':
        raise CompanyCredentialError('내부 API Key 풀은 Windows DPAPI 환경에서만 저장할 수 있습니다.', error_code='dpapi_unavailable')
    try:
        serialized = __import__('json').dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        protected = _protect_windows(serialized)
        path = _internal_pool_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_bytes(protected)
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(path)
    except CompanyCredentialError:
        raise
    except OSError as exc:
        raise CompanyCredentialError('내부 API Key 풀을 저장하지 못했습니다.', error_code='internal_credential_write_failed', status_code=500) from exc


def get_internal_api_key_allocation() -> dict:
    """Return administrator-safe pool metadata; secrets never leave the server."""
    with _lock:
        pool = _read_internal_pool()
        stats = pool['stats']
        keys = [
            {'id': item.get('id'), 'label': item.get('label'),
             'selection_count': int((stats.get(str(item.get('id'))) or {}).get('selection_count') or 0),
             'last_selected_at': str((stats.get(str(item.get('id'))) or {}).get('last_selected_at') or '')}
            for item in pool['keys'] if isinstance(item, dict)
        ]
        return {
            'keys': keys,
            'allocation_mode': 'round_robin_per_request',
            'persistent_supported': sys.platform == 'win32',
        }


def update_internal_api_key_allocation(payload: object) -> dict:
    """Replace pool metadata and assignments while retaining omitted secret values."""
    if not isinstance(payload, dict):
        raise CompanyCredentialError('내부 API Key 배정 요청 형식이 올바르지 않습니다.', error_code='internal_credential_invalid')
    raw_keys = payload.get('keys')
    if not isinstance(raw_keys, list) or len(raw_keys) > _MAX_INTERNAL_KEYS:
        raise CompanyCredentialError('API Key 목록 정보가 올바르지 않습니다.', error_code='internal_credential_invalid')
    with _lock:
        previous_pool = _read_internal_pool()
        existing = {item.get('id'): item for item in previous_pool['keys'] if isinstance(item, dict)}
        keys, seen = [], set()
        for item in raw_keys:
            if not isinstance(item, dict):
                raise CompanyCredentialError('API Key 항목 형식이 올바르지 않습니다.', error_code='internal_credential_invalid')
            key_id = str(item.get('id') or '').strip() or uuid.uuid4().hex
            label = str(item.get('label') or '').strip()
            supplied_secret = str(item.get('api_key') or '').strip()
            if not label or len(label) > 100 or key_id in seen:
                raise CompanyCredentialError('API Key 이름 또는 식별자가 올바르지 않습니다.', error_code='internal_credential_invalid')
            secret = supplied_secret or str(existing.get(key_id, {}).get('secret') or '')
            if not secret or len(secret) > _MAX_API_KEY_CHARS:
                raise CompanyCredentialError('각 API Key의 실제 값을 입력하세요.', error_code='api_key_required')
            keys.append({'id': key_id, 'label': label, 'secret': secret})
            seen.add(key_id)
        old_stats = previous_pool.get('stats') if isinstance(previous_pool.get('stats'), dict) else {}
        stats = {key_id: old_stats[key_id] for key_id in seen if isinstance(old_stats.get(key_id), dict)}
        next_key_index = int(previous_pool.get('next_key_index') or 0)
        _write_internal_pool({
            'version': 2, 'keys': keys, 'next_key_index': next_key_index % len(keys) if keys else 0,
            'stats': stats,
        })
        return get_internal_api_key_allocation()


def _acquire_internal_api_key() -> tuple[str, str, str]:
    """Atomically reserve the next pooled key for one child execution."""
    with _lock:
        pool = _read_internal_pool()
        keys = [item for item in pool['keys'] if isinstance(item, dict) and str(item.get('secret') or '').strip()]
        if not keys:
            return '', 'internal_pool_empty', ''
        index = int(pool.get('next_key_index') or 0) % len(keys)
        selected = keys[index]
        key_id = str(selected.get('id') or '')
        stats = pool.get('stats') if isinstance(pool.get('stats'), dict) else {}
        entry = stats.get(key_id) if isinstance(stats.get(key_id), dict) else {}
        entry['selection_count'] = max(0, int(entry.get('selection_count') or 0)) + 1
        entry['last_selected_at'] = datetime.now(timezone.utc).isoformat()
        stats[key_id] = entry
        pool.update({'version': 2, 'next_key_index': (index + 1) % len(keys), 'stats': stats})
        # Legacy assignments are deliberately discarded on the first request.
        pool.pop('assignments', None)
        _write_internal_pool(pool)
        # The audit contains opaque user/key IDs only; it never contains an IP
        # address or credential.  Detailed token usage is attached by the chat
        # service using the same key ID when the request completes.
        audit = {
            'event_id': uuid.uuid4().hex,
            'selected_at': entry['last_selected_at'],
            'key_id': key_id,
            'user_storage_key': getattr(get_active_user(), 'storage_key', ''),
            'allocation_mode': 'round_robin_per_request',
        }
        try:
            path = _internal_selection_audit_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as handle:
                handle.write(__import__('json').dumps(audit, ensure_ascii=False, separators=(',', ':')) + '\n')
        except OSError:
            # A credential must remain usable when a non-secret audit file
            # cannot be appended (for example, a transient disk error).
            pass
        return str(selected['secret']).strip(), 'internal_round_robin', key_id


def _credential_path() -> Path:
    if is_internal_multiuser_mode() and get_active_user() is not None:
        # Per-user credentials stay below the same private state root as chat
        # history.  The filename is intentionally not shared with standalone.
        return Path(CODEX_STORAGE_DIR) / 'credentials' / 'company_api_key.dpapi'
    override = str(os.environ.get('CODEX_COMPANY_CREDENTIAL_PATH') or '').strip()
    if override:
        return Path(override).expanduser()
    local_app_data = str(os.environ.get('LOCALAPPDATA') or '').strip()
    if not local_app_data:
        local_app_data = str(Path.home() / 'AppData' / 'Local')
    return Path(local_app_data) / 'CodexWorkbench' / 'credentials' / 'company_api_key.dpapi'


def _environment_api_key() -> str:
    for name in ('DTGPT_API_KEY', 'CODEX_CLAUDE_AUTH_TOKEN', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY'):
        value = str(os.environ.get(name) or '').strip()
        if value:
            return value
    return ''


class _DataBlob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _blob(value: bytes):
    buffer = ctypes.create_string_buffer(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _protect_windows(value: bytes) -> bytes:
    if sys.platform != 'win32':
        raise CompanyCredentialError(
            '영구 저장은 Windows DPAPI 환경에서만 지원됩니다.',
            error_code='dpapi_unavailable',
        )
    input_blob, input_buffer = _blob(value)
    entropy_blob, entropy_buffer = _blob(_DPAPI_ENTROPY)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(input_blob), 'Codex Workbench company API key',
        ctypes.byref(entropy_blob), None, None, 0, ctypes.byref(output_blob),
    )
    del input_buffer, entropy_buffer
    if not ok:
        raise CompanyCredentialError(
            'Windows DPAPI로 API Key를 보호하지 못했습니다.',
            error_code='dpapi_protect_failed', status_code=500,
        )
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _unprotect_windows(value: bytes) -> bytes:
    if sys.platform != 'win32':
        raise CompanyCredentialError(
            '저장된 Windows DPAPI 자격 증명은 Windows에서만 읽을 수 있습니다.',
            error_code='dpapi_unavailable',
        )
    input_blob, input_buffer = _blob(value)
    entropy_blob, entropy_buffer = _blob(_DPAPI_ENTROPY)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob), None, ctypes.byref(entropy_blob),
        None, None, 0, ctypes.byref(output_blob),
    )
    del input_buffer, entropy_buffer
    if not ok:
        raise CompanyCredentialError(
            '저장된 API Key를 현재 Windows 계정으로 해독하지 못했습니다.',
            error_code='dpapi_unprotect_failed', status_code=500,
        )
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _read_persistent_key() -> str:
    path = _credential_path()
    if not path.is_file():
        return ''
    try:
        return _unprotect_windows(path.read_bytes()).decode('utf-8').strip()
    except CompanyCredentialError:
        raise
    except (OSError, UnicodeError) as exc:
        raise CompanyCredentialError(
            '저장된 API Key를 읽지 못했습니다.',
            error_code='credential_read_failed', status_code=500,
        ) from exc


def resolve_company_api_key() -> tuple[str, str]:
    """Return ``(secret, source)`` using session > DPAPI > environment priority."""
    with _lock:
        # In the internal deployment no user-supplied or server environment
        # key can bypass the administrator-managed pool.  Merely checking the
        # status must not consume a round-robin slot.
        if is_internal_multiuser_mode() and get_active_user() is not None:
            pool = _read_internal_pool()
            for item in pool['keys']:
                if isinstance(item, dict):
                    secret = str(item.get('secret') or '').strip()
                    if secret:
                        return secret, 'internal_pool'
            return '', 'internal_pool_empty'
        session_key = _credential_session_key()
        if session_key == 'standalone' and _session_api_key:
            return _session_api_key, 'session'
        if _session_api_keys.get(session_key):
            return _session_api_keys[session_key], 'session'
        if _credential_path().is_file():
            return _read_persistent_key(), 'windows_dpapi'
        environment_value = _environment_api_key()
        if environment_value:
            return environment_value, 'environment'
        return '', 'none'


def get_company_credential_status() -> dict:
    try:
        value, source = resolve_company_api_key()
        error = None
    except CompanyCredentialError as exc:
        value, source, error = '', 'windows_dpapi', exc.error_code
    return {
        'configured': bool(value),
        'source': source,
        'persistent': source == 'windows_dpapi',
        'persistent_supported': sys.platform == 'win32',
        'error': error,
    }


def store_company_api_key(api_key, *, persistent=False) -> dict:
    value = str(api_key or '').strip()
    if not value:
        raise CompanyCredentialError('API Key를 입력하세요.', error_code='api_key_required')
    if len(value) > _MAX_API_KEY_CHARS:
        raise CompanyCredentialError('API Key가 너무 깁니다.', error_code='api_key_too_long')
    global _session_api_key
    with _lock:
        session_key = _credential_session_key()
        if persistent:
            protected = _protect_windows(value.encode('utf-8'))
            path = _credential_path()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(path.suffix + '.tmp')
                temporary.write_bytes(protected)
                try:
                    temporary.chmod(0o600)
                except OSError:
                    pass
                temporary.replace(path)
            except OSError as exc:
                raise CompanyCredentialError(
                    '암호화된 API Key 파일을 저장하지 못했습니다.',
                    error_code='credential_write_failed', status_code=500,
                ) from exc
            _session_api_keys.pop(session_key, None)
            if session_key == 'standalone':
                _session_api_key = ''
        else:
            _session_api_keys[session_key] = value
            if session_key == 'standalone':
                _session_api_key = value
        return get_company_credential_status()


def delete_company_api_key() -> dict:
    global _session_api_key
    with _lock:
        _session_api_keys.pop(_credential_session_key(), None)
        if _credential_session_key() == 'standalone':
            _session_api_key = ''
        path = _credential_path()
        try:
            if path.is_file():
                path.unlink()
        except OSError as exc:
            raise CompanyCredentialError(
                '저장된 API Key를 삭제하지 못했습니다.',
                error_code='credential_delete_failed', status_code=500,
            ) from exc
        return get_company_credential_status()


def _credential_session_key() -> str:
    user = get_active_user()
    return f'user:{user.storage_key}' if user is not None else 'standalone'


def apply_company_api_key(env: dict) -> bool:
    try:
        if is_internal_multiuser_mode() and get_active_user() is not None:
            value, _source, key_id = _acquire_internal_api_key()
            if key_id:
                # This opaque ID is safe to include in execution diagnostics;
                # the actual credential is never exposed by an API response.
                env['CODEX_WORKBENCH_INTERNAL_API_KEY_ID'] = key_id
        else:
            value, _source = resolve_company_api_key()
    except CompanyCredentialError:
        return False
    if not value:
        return False
    env['DTGPT_API_KEY'] = value
    return True


def _configured_admin_secret() -> str:
    return str(
        os.environ.get('CODEX_COMPANY_ADMIN_PASSWORD')
        or os.environ.get('CODEX_COMPANY_ADMIN_TOKEN')
        or ''
    ).strip()


def verify_admin_secret(candidate) -> bool:
    expected = _configured_admin_secret()
    provided = str(candidate or '')
    return bool(expected) and hmac.compare_digest(provided.encode('utf-8'), expected.encode('utf-8'))


def is_admin_auth_configured() -> bool:
    return bool(_configured_admin_secret())


def test_company_api_key(timeout_seconds=10) -> dict:
    api_key, source = resolve_company_api_key()
    if not api_key:
        raise CompanyCredentialError('테스트할 API Key가 없습니다.', error_code='api_key_not_configured')
    health_url = str(os.environ.get('CODEX_DTGPT_HEALTH_URL') or '').strip()
    if not health_url:
        raise CompanyCredentialError('회사 /health 주소가 설정되지 않았습니다.', error_code='health_url_missing')
    health_request = urllib.request.Request(
        health_url,
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'X-API-Key': api_key,
            'User-Agent': 'CodexWorkbench/credential-test',
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(health_request, timeout=max(2, int(timeout_seconds))) as response:
            status_code = int(getattr(response, 'status', 200) or 200)
    except urllib.error.HTTPError as exc:
        raise CompanyCredentialError(
            f'회사 API 연결 테스트가 HTTP {exc.code}로 실패했습니다.',
            error_code='credential_test_http_error',
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CompanyCredentialError(
            '회사 API /health 엔드포인트에 연결하지 못했습니다.',
            error_code='credential_test_connection_failed',
        ) from exc
    return {'ok': 200 <= status_code < 300, 'status_code': status_code, 'source': source}
