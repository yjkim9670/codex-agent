"""Model chat session storage and multi-provider execution helpers."""

import json
import logging
import math
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path, PurePosixPath

from .. import state
from ..config import (
    KST,
    LEGACY_MODEL_CHAT_STORE_PATH,
    LEGACY_MODEL_SETTINGS_PATH,
    LEGACY_MODEL_USAGE_HISTORY_PATH,
    LEGACY_MODEL_USAGE_SNAPSHOT_PATH,
    MODEL_API_TIMEOUT_SECONDS,
    MODEL_CLAUDE_DEFAULT_MODEL,
    MODEL_CHAT_STORE_PATH,
    MODEL_CONTEXT_MAX_CHARS,
    MODEL_DEFAULT_REASONING_EFFORT,
    MODEL_DEFAULT_PROVIDER,
    MODEL_DTGPT_API_BASE_URL,
    MODEL_DTGPT_API_BASE_URLS,
    MODEL_DTGPT_API_KEY,
    MODEL_DTGPT_API_KEY_ENV,
    MODEL_DTGPT_API_KEY_HEADER,
    MODEL_DTGPT_API_KEY_PREFIX,
    MODEL_DTGPT_DEFAULT_MODEL,
    MODEL_EXEC_TIMEOUT_SECONDS,
    MODEL_GEMINI_API_BASE_URL,
    MODEL_GEMINI_API_KEY,
    MODEL_GEMINI_DEFAULT_MODEL,
    MODEL_GEMINI_MODEL_OPTIONS,
    MODEL_PROVIDER_DEFAULT_MODELS,
    MODEL_PROVIDER_MODEL_OPTIONS,
    MODEL_PROVIDER_OPTIONS,
    MODEL_REASONING_OPTIONS,
    MODEL_SETTINGS_PATH,
    MODEL_STREAM_TERMINATE_GRACE_SECONDS,
    MODEL_STREAM_TTL_SECONDS,
    MODEL_USAGE_HISTORY_PATH,
    MODEL_USAGE_SNAPSHOT_PATH,
    MODEL_WORKSPACE_BLOCKED_PATHS,
    REPO_ROOT,
    WORKSPACE_DIR,
)
from ..utils.time import normalize_timestamp, parse_timestamp

_DATA_LOCK = threading.Lock()
_CONFIG_LOCK = threading.Lock()
_USAGE_LOCK = threading.Lock()
_USAGE_HISTORY_LOCK = threading.Lock()
_USAGE_SNAPSHOT_WORKER_LOCK = threading.Lock()
_SESSION_SUBMIT_LOCKS_GUARD = threading.Lock()
_SESSION_SUBMIT_LOCKS = {}
_PATCH_APPLY_LOCK = threading.Lock()
_CLAUDE_CLI_CAPABILITIES_LOCK = threading.Lock()
_CLAUDE_CLI_CAPABILITIES = None
_LOGGER = logging.getLogger(__name__)
_FINALIZE_LAG_WARNING_MS = 5000
_USAGE_HISTORY_VERSION = 1
_USAGE_HISTORY_BUCKET_HOURS = 1
_USAGE_HISTORY_MAX_ITEMS = 24 * 30
_USAGE_SNAPSHOT_POLL_SECONDS = 300
_USAGE_RATE_LIMIT_REFRESH_SECONDS = 60
_USAGE_SNAPSHOT_WORKER_STARTED = False
_PENDING_QUEUE_KEY = 'pending_queue'
_PENDING_QUEUE_BOOTSTRAP_LOCK = threading.Lock()
_PENDING_QUEUE_BOOTSTRAP_STARTED = False
_PLAN_MODE_PROMPT_SUFFIX = (
    "## Plan Mode Guardrails\n"
    "- Plan mode is enabled for this turn.\n"
    "- Do not modify files.\n"
    "- Do not run commands that create, edit, move, or delete files.\n"
    "- Provide analysis and an implementation plan only.\n"
    "- If changes are needed, describe proposed patches without applying them."
)
_PLAN_MODE_TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}
_LAYOUT_ROOT_SERVER = 'server'
_LAYOUT_ROOT_WORKSPACE = 'workspace'
_LAYOUT_ROOT_KEYS = {_LAYOUT_ROOT_SERVER, _LAYOUT_ROOT_WORKSPACE}
_LAYOUT_MAX_PATH_CHARS = 1024
_SUPPORTED_PROVIDERS = ('gemini', 'dtgpt', 'claude')
_OPENAI_COMPATIBLE_PROVIDERS = ('dtgpt',)
_EFFORT_ALIASES = {
    'minimum': 'low',
    'min': 'low',
    'low': 'low',
    'medium': 'medium',
    'med': 'medium',
    'high': 'high',
    'maximum': 'max',
    'max': 'max',
}
_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_ENV_REFERENCE_PATTERN = re.compile(r'^\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}$')
_PATCH_BLOCK_PATTERN = re.compile(r'```(?:diff|patch)\s*\n(.*?)```', re.IGNORECASE | re.DOTALL)
_TOOL_RUN_BLOCK_PATTERN = re.compile(r'```(?:bash|sh|shell)\s*\n(.*?)```', re.IGNORECASE | re.DOTALL)
_HUNK_HEADER_PATTERN = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')
_PATCH_MAX_CHARS = 400_000
_CONTEXT_MESSAGE_ROLE_MAX_CHARS = {
    'assistant': 1400,
    'user': 1400,
    'system': 900,
    'error': 900,
}
_CONTEXT_MESSAGE_DEFAULT_MAX_CHARS = 700
_CONTEXT_MEMORY_ROLE_MAX_CHARS = {
    'user': 260,
    'assistant': 120,
    'system': 160,
    'error': 160,
}
_CONTEXT_MEMORY_DEFAULT_MAX_CHARS = 140
_CONTEXT_AUTO_NOTE_LINE_PATTERN = re.compile(r'^\[(?:Patch Apply|Tool Run)\]\s', re.IGNORECASE)
_TOOL_RUN_MARKERS = ('@run', '#@run', '# @run')
_TOOL_RUN_MAX_COMMANDS = 6
_TOOL_RUN_MAX_OUTPUT_CHARS = 4000
_TOOL_RUN_ALLOWED_EXECUTABLES = {
    'python',
    'python3',
    'bash',
    'sh',
    'ls',
    'cat',
    'pwd',
    'echo',
    'mkdir',
    'rm',
    'test',
    '[',
    'chmod',
    'iverilog',
    'vvp',
    'verilator',
    'vcs',
    'xrun',
    'ncvlog',
    'ncelab',
    'ncsim',
    'vsim',
    'vlog',
    'make',
    'pytest',
    'gcc',
    'g++',
    'cmake',
    'node',
    'npm',
}
_DTGPT_KNOWN_BASE_URLS_LINUX = (
    'http://dtgpt.samsungds.net/llm/v1',
)
_DTGPT_KNOWN_BASE_URLS_WINDOWS = (
    'http://cloud.dtgpt.samsungds.net/llm/v1',
)
_BLOCKED_WORKSPACE_PREFIXES = tuple(
    str(item or '').strip().replace('\\', '/').strip().strip('/')
    for item in MODEL_WORKSPACE_BLOCKED_PATHS
    if str(item or '').strip().replace('\\', '/').strip().strip('/')
)
_BLOCKED_WORKSPACE_PREFIX_PARTS = tuple(
    PurePosixPath(prefix).parts for prefix in _BLOCKED_WORKSPACE_PREFIXES
)

_ROLE_LABELS = {
    'user': 'User',
    'assistant': 'Assistant',
    'system': 'System',
    'error': 'Error',
}

_TOKEN_COUNT_KEYS = (
    'total_tokens',
    'token_count',
    'tokens',
)

_TOKEN_USAGE_KEYS = (
    'token_usage',
    'usage',
    'total_token_usage',
    'last_token_usage',
)

_TOKEN_PART_KEYS = (
    'input_tokens',
    'cached_input_tokens',
    'output_tokens',
    'reasoning_output_tokens',
)


def _is_windows_platform():
    return os.name == 'nt'


def _known_dtgpt_base_urls():
    if _is_windows_platform():
        return _DTGPT_KNOWN_BASE_URLS_WINDOWS
    return _DTGPT_KNOWN_BASE_URLS_LINUX


def _is_dtgpt_cloud_endpoint(url):
    lowered = str(url or '').strip().lower()
    return 'cloud.dtgpt.samsungds.net' in lowered


def _dtgpt_endpoint_rank(url):
    lowered = str(url or '').strip().lower()
    is_cloud = _is_dtgpt_cloud_endpoint(lowered)
    is_direct = '://dtgpt.samsungds.net' in lowered

    if _is_windows_platform():
        if is_cloud:
            return 0
        if is_direct:
            return 1
        return 2

    if is_direct:
        return 0
    if is_cloud:
        return 1
    return 2


def _coerce_non_negative_int(value):
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric < 0:
        return None
    return int(numeric)


def _coerce_non_negative_float(value):
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric < 0:
        return None
    return numeric


def _coerce_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        normalized = value.strip().replace(',', '')
        if normalized.endswith('%'):
            normalized = normalized[:-1].strip()
        value = normalized
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _canonical_provider_name(value):
    raw = str(value or '').strip().lower()
    aliases = {
        'gemini': 'gemini',
        'google': 'gemini',
        'dtgpt': 'dtgpt',
        'dt-gpt': 'dtgpt',
        'dt_gpt': 'dtgpt',
        'dt gpt': 'dtgpt',
        'samsung_dtgpt': 'dtgpt',
        'samsung-dtgpt': 'dtgpt',
        'samsung dtgpt': 'dtgpt',
        'samsungds dtgpt': 'dtgpt',
        'openai': 'dtgpt',
        'gpt': 'dtgpt',
        'kimi': 'dtgpt',
        'moonshot': 'dtgpt',
        'moonshotai': 'dtgpt',
        'glm': 'dtgpt',
        'bigmodel': 'dtgpt',
        'zhipu': 'dtgpt',
        'claude': 'claude',
        'anthropic': 'claude',
        'claude code': 'claude',
        'claude-code': 'claude',
        'claude code cli': 'claude',
        'claude-cli': 'claude',
        'claude cli': 'claude',
    }
    return aliases.get(raw, '')


def _normalize_provider_name(value):
    canonical = _canonical_provider_name(value)
    if canonical in _SUPPORTED_PROVIDERS:
        return canonical
    fallback = _canonical_provider_name(MODEL_DEFAULT_PROVIDER)
    if fallback in _SUPPORTED_PROVIDERS:
        return fallback
    return 'gemini'


def get_provider_options():
    options = []
    for item in MODEL_PROVIDER_OPTIONS:
        provider = _canonical_provider_name(item)
        if not provider:
            continue
        if provider in options:
            continue
        options.append(provider)
    if not options:
        options = list(_SUPPORTED_PROVIDERS)
    default_provider = _normalize_provider_name(MODEL_DEFAULT_PROVIDER)
    if default_provider not in options:
        options.insert(0, default_provider)
    return options


def _default_model_for_provider(provider):
    normalized = _normalize_provider_name(provider)
    configured = MODEL_PROVIDER_DEFAULT_MODELS.get(normalized)
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    if normalized == 'claude':
        return MODEL_CLAUDE_DEFAULT_MODEL
    if normalized == 'dtgpt':
        return MODEL_DTGPT_DEFAULT_MODEL
    return MODEL_GEMINI_DEFAULT_MODEL


def get_model_options(provider=None):
    normalized = _normalize_provider_name(provider)
    configured = MODEL_PROVIDER_MODEL_OPTIONS.get(normalized)
    if not isinstance(configured, list):
        configured = []
    options = []
    for item in configured:
        normalized_model = _normalize_model_name(normalized, item)
        if not normalized_model or normalized_model in options:
            continue
        options.append(normalized_model)
    default_model = _normalize_model_name(normalized, _default_model_for_provider(normalized))
    if default_model not in options:
        options.insert(0, default_model)
    return options


def _normalize_reasoning_effort(value):
    raw = str(value or '').strip().lower()
    if not raw:
        return None
    if raw in {'auto', 'default', 'none', 'off'}:
        return None
    normalized = _EFFORT_ALIASES.get(raw, raw)
    allowed = {'low', 'medium', 'high', 'max'}
    for item in MODEL_REASONING_OPTIONS:
        token = str(item or '').strip().lower()
        if not token or token in {'auto', 'default', 'none', 'off'}:
            continue
        allowed.add(_EFFORT_ALIASES.get(token, token))
    if normalized not in allowed:
        return None
    return normalized


def get_reasoning_options():
    options = []
    for item in MODEL_REASONING_OPTIONS:
        normalized = _normalize_reasoning_effort(item)
        if not normalized or normalized in options:
            continue
        options.append(normalized)
    default_effort = _normalize_reasoning_effort(MODEL_DEFAULT_REASONING_EFFORT)
    if default_effort and default_effort not in options:
        options.insert(0, default_effort)
    if not options:
        options = ['low', 'medium', 'high', 'max']
    return options


def _paths_match(path_a, path_b):
    try:
        return Path(path_a).resolve() == Path(path_b).resolve()
    except Exception:
        return str(path_a) == str(path_b)


def _append_unique_path(paths, candidate):
    if candidate is None:
        return
    try:
        candidate_path = Path(candidate)
    except Exception:
        return
    for existing in paths:
        if _paths_match(existing, candidate_path):
            return
    paths.append(candidate_path)


def _uses_parent_workspace_storage_layout():
    try:
        return WORKSPACE_DIR.resolve() == REPO_ROOT.parent.resolve()
    except Exception:
        return False


def _standard_workspace_storage_dir():
    return WORKSPACE_DIR / REPO_ROOT.name / 'workspace' / '.agent_state'


def _iter_model_state_candidate_paths(primary_path, legacy_path=None):
    primary = Path(primary_path)
    legacy = Path(legacy_path) if legacy_path is not None else None

    candidate_names = [primary.name]
    if legacy is not None and legacy.name != primary.name:
        candidate_names.append(legacy.name)

    candidate_dirs = []
    _append_unique_path(candidate_dirs, primary.parent)
    if legacy is not None:
        _append_unique_path(candidate_dirs, legacy.parent)
    _append_unique_path(candidate_dirs, WORKSPACE_DIR / '.agent_state')
    if _uses_parent_workspace_storage_layout():
        _append_unique_path(candidate_dirs, _standard_workspace_storage_dir())

    candidates = []
    for directory in candidate_dirs:
        for filename in candidate_names:
            _append_unique_path(candidates, Path(directory) / filename)
    _append_unique_path(candidates, primary)
    _append_unique_path(candidates, legacy)
    return candidates


def _read_json_object_from_path(path):
    try:
        raw = Path(path).read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except Exception:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _resolve_existing_path(primary_path, legacy_path):
    primary = Path(primary_path)
    for candidate in _iter_model_state_candidate_paths(primary, legacy_path):
        try:
            exists = candidate.exists()
        except Exception:
            exists = False
        if exists:
            return candidate
    return primary


def _is_blank_merge_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _normalized_time_sort_key(value):
    normalized = normalize_timestamp(value)
    return normalized or ''


def _parse_plan_mode(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _PLAN_MODE_TRUTHY_VALUES
    return False


def _normalize_model_pending_queue_entry(entry):
    if not isinstance(entry, dict):
        return None
    prompt = str(entry.get('prompt') or '').strip()
    if not prompt:
        return None
    return {
        'id': str(entry.get('id') or uuid.uuid4().hex),
        'prompt': prompt,
        'plan_mode': bool(entry.get('plan_mode')),
        'layout_context': entry.get('layout_context') if isinstance(entry.get('layout_context'), dict) else {},
        'created_at': normalize_timestamp(entry.get('created_at')),
    }


def _normalize_session_pending_queue(session):
    if not isinstance(session, dict):
        return []
    raw_queue = session.get(_PENDING_QUEUE_KEY)
    if not isinstance(raw_queue, list):
        session[_PENDING_QUEUE_KEY] = []
        return session[_PENDING_QUEUE_KEY]
    normalized_queue = []
    for item in raw_queue:
        normalized_item = _normalize_model_pending_queue_entry(item)
        if normalized_item:
            normalized_queue.append(normalized_item)
    session[_PENDING_QUEUE_KEY] = normalized_queue
    return session[_PENDING_QUEUE_KEY]


def _message_merge_score(message):
    if not isinstance(message, dict):
        return (0, 0)
    content = str(message.get('content') or '')
    return (len(content.strip()), len(message))


def _message_identity(message):
    if not isinstance(message, dict):
        return None
    message_id = str(message.get('id') or '').strip()
    if message_id:
        return ('id', message_id)
    role = str(message.get('role') or '').strip().lower() or 'assistant'
    created_at = normalize_timestamp(message.get('created_at'))
    content = str(message.get('content') or '')
    return ('fallback', role, created_at, content)


def _merge_message_records(existing, incoming):
    if not isinstance(existing, dict):
        return deepcopy(incoming) if isinstance(incoming, dict) else None
    if not isinstance(incoming, dict):
        return deepcopy(existing)

    existing_time = _normalized_time_sort_key(existing.get('created_at'))
    incoming_time = _normalized_time_sort_key(incoming.get('created_at'))
    prefer_incoming = (
        incoming_time > existing_time
        or (
            incoming_time == existing_time
            and _message_merge_score(incoming) >= _message_merge_score(existing)
        )
    )
    primary = incoming if prefer_incoming else existing
    secondary = existing if prefer_incoming else incoming
    merged = deepcopy(primary)
    for key, value in secondary.items():
        if key not in merged or _is_blank_merge_value(merged.get(key)):
            merged[key] = deepcopy(value)
    if _is_blank_merge_value(merged.get('content')):
        merged['content'] = str(existing.get('content') or incoming.get('content') or '')
    return merged


def _merge_message_lists(existing_messages, incoming_messages):
    merged = {}
    for source_index, messages in enumerate((existing_messages, incoming_messages)):
        if not isinstance(messages, list):
            continue
        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            identity = _message_identity(message)
            if identity is None:
                identity = ('anon', source_index, message_index)
            current = merged.get(identity)
            merged_record = _merge_message_records(current, message) if current else deepcopy(message)
            merged[identity] = {
                'message': merged_record,
                'sort_key': (
                    _normalized_time_sort_key((merged_record or {}).get('created_at')),
                    source_index,
                    message_index,
                ),
            }
    ordered = sorted(merged.values(), key=lambda item: item.get('sort_key') or ('', 0, 0))
    return [item.get('message') for item in ordered if isinstance(item.get('message'), dict)]


def _pending_queue_entry_identity(entry):
    normalized = _normalize_model_pending_queue_entry(entry)
    if not normalized:
        return None
    entry_id = str(normalized.get('id') or '').strip()
    if entry_id:
        return ('id', entry_id)
    return ('fallback', normalized.get('created_at'), normalized.get('prompt'))


def _merge_pending_queue_entries(existing_queue, incoming_queue):
    merged = {}
    for queue in (existing_queue, incoming_queue):
        if not isinstance(queue, list):
            continue
        for item in queue:
            normalized = _normalize_model_pending_queue_entry(item)
            if not normalized:
                continue
            identity = _pending_queue_entry_identity(normalized)
            if identity is None or identity in merged:
                continue
            merged[identity] = normalized
    items = list(merged.values())
    items.sort(key=lambda item: item.get('created_at') or '')
    return items


def _is_default_session_title(value):
    title = str(value or '').strip()
    return not title or title == 'New session'


def _merge_session_title(primary_title, secondary_title):
    primary = str(primary_title or '').strip()
    secondary = str(secondary_title or '').strip()
    if not _is_default_session_title(primary):
        return primary
    if not _is_default_session_title(secondary):
        return secondary
    return primary or secondary or 'New session'


def _merge_session_records(existing, incoming):
    if not isinstance(existing, dict):
        return deepcopy(incoming) if isinstance(incoming, dict) else None
    if not isinstance(incoming, dict):
        return deepcopy(existing)

    existing_updated = _normalized_time_sort_key(existing.get('updated_at') or existing.get('created_at'))
    incoming_updated = _normalized_time_sort_key(incoming.get('updated_at') or incoming.get('created_at'))
    prefer_incoming = incoming_updated >= existing_updated
    primary = incoming if prefer_incoming else existing
    secondary = existing if prefer_incoming else incoming
    merged = deepcopy(primary)

    for key, value in secondary.items():
        if key in {'messages', _PENDING_QUEUE_KEY, 'created_at', 'updated_at', 'title'}:
            continue
        if key not in merged or _is_blank_merge_value(merged.get(key)):
            merged[key] = deepcopy(value)

    merged['id'] = str(merged.get('id') or secondary.get('id') or '').strip()
    created_candidates = [
        _normalized_time_sort_key(existing.get('created_at')),
        _normalized_time_sort_key(incoming.get('created_at')),
    ]
    created_candidates = [value for value in created_candidates if value]
    updated_candidates = [
        _normalized_time_sort_key(existing.get('updated_at') or existing.get('created_at')),
        _normalized_time_sort_key(incoming.get('updated_at') or incoming.get('created_at')),
    ]
    updated_candidates = [value for value in updated_candidates if value]

    merged['created_at'] = min(created_candidates) if created_candidates else normalize_timestamp(None)
    merged['updated_at'] = max(updated_candidates) if updated_candidates else merged['created_at']
    merged['title'] = _merge_session_title(primary.get('title'), secondary.get('title'))
    merged['messages'] = _merge_message_lists(existing.get('messages', []), incoming.get('messages', []))
    merged[_PENDING_QUEUE_KEY] = _merge_pending_queue_entries(
        existing.get(_PENDING_QUEUE_KEY, []),
        incoming.get(_PENDING_QUEUE_KEY, []),
    )
    return merged


def _load_session_store_payload_from_path(path):
    payload = _read_json_object_from_path(path)
    if not isinstance(payload, dict):
        return {'sessions': []}
    sessions = payload.get('sessions')
    if not isinstance(sessions, list):
        sessions = []
    normalized_sessions = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        session_copy = deepcopy(session)
        messages = session_copy.get('messages')
        if not isinstance(messages, list):
            session_copy['messages'] = []
        _normalize_session_pending_queue(session_copy)
        normalized_sessions.append(session_copy)
    return {'sessions': normalized_sessions}


def _merge_session_store_payloads(payloads):
    merged_by_id = {}
    anonymous_sessions = []
    for payload in payloads:
        sessions = payload.get('sessions', []) if isinstance(payload, dict) else []
        if not isinstance(sessions, list):
            continue
        for session in sessions:
            if not isinstance(session, dict):
                continue
            session_id = str(session.get('id') or '').strip()
            if not session_id:
                anonymous_sessions.append(deepcopy(session))
                continue
            current = merged_by_id.get(session_id)
            merged_by_id[session_id] = (
                _merge_session_records(current, session) if current else deepcopy(session)
            )
    merged_sessions = list(merged_by_id.values()) + anonymous_sessions
    for session in merged_sessions:
        _normalize_session_pending_queue(session)
    return {
        'sessions': _sort_sessions(merged_sessions)
    }


def _load_data():
    payloads = []
    for candidate_path in _iter_model_state_candidate_paths(
            MODEL_CHAT_STORE_PATH,
            LEGACY_MODEL_CHAT_STORE_PATH):
        try:
            exists = candidate_path.exists()
        except Exception:
            exists = False
        if not exists:
            continue
        payloads.append(_load_session_store_payload_from_path(candidate_path))
    if not payloads:
        return {'sessions': []}
    return _merge_session_store_payloads(payloads)


def _save_data(data):
    MODEL_CHAT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=str(MODEL_CHAT_STORE_PATH.parent),
            prefix=f'.{MODEL_CHAT_STORE_PATH.name}.',
            suffix='.tmp',
            delete=False,
        ) as handle:
            handle.write(serialized)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
            temp_path = Path(handle.name)
        os.replace(temp_path, MODEL_CHAT_STORE_PATH)
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _default_settings():
    provider = _normalize_provider_name(MODEL_DEFAULT_PROVIDER)
    reasoning_effort = _normalize_reasoning_effort(MODEL_DEFAULT_REASONING_EFFORT)
    return {
        'provider': provider,
        'model': _default_model_for_provider(provider),
        'reasoning_effort': reasoning_effort,
        'plan_mode_provider': None,
        'plan_mode_model': None,
        'plan_mode_reasoning_effort': None,
    }


def _read_workspace_settings():
    data = {}
    best_mtime = None
    for candidate_path in _iter_model_state_candidate_paths(
            MODEL_SETTINGS_PATH,
            LEGACY_MODEL_SETTINGS_PATH):
        payload = _read_json_object_from_path(candidate_path)
        if not isinstance(payload, dict) or not payload:
            continue
        try:
            mtime = candidate_path.stat().st_mtime
        except Exception:
            mtime = -1
        if best_mtime is None or mtime >= best_mtime:
            data = payload
            best_mtime = mtime
    if not data:
        return _default_settings()

    provider = _normalize_provider_name(data.get('provider'))
    model = str(data.get('model') or '').strip() or _default_model_for_provider(provider)
    reasoning_effort = _normalize_reasoning_effort(
        data.get('reasoning_effort')
        if 'reasoning_effort' in data
        else MODEL_DEFAULT_REASONING_EFFORT
    )
    plan_mode_provider_raw = str(data.get('plan_mode_provider') or '').strip()
    plan_mode_provider = (
        _normalize_provider_name(plan_mode_provider_raw)
        if plan_mode_provider_raw
        else None
    )
    plan_mode_model_raw = str(data.get('plan_mode_model') or '').strip()
    plan_mode_model = None
    if plan_mode_model_raw:
        base_provider = plan_mode_provider or provider
        plan_mode_model = _normalize_model_name(base_provider, plan_mode_model_raw)
    plan_mode_reasoning_effort = _normalize_reasoning_effort(data.get('plan_mode_reasoning_effort'))
    return {
        'provider': provider,
        'model': model,
        'reasoning_effort': reasoning_effort,
        'plan_mode_provider': plan_mode_provider,
        'plan_mode_model': plan_mode_model,
        'plan_mode_reasoning_effort': plan_mode_reasoning_effort,
    }


def _write_workspace_settings(settings):
    provider = _normalize_provider_name(settings.get('provider'))
    model = str(settings.get('model') or '').strip() or _default_model_for_provider(provider)
    plan_mode_provider_raw = str(settings.get('plan_mode_provider') or '').strip()
    plan_mode_provider = (
        _normalize_provider_name(plan_mode_provider_raw)
        if plan_mode_provider_raw
        else None
    )
    plan_mode_model_raw = str(settings.get('plan_mode_model') or '').strip()
    plan_mode_model = None
    if plan_mode_model_raw:
        base_provider = plan_mode_provider or provider
        plan_mode_model = _normalize_model_name(base_provider, plan_mode_model_raw)
    reasoning_effort = _normalize_reasoning_effort(settings.get('reasoning_effort'))
    if reasoning_effort is None:
        reasoning_effort = _normalize_reasoning_effort(MODEL_DEFAULT_REASONING_EFFORT)
    plan_mode_reasoning_effort = _normalize_reasoning_effort(settings.get('plan_mode_reasoning_effort'))
    payload = {
        'provider': provider,
        'model': model,
        'reasoning_effort': reasoning_effort,
        'plan_mode_provider': plan_mode_provider,
        'plan_mode_model': plan_mode_model,
        'plan_mode_reasoning_effort': plan_mode_reasoning_effort,
    }
    MODEL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def get_settings():
    with _CONFIG_LOCK:
        settings = _read_workspace_settings()
        if not MODEL_SETTINGS_PATH.exists():
            _write_workspace_settings(settings)
        return settings


def _resolve_settings_values(
        current,
        provider=None,
        model=None,
        plan_mode_provider=None,
        plan_mode_model=None,
        reasoning_effort=None,
        plan_mode_reasoning_effort=None):
    current_provider = _normalize_provider_name(current.get('provider'))
    current_raw_model = str(current.get('model') or '').strip()
    current_model = _normalize_model_name(current_provider, current_raw_model)

    current_plan_provider_raw = str(current.get('plan_mode_provider') or '').strip()
    current_plan_provider = (
        _normalize_provider_name(current_plan_provider_raw)
        if current_plan_provider_raw
        else None
    )
    current_plan_model_raw = str(current.get('plan_mode_model') or '').strip()
    current_plan_model = None
    if current_plan_model_raw:
        current_plan_base_provider = current_plan_provider or current_provider
        current_plan_model = _normalize_model_name(current_plan_base_provider, current_plan_model_raw)
    current_reasoning_effort = _normalize_reasoning_effort(current.get('reasoning_effort'))
    if current_reasoning_effort is None:
        current_reasoning_effort = _normalize_reasoning_effort(MODEL_DEFAULT_REASONING_EFFORT)
    current_plan_mode_reasoning_effort = _normalize_reasoning_effort(current.get('plan_mode_reasoning_effort'))

    next_provider = current_provider
    provider_changed = False
    if provider is not None:
        next_provider = _normalize_provider_name(provider)
        provider_changed = next_provider != current_provider

    if model is None:
        next_model = _default_model_for_provider(next_provider) if provider_changed else current_model
    else:
        raw_model = str(model).strip()
        if provider_changed and raw_model:
            preview_model = _normalize_model_name(next_provider, raw_model)
            if raw_model == current_raw_model or preview_model == current_model:
                raw_model = ''
        next_model = _normalize_model_name(next_provider, raw_model)

    next_plan_provider = current_plan_provider
    if plan_mode_provider is not None:
        raw_plan_provider = str(plan_mode_provider).strip()
        next_plan_provider = _normalize_provider_name(raw_plan_provider) if raw_plan_provider else None

    if plan_mode_model is None:
        next_plan_model = current_plan_model
    else:
        raw_plan_model = str(plan_mode_model).strip()
        if raw_plan_model:
            plan_base_provider = next_plan_provider or next_provider
            next_plan_model = _normalize_model_name(plan_base_provider, raw_plan_model)
        else:
            next_plan_model = None

    if reasoning_effort is None:
        next_reasoning_effort = current_reasoning_effort
    else:
        next_reasoning_effort = _normalize_reasoning_effort(reasoning_effort)

    if plan_mode_reasoning_effort is None:
        next_plan_mode_reasoning_effort = current_plan_mode_reasoning_effort
    else:
        next_plan_mode_reasoning_effort = _normalize_reasoning_effort(plan_mode_reasoning_effort)

    return {
        'provider': next_provider,
        'model': next_model,
        'reasoning_effort': next_reasoning_effort,
        'plan_mode_provider': next_plan_provider,
        'plan_mode_model': next_plan_model,
        'plan_mode_reasoning_effort': next_plan_mode_reasoning_effort,
    }


def resolve_settings_preview(
        provider=None,
        model=None,
        plan_mode_provider=None,
        plan_mode_model=None,
        reasoning_effort=None,
        plan_mode_reasoning_effort=None):
    with _CONFIG_LOCK:
        current = _read_workspace_settings()
        return _resolve_settings_values(
            current,
            provider=provider,
            model=model,
            plan_mode_provider=plan_mode_provider,
            plan_mode_model=plan_mode_model,
            reasoning_effort=reasoning_effort,
            plan_mode_reasoning_effort=plan_mode_reasoning_effort,
        )


def update_settings(
        provider=None,
        model=None,
        plan_mode_provider=None,
        plan_mode_model=None,
        reasoning_effort=None,
        plan_mode_reasoning_effort=None):
    with _CONFIG_LOCK:
        current = _read_workspace_settings()
        payload = _resolve_settings_values(
            current,
            provider=provider,
            model=model,
            plan_mode_provider=plan_mode_provider,
            plan_mode_model=plan_mode_model,
            reasoning_effort=reasoning_effort,
            plan_mode_reasoning_effort=plan_mode_reasoning_effort,
        )
        _write_workspace_settings(payload)
        return payload


def resolve_execution_profile(plan_mode=False):
    settings = get_settings()

    default_provider = _normalize_provider_name(settings.get('provider'))
    default_model = _normalize_model_name(default_provider, settings.get('model'))
    default_reasoning_effort = _normalize_reasoning_effort(settings.get('reasoning_effort'))
    if default_reasoning_effort is None:
        default_reasoning_effort = _normalize_reasoning_effort(MODEL_DEFAULT_REASONING_EFFORT)
    if not plan_mode:
        return {
            'provider': default_provider,
            'model': default_model,
            'reasoning_effort': default_reasoning_effort,
        }

    plan_provider_raw = str(settings.get('plan_mode_provider') or '').strip()
    plan_model_raw = str(settings.get('plan_mode_model') or '').strip()

    if plan_provider_raw:
        plan_provider = _normalize_provider_name(plan_provider_raw)
    else:
        plan_provider = default_provider

    if plan_model_raw:
        plan_model = _normalize_model_name(plan_provider, plan_model_raw)
    elif plan_provider == default_provider:
        plan_model = default_model
    else:
        plan_model = _default_model_for_provider(plan_provider)

    plan_reasoning_effort = _normalize_reasoning_effort(settings.get('plan_mode_reasoning_effort'))
    if plan_reasoning_effort is None:
        plan_reasoning_effort = default_reasoning_effort

    return {
        'provider': plan_provider,
        'model': plan_model,
        'reasoning_effort': plan_reasoning_effort,
    }


def _provider_account_name(provider):
    normalized = _normalize_provider_name(provider)
    if normalized == 'claude':
        return 'Claude CLI'
    if normalized in _OPENAI_COMPATIBLE_PROVIDERS:
        return 'Samsung DTGPT API'
    return 'Gemini API'


def _empty_usage_summary(provider=None):
    normalized = _normalize_provider_name(provider)
    return {
        'provider': normalized,
        'five_hour': None,
        'weekly': None,
        'rate_limits_updated_at': None,
        'account_name': _provider_account_name(normalized),
        'tokens': None,
    }


def _normalize_usage_summary(data):
    if not isinstance(data, dict):
        return _empty_usage_summary()
    provider = _normalize_provider_name(data.get('provider'))
    tokens = data.get('tokens')
    if not isinstance(tokens, dict):
        tokens = None
    account_name = str(data.get('account_name') or '').strip() or _provider_account_name(provider)

    # Rate limit data 처리
    five_hour = data.get('five_hour')
    if five_hour and isinstance(five_hour, dict):
        five_hour = {
            'used_percent': _coerce_non_negative_float(five_hour.get('used_percent')),
            'resets_at': five_hour.get('resets_at')
        }
    else:
        five_hour = None

    weekly = data.get('weekly')
    if weekly and isinstance(weekly, dict):
        weekly = {
            'used_percent': _coerce_non_negative_float(weekly.get('used_percent')),
            'resets_at': weekly.get('resets_at')
        }
    else:
        weekly = None

    rate_limits_updated_at = None
    parsed_rate_limits_updated_at = parse_timestamp(data.get('rate_limits_updated_at'))
    if parsed_rate_limits_updated_at is not None:
        rate_limits_updated_at = normalize_timestamp(parsed_rate_limits_updated_at)

    return {
        'provider': provider,
        'five_hour': five_hour,
        'weekly': weekly,
        'rate_limits_updated_at': rate_limits_updated_at,
        'account_name': account_name,
        'tokens': tokens,
    }


def _read_usage_summary():
    source_path = _resolve_existing_path(MODEL_USAGE_SNAPSHOT_PATH, LEGACY_MODEL_USAGE_SNAPSHOT_PATH)
    try:
        raw = source_path.read_text(encoding='utf-8')
        data = json.loads(raw)
    except FileNotFoundError:
        return _empty_usage_summary()
    except Exception:
        return _empty_usage_summary()
    return _normalize_usage_summary(data)


def _write_usage_summary(summary):
    MODEL_USAGE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_USAGE_SNAPSHOT_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _usage_rate_limits_refresh_due(summary, max_age_seconds=_USAGE_RATE_LIMIT_REFRESH_SECONDS):
    normalized_summary = _normalize_usage_summary(summary)
    if normalized_summary.get('provider') != 'claude':
        return False
    if normalized_summary.get('five_hour') is None or normalized_summary.get('weekly') is None:
        return True
    if max_age_seconds is None:
        return False
    try:
        max_age = float(max_age_seconds)
    except (TypeError, ValueError):
        max_age = float(_USAGE_RATE_LIMIT_REFRESH_SECONDS)
    if max_age <= 0:
        return False
    refreshed_at = parse_timestamp(normalized_summary.get('rate_limits_updated_at'))
    if refreshed_at is None:
        return True
    age_seconds = (datetime.now(KST) - refreshed_at).total_seconds()
    return age_seconds >= max_age


def get_usage_summary_with_rate_limits(plan='pro', force_refresh=False, max_age_seconds=_USAGE_RATE_LIMIT_REFRESH_SECONDS):
    with _USAGE_LOCK:
        summary = _read_usage_summary()
    if summary.get('provider') != 'claude':
        return summary
    if not force_refresh and not _usage_rate_limits_refresh_due(summary, max_age_seconds=max_age_seconds):
        return summary
    try:
        rate_limits = get_monitor_rate_limits(plan=plan, use_cache=False)
    except Exception:
        _LOGGER.debug('usage rate limit refresh skipped', exc_info=True)
        return summary
    if not isinstance(rate_limits, dict):
        return summary

    with _USAGE_LOCK:
        current_summary = _read_usage_summary()
        if current_summary.get('provider') != 'claude':
            return current_summary
        if (
            not force_refresh
            and not _usage_rate_limits_refresh_due(current_summary, max_age_seconds=max_age_seconds)
        ):
            return current_summary

        next_summary = dict(current_summary)
        updated = False
        for key in ('five_hour', 'weekly'):
            value = rate_limits.get(key)
            if not isinstance(value, dict):
                continue
            next_summary[key] = {
                'used_percent': _coerce_non_negative_float(value.get('used_percent')),
                'resets_at': value.get('resets_at'),
            }
            updated = True

        if not updated:
            return current_summary

        next_summary['provider'] = 'claude'
        next_summary['account_name'] = _provider_account_name('claude')
        next_summary['rate_limits_updated_at'] = normalize_timestamp(None)
        normalized_summary = _normalize_usage_summary(next_summary)
        _write_usage_summary(normalized_summary)
        return normalized_summary


def _write_json_atomic(path, payload):
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=str(target_path.parent),
            prefix=f'.{target_path.name}.',
            suffix='.tmp',
            delete=False,
        ) as handle:
            handle.write(serialized)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
            temp_path = Path(handle.name)
        os.replace(temp_path, target_path)
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _usage_history_bucket_start_text(value=None):
    parsed = parse_timestamp(value)
    if parsed is None:
        parsed = datetime.now(KST)
    bucket_start = parsed.replace(minute=0, second=0, microsecond=0)
    return normalize_timestamp(bucket_start)


def _empty_usage_history_ledger():
    return {
        'version': _USAGE_HISTORY_VERSION,
        'updated_at': normalize_timestamp(None),
        'bucket_hours': _USAGE_HISTORY_BUCKET_HOURS,
        'timezone': 'Asia/Seoul',
        'items': [],
    }


def _normalize_usage_history_snapshot(value):
    if not isinstance(value, dict):
        return None
    bucket_start = _usage_history_bucket_start_text(
        value.get('bucket_start') or value.get('bucket') or value.get('hour')
    )
    recorded_at = normalize_timestamp(
        value.get('recorded_at') or value.get('captured_at') or bucket_start
    )
    token_total = _coerce_non_negative_int(value.get('token_total'))
    if token_total is None:
        token_total = _coerce_non_negative_int(value.get('cumulative_total_tokens'))
    token_input = _coerce_non_negative_int(value.get('token_input'))
    if token_input is None:
        token_input = _coerce_non_negative_int(value.get('cumulative_input_tokens'))
    token_output = _coerce_non_negative_int(value.get('token_output'))
    if token_output is None:
        token_output = _coerce_non_negative_int(value.get('cumulative_output_tokens'))
    token_reasoning = _coerce_non_negative_int(value.get('token_reasoning_output'))
    if token_reasoning is None:
        token_reasoning = _coerce_non_negative_int(value.get('cumulative_reasoning_tokens'))
    token_requests = _coerce_non_negative_int(value.get('token_requests'))
    if token_requests is None:
        token_requests = _coerce_non_negative_int(value.get('request_count'))
    provider = _normalize_provider_name(value.get('provider'))
    account_name = str(value.get('account_name') or '').strip() or _provider_account_name(provider)
    return {
        'bucket_start': bucket_start,
        'recorded_at': recorded_at,
        'provider': provider,
        'account_name': account_name,
        'token_total': token_total or 0,
        'token_input': token_input or 0,
        'token_output': token_output or 0,
        'token_reasoning_output': token_reasoning or 0,
        'token_requests': token_requests or 0,
        'five_hour_used_percent': None,
        'weekly_used_percent': None,
        'five_hour_resets_at': '',
        'weekly_resets_at': '',
    }


def _load_usage_history_ledger(path=MODEL_USAGE_HISTORY_PATH):
    source_path = _resolve_existing_path(path, LEGACY_MODEL_USAGE_HISTORY_PATH)
    try:
        raw = source_path.read_text(encoding='utf-8')
        data = json.loads(raw)
    except FileNotFoundError:
        return _empty_usage_history_ledger()
    except Exception:
        return _empty_usage_history_ledger()
    if not isinstance(data, dict):
        return _empty_usage_history_ledger()

    ledger = _empty_usage_history_ledger()
    version = _coerce_non_negative_int(data.get('version'))
    if version is not None:
        ledger['version'] = max(1, version)
    updated_at = str(data.get('updated_at') or '').strip()
    if updated_at:
        ledger['updated_at'] = normalize_timestamp(updated_at)
    bucket_hours = _coerce_non_negative_int(data.get('bucket_hours'))
    if bucket_hours is not None:
        ledger['bucket_hours'] = max(1, bucket_hours)
    timezone_text = str(data.get('timezone') or '').strip()
    if timezone_text:
        ledger['timezone'] = timezone_text

    raw_items = data.get('items')
    if isinstance(raw_items, list):
        deduped = {}
        for entry in raw_items:
            snapshot = _normalize_usage_history_snapshot(entry)
            if not snapshot:
                continue
            existing = deduped.get(snapshot['bucket_start'])
            if not existing or snapshot['recorded_at'] >= existing['recorded_at']:
                deduped[snapshot['bucket_start']] = snapshot
        items = sorted(deduped.values(), key=lambda item: item.get('bucket_start', ''))
        if len(items) > _USAGE_HISTORY_MAX_ITEMS:
            items = items[-_USAGE_HISTORY_MAX_ITEMS:]
        ledger['items'] = items
    return ledger


def _save_usage_history_ledger(ledger, path=MODEL_USAGE_HISTORY_PATH):
    _write_json_atomic(path, ledger)


def _build_usage_history_snapshot(usage_summary):
    usage = usage_summary if isinstance(usage_summary, dict) else {}
    tokens = usage.get('tokens') if isinstance(usage.get('tokens'), dict) else {}
    provider = _normalize_provider_name(usage.get('provider'))
    return _normalize_usage_history_snapshot({
        'bucket_start': _usage_history_bucket_start_text(None),
        'recorded_at': normalize_timestamp(None),
        'provider': provider,
        'account_name': usage.get('account_name'),
        'token_total': tokens.get('cumulative_total_tokens'),
        'token_input': tokens.get('cumulative_input_tokens'),
        'token_output': tokens.get('cumulative_output_tokens'),
        'token_reasoning_output': tokens.get('cumulative_reasoning_tokens'),
        'token_requests': tokens.get('request_count'),
    })


def record_usage_snapshot_if_due(force=False, usage_summary=None):
    if usage_summary is None:
        usage_summary = get_usage_summary()
    snapshot = _build_usage_history_snapshot(usage_summary)
    if not snapshot:
        return {
            'recorded': False,
            'usage': usage_summary,
            'snapshot': None,
        }

    recorded = False
    requested_force = bool(force)
    with _USAGE_HISTORY_LOCK:
        try:
            ledger = _load_usage_history_ledger()
            items = list(ledger.get('items') or [])
            existing_index = -1
            for idx, item in enumerate(items):
                if item.get('bucket_start') == snapshot['bucket_start']:
                    existing_index = idx
                    break
            if existing_index >= 0:
                if requested_force and items[existing_index] != snapshot:
                    items[existing_index] = snapshot
                    recorded = True
                else:
                    snapshot = items[existing_index]
            else:
                items.append(snapshot)
                recorded = True

            if recorded:
                items.sort(key=lambda item: item.get('bucket_start', ''))
                if len(items) > _USAGE_HISTORY_MAX_ITEMS:
                    items = items[-_USAGE_HISTORY_MAX_ITEMS:]
                ledger['items'] = items
                ledger['updated_at'] = normalize_timestamp(None)
                _save_usage_history_ledger(ledger)
        except Exception:
            _LOGGER.debug('usage history snapshot update skipped', exc_info=True)
            recorded = False

    return {
        'recorded': recorded,
        'usage': usage_summary,
        'snapshot': snapshot,
    }


def _build_usage_history_items(items):
    derived = []
    previous = None
    for raw in items:
        snapshot = _normalize_usage_history_snapshot(raw)
        if not snapshot:
            continue
        token_total = _coerce_non_negative_int(snapshot.get('token_total')) or 0
        delta_tokens = 0
        reset_detected = False
        if previous:
            previous_total = _coerce_non_negative_int(previous.get('token_total')) or 0
            delta_tokens = token_total - previous_total
            if delta_tokens < 0:
                reset_detected = True
                delta_tokens = token_total
        derived.append({
            **snapshot,
            'delta_tokens': max(0, int(delta_tokens)),
            'delta_workspace_tokens': max(0, int(delta_tokens)),
            'delta_account_tokens': 0,
            'delta_five_hour_used_percent': None,
            'delta_weekly_used_percent': None,
            'reset_detected': reset_detected,
            'tokens_per_five_hour_percent': None,
            'tokens_per_weekly_percent': None,
            'tokens_per_five_hour_percent_workspace': None,
            'tokens_per_weekly_percent_workspace': None,
            'tokens_per_five_hour_percent_account': None,
            'tokens_per_weekly_percent_account': None,
        })
        previous = snapshot
    return derived


def get_usage_history_summary(hours=168):
    requested_hours = _coerce_non_negative_int(hours)
    if requested_hours is None or requested_hours <= 0:
        requested_hours = 168
    requested_hours = min(requested_hours, _USAGE_HISTORY_MAX_ITEMS)

    with _USAGE_HISTORY_LOCK:
        try:
            ledger = _load_usage_history_ledger()
        except Exception:
            ledger = _empty_usage_history_ledger()

    items = list(ledger.get('items') or [])
    if requested_hours > 0 and len(items) > requested_hours:
        items = items[-requested_hours:]
    history_items = _build_usage_history_items(items)
    token_delta_total = sum(
        (_coerce_non_negative_int(item.get('delta_tokens')) or 0)
        for item in history_items
    )
    reset_count = sum(1 for item in history_items if item.get('reset_detected'))
    first_bucket = history_items[0]['bucket_start'] if history_items else ''
    last_bucket = history_items[-1]['bucket_start'] if history_items else ''
    first_recorded = history_items[0]['recorded_at'] if history_items else ''
    last_recorded = history_items[-1]['recorded_at'] if history_items else ''
    return {
        'path': str(MODEL_USAGE_HISTORY_PATH),
        'updated_at': ledger.get('updated_at'),
        'bucket_hours': max(1, _coerce_non_negative_int(ledger.get('bucket_hours')) or _USAGE_HISTORY_BUCKET_HOURS),
        'timezone': str(ledger.get('timezone') or 'Asia/Seoul'),
        'requested_hours': requested_hours,
        'count': len(history_items),
        'first_bucket_start': first_bucket,
        'last_bucket_start': last_bucket,
        'first_recorded_at': first_recorded,
        'last_recorded_at': last_recorded,
        'token_delta_scope': 'workspace',
        'token_delta_total': token_delta_total,
        'token_delta_total_workspace': token_delta_total,
        'token_delta_total_account': 0,
        'reset_detected_count': reset_count,
        'relation': {
            'scope': 'workspace',
            'five_hour': {
                'token_sum': token_delta_total,
                'percent_sum': 0,
                'tokens_per_percent': None,
            },
            'weekly': {
                'token_sum': token_delta_total,
                'percent_sum': 0,
                'tokens_per_percent': None,
            },
            'workspace': {
                'five_hour': {
                    'token_sum': token_delta_total,
                    'percent_sum': 0,
                    'tokens_per_percent': None,
                },
                'weekly': {
                    'token_sum': token_delta_total,
                    'percent_sum': 0,
                    'tokens_per_percent': None,
                },
            },
            'account': {
                'five_hour': {
                    'token_sum': 0,
                    'percent_sum': 0,
                    'tokens_per_percent': None,
                },
                'weekly': {
                    'token_sum': 0,
                    'percent_sum': 0,
                    'tokens_per_percent': None,
                },
            },
        },
        'scope': {
            'workspace_path': str(WORKSPACE_DIR),
            'usage_snapshot_path': str(MODEL_USAGE_SNAPSHOT_PATH),
            'relation_scope': 'workspace',
            'token_delta_key': 'delta_tokens',
        },
        'items': history_items,
    }


def _usage_snapshot_worker_loop():
    while True:
        try:
            usage_summary = get_usage_summary_with_rate_limits(
                max_age_seconds=_USAGE_SNAPSHOT_POLL_SECONDS
            )
            record_usage_snapshot_if_due(usage_summary=usage_summary)
        except Exception:
            _LOGGER.exception('usage snapshot worker failed')
        time.sleep(_USAGE_SNAPSHOT_POLL_SECONDS)


def ensure_usage_snapshot_background_worker():
    global _USAGE_SNAPSHOT_WORKER_STARTED
    with _USAGE_SNAPSHOT_WORKER_LOCK:
        if _USAGE_SNAPSHOT_WORKER_STARTED:
            return False
        worker = threading.Thread(
            target=_usage_snapshot_worker_loop,
            name='model-usage-snapshot-worker',
            daemon=True,
        )
        worker.start()
        _USAGE_SNAPSHOT_WORKER_STARTED = True
    return True


def _update_usage_summary_tokens(provider, input_tokens=None, output_tokens=None, total_tokens=None, reasoning_tokens=None):
    if (
        input_tokens is None
        and output_tokens is None
        and total_tokens is None
        and reasoning_tokens is None
    ):
        return

    normalized_provider = _normalize_provider_name(provider)

    with _USAGE_LOCK:
        summary = _read_usage_summary()
        current_tokens = summary.get('tokens') if isinstance(summary.get('tokens'), dict) else {}

        previous_input = _coerce_non_negative_int(current_tokens.get('cumulative_input_tokens')) or 0
        previous_output = _coerce_non_negative_int(current_tokens.get('cumulative_output_tokens')) or 0
        previous_total = _coerce_non_negative_int(current_tokens.get('cumulative_total_tokens')) or 0
        previous_reasoning = _coerce_non_negative_int(current_tokens.get('cumulative_reasoning_tokens')) or 0
        request_count = (_coerce_non_negative_int(current_tokens.get('request_count')) or 0) + 1

        summary['provider'] = normalized_provider
        summary['account_name'] = _provider_account_name(normalized_provider)
        summary['tokens'] = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
            'reasoning_tokens': reasoning_tokens,
            'cumulative_input_tokens': previous_input + (input_tokens or 0),
            'cumulative_output_tokens': previous_output + (output_tokens or 0),
            'cumulative_total_tokens': previous_total + (total_tokens or 0),
            'cumulative_reasoning_tokens': previous_reasoning + (reasoning_tokens or 0),
            'request_count': request_count,
            'updated_at': normalize_timestamp(None),
        }
        _write_usage_summary(summary)


def _extract_gemini_usage_metadata(payload):
    if isinstance(payload, list):
        for item in reversed(payload):
            usage = _extract_gemini_usage_metadata(item)
            if usage:
                return usage
        return None
    if not isinstance(payload, dict):
        return None
    usage = payload.get('usageMetadata')
    return usage if isinstance(usage, dict) else None


def _coerce_usage_field(usage_payload, *keys):
    if not isinstance(usage_payload, dict):
        return None
    for key in keys:
        value = _coerce_non_negative_int(usage_payload.get(key))
        if value is not None:
            return value
    return None


def _update_usage_summary_from_gemini_metadata(provider, usage_metadata):
    if not isinstance(usage_metadata, dict):
        return
    input_tokens = _coerce_usage_field(usage_metadata, 'promptTokenCount', 'inputTokenCount')
    output_tokens = _coerce_usage_field(usage_metadata, 'candidatesTokenCount', 'outputTokenCount')
    total_tokens = _coerce_usage_field(usage_metadata, 'totalTokenCount')
    reasoning_tokens = _coerce_usage_field(usage_metadata, 'thoughtsTokenCount', 'reasoningTokenCount')
    _update_usage_summary_tokens(provider, input_tokens, output_tokens, total_tokens, reasoning_tokens)


def _update_usage_summary_from_openai_usage(provider, usage_payload):
    if not isinstance(usage_payload, dict):
        return
    input_tokens = _coerce_usage_field(usage_payload, 'prompt_tokens', 'input_tokens')
    output_tokens = _coerce_usage_field(usage_payload, 'completion_tokens', 'output_tokens')
    total_tokens = _coerce_usage_field(usage_payload, 'total_tokens')
    reasoning_tokens = _coerce_usage_field(usage_payload, 'reasoning_tokens')
    _update_usage_summary_tokens(provider, input_tokens, output_tokens, total_tokens, reasoning_tokens)


def get_usage_summary():
    with _USAGE_LOCK:
        return _read_usage_summary()


def _safe_file_size(path):
    try:
        return max(0, int(path.stat().st_size))
    except FileNotFoundError:
        return 0
    except Exception:
        return 0


def _collect_session_storage_summary(data):
    sessions = data.get('sessions', []) if isinstance(data, dict) else []
    if not isinstance(sessions, list):
        sessions = []

    message_count = 0
    work_details_count = 0
    work_details_bytes = 0

    for session in sessions:
        messages = session.get('messages', []) if isinstance(session, dict) else []
        if not isinstance(messages, list):
            continue
        message_count += len(messages)
        for message in messages:
            if not isinstance(message, dict):
                continue
            details = message.get('work_details')
            if not isinstance(details, str) or not details:
                continue
            work_details_count += 1
            work_details_bytes += len(details.encode('utf-8'))

    source_path = _resolve_existing_path(MODEL_CHAT_STORE_PATH, LEGACY_MODEL_CHAT_STORE_PATH)
    store_bytes = _safe_file_size(source_path)
    return {
        'path': str(source_path),
        'total_bytes': store_bytes,
        'session_count': len(sessions),
        'message_count': message_count,
        'work_details_count': work_details_count,
        'work_details_bytes': work_details_bytes,
    }


def get_session_storage_summary():
    with _DATA_LOCK:
        data = _load_data()
    return _collect_session_storage_summary(data)


def _extract_token_count_from_usage(value):
    if not isinstance(value, dict):
        return None
    total = _coerce_non_negative_int(value.get('total_tokens'))
    if total is not None:
        return total
    parts = []
    for key in _TOKEN_PART_KEYS:
        count = _coerce_non_negative_int(value.get(key))
        if count is not None:
            parts.append(count)
    if not parts:
        return None
    return sum(parts)


def _estimate_tokens_from_text(text):
    if not isinstance(text, str):
        text = '' if text is None else str(text)
    normalized = ' '.join(text.split())
    if not normalized:
        return 0
    # Lightweight approximation for GPT-family tokenization.
    return max(1, (len(normalized) + 3) // 4)


def _estimate_message_tokens(message):
    if not isinstance(message, dict):
        return 0
    for key in _TOKEN_COUNT_KEYS:
        count = _coerce_non_negative_int(message.get(key))
        if count is not None:
            return count
    for key in _TOKEN_USAGE_KEYS:
        count = _extract_token_count_from_usage(message.get(key))
        if count is not None:
            return count
    parts = []
    for key in _TOKEN_PART_KEYS:
        count = _coerce_non_negative_int(message.get(key))
        if count is not None:
            parts.append(count)
    if parts:
        return sum(parts)
    return _estimate_tokens_from_text(message.get('content'))


def _estimate_session_tokens(session):
    messages = session.get('messages', []) if isinstance(session, dict) else []
    if not isinstance(messages, list):
        return 0
    total = 0
    for message in messages:
        total += _estimate_message_tokens(message)
    return total


def _sort_sessions(sessions):
    return sorted(
        sessions,
        key=lambda item: item.get('updated_at') or item.get('created_at') or '',
        reverse=True,
    )


def _find_session(sessions, session_id):
    for session in sessions:
        if session.get('id') == session_id:
            return session
    return None


def _count_pending_queue_items(session):
    queue = _normalize_session_pending_queue(session)
    return len(queue)


def _peek_pending_queue_entry(session_id):
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
        if not session:
            return None, 0
        queue = _normalize_session_pending_queue(session)
        if not queue:
            return None, 0
        return deepcopy(queue[0]), len(queue)


def _remove_pending_queue_entry(session_id, entry_id):
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        session = _find_session(sessions, session_id)
        if not session:
            return 0
        queue = _normalize_session_pending_queue(session)
        removed = False
        if entry_id:
            for index, item in enumerate(queue):
                if item.get('id') == entry_id:
                    queue.pop(index)
                    removed = True
                    break
        if not removed and queue:
            queue.pop(0)
            removed = True
        if removed:
            session['updated_at'] = normalize_timestamp(None)
            data['sessions'] = _sort_sessions(sessions)
            _save_data(data)
        return len(queue)


def get_pending_queue_count_for_session(session_id):
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
        if not session:
            return 0
        return _count_pending_queue_items(session)


def _has_user_message(session):
    return any(message.get('role') == 'user' for message in session.get('messages', []))


def generate_session_title(prompt):
    normalized = ' '.join(str(prompt or '').strip().split())
    if not normalized:
        return 'New session'
    if len(normalized) > 24:
        return f"{normalized[:24]}..."
    return normalized


def list_sessions():
    with _DATA_LOCK:
        data = _load_data()
        sessions = _sort_sessions(data.get('sessions', []))
    summary = []
    for session in sessions:
        pending_queue_count = _count_pending_queue_items(session)
        summary.append(
            {
                'id': session.get('id'),
                'title': session.get('title') or 'New session',
                'created_at': session.get('created_at'),
                'updated_at': session.get('updated_at'),
                'message_count': len(session.get('messages', [])),
                'pending_queue_count': pending_queue_count,
                'token_count': _estimate_session_tokens(session),
            }
        )
    return summary


def get_session(session_id):
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
    if not session:
        return None
    session_copy = deepcopy(session)
    pending_queue = _normalize_session_pending_queue(session_copy)
    session_copy[_PENDING_QUEUE_KEY] = pending_queue
    session_copy['pending_queue_count'] = len(pending_queue)
    return session_copy


def create_session(title=None):
    now = normalize_timestamp(None)
    session = {
        'id': uuid.uuid4().hex,
        'title': (title or '').strip() or 'New session',
        'created_at': now,
        'updated_at': now,
        'messages': [],
        _PENDING_QUEUE_KEY: [],
    }
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        sessions.append(session)
        data['sessions'] = _sort_sessions(sessions)
        _save_data(data)
    return deepcopy(session)


def append_message(session_id, role, content, metadata=None, created_at=None):
    if content is None:
        content = ''
    message = {
        'id': uuid.uuid4().hex,
        'role': role,
        'content': str(content),
        'created_at': normalize_timestamp(created_at),
    }
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if key in message:
                continue
            message[key] = value
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        session = _find_session(sessions, session_id)
        if not session:
            return None
        session.setdefault('messages', []).append(message)
        session['updated_at'] = normalize_timestamp(None)
        data['sessions'] = _sort_sessions(sessions)
        _save_data(data)
    return deepcopy(message)


def update_message(session_id, message_id, content, role=None, metadata=None, created_at=None):
    """기존 메시지의 content/role/metadata를 업데이트합니다 (draft 교체 등에 사용)."""
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        session = _find_session(sessions, session_id)
        if not session:
            return None
        for msg in session.get('messages', []):
            if msg.get('id') != message_id:
                continue
            msg['content'] = str(content)
            if role is not None:
                msg['role'] = role
            if created_at is not None:
                msg['created_at'] = normalize_timestamp(created_at)
            if isinstance(metadata, dict):
                for key, value in metadata.items():
                    if key not in ('id', 'role', 'content', 'created_at'):
                        msg[key] = value
            msg.pop('is_draft', None)
            session['updated_at'] = normalize_timestamp(None)
            data['sessions'] = _sort_sessions(sessions)
            _save_data(data)
            return deepcopy(msg)
        return None


def ensure_default_title(session_id, prompt):
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
        if not session:
            return None
        title = session.get('title') or ''
        if title.strip() and title != 'New session':
            return deepcopy(session)
        if _has_user_message(session):
            return deepcopy(session)
        session['title'] = generate_session_title(prompt)
        session['updated_at'] = normalize_timestamp(None)
        data['sessions'] = _sort_sessions(data.get('sessions', []))
        _save_data(data)
        return deepcopy(session)


def rename_session(session_id, title):
    if not title:
        return None
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
        if not session:
            return None
        session['title'] = title
        session['updated_at'] = normalize_timestamp(None)
        data['sessions'] = _sort_sessions(data.get('sessions', []))
        _save_data(data)
        return deepcopy(session)


def delete_session(session_id):
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        remaining = [session for session in sessions if session.get('id') != session_id]
        if len(remaining) == len(sessions):
            return False
        data['sessions'] = _sort_sessions(remaining)
        _save_data(data)
        return True


def _normalize_context_text(value):
    if not isinstance(value, str):
        value = '' if value is None else str(value)
    text = value.replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        return ''
    lines = [line.rstrip() for line in text.split('\n')]
    return '\n'.join(lines).strip()


def _normalize_context_role(value, fallback='user'):
    role = str(value or '').strip().lower() or fallback
    if role in _ROLE_LABELS:
        return role
    return fallback


def _strip_context_auto_notes(value):
    normalized = _normalize_context_text(value)
    if not normalized:
        return ''
    lines = normalized.split('\n')
    removed = False
    while lines:
        tail = lines[-1].strip()
        if not tail:
            lines.pop()
            continue
        if _CONTEXT_AUTO_NOTE_LINE_PATTERN.match(tail):
            removed = True
            lines.pop()
            continue
        break
    if not removed:
        return normalized
    return '\n'.join(lines).strip()


def _single_line_text(value):
    normalized = _normalize_context_text(value)
    if not normalized:
        return ''
    return ' '.join(normalized.split())


def _clip_text(value, max_chars):
    if not isinstance(value, str):
        value = '' if value is None else str(value)
    if max_chars <= 0:
        return ''
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return f"{value[:max_chars - 3]}..."


def _looks_like_unified_diff(text):
    body = str(text or '')
    if not body.strip():
        return False
    if re.search(r'(?m)^diff --git ', body):
        return True
    has_old = re.search(r'(?m)^---\s+\S+', body)
    has_new = re.search(r'(?m)^\+\+\+\s+\S+', body)
    has_hunk = re.search(r'(?m)^@@\s', body)
    return bool(has_old and has_new and has_hunk)


def _extract_patch_text_from_response(content):
    text = str(content or '')
    if not text.strip():
        return ''

    candidates = []
    for match in _PATCH_BLOCK_PATTERN.finditer(text):
        block = (match.group(1) or '').strip()
        if _looks_like_unified_diff(block):
            candidates.append(block)
    if candidates:
        return '\n\n'.join(candidates).strip()

    stripped = text.strip()
    if _looks_like_unified_diff(stripped):
        return stripped
    return ''


def _extract_tool_commands_from_response(content):
    text = str(content or '')
    if not text.strip():
        return []

    commands = []
    for match in _TOOL_RUN_BLOCK_PATTERN.finditer(text):
        block = (match.group(1) or '').replace('\r\n', '\n').replace('\r', '\n')
        if not block.strip():
            continue

        non_empty_lines = [line.strip() for line in block.split('\n') if line.strip()]
        if not non_empty_lines:
            continue

        first_line = non_empty_lines[0].lower()
        if not any(first_line.startswith(marker) for marker in _TOOL_RUN_MARKERS):
            continue

        for line in non_empty_lines[1:]:
            if line.startswith('#'):
                continue
            normalized = line[2:].strip() if line.startswith('$ ') else line
            if not normalized:
                continue
            commands.append(normalized)
            if len(commands) >= _TOOL_RUN_MAX_COMMANDS:
                return commands
    return commands


def _extract_patch_path_token(line):
    token = str(line or '').strip()
    if not token:
        return ''
    token = token.split('\t', 1)[0].strip()
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        token = token[1:-1].strip()
    if token:
        parts = token.split(' ', 1)
        token = parts[0].strip()
    return token


def _match_blocked_workspace_prefix(relative_path):
    normalized = str(relative_path or '').strip().replace('\\', '/').strip('/')
    if not normalized:
        return ''
    path_parts = PurePosixPath(normalized).parts
    for prefix, prefix_parts in zip(_BLOCKED_WORKSPACE_PREFIXES, _BLOCKED_WORKSPACE_PREFIX_PARTS):
        if not prefix_parts:
            continue
        if len(path_parts) < len(prefix_parts):
            continue
        if tuple(path_parts[:len(prefix_parts)]) == tuple(prefix_parts):
            return prefix
    return ''


def _normalize_patch_path(token):
    value = str(token or '').strip().replace('\\', '/')
    if not value:
        return None, None
    if value == '/dev/null':
        return None, None
    if value.startswith('a/') or value.startswith('b/'):
        value = value[2:]
    value = value.strip().lstrip('./')
    # Some model outputs include a workspace/ prefix even though paths should be workspace-relative.
    while value.startswith('workspace/'):
        value = value[len('workspace/'):]
    if not value:
        return None, None

    pure_path = PurePosixPath(value)
    if pure_path.is_absolute():
        return None, f'절대 경로는 허용되지 않습니다: {value}'
    if any(part == '..' for part in pure_path.parts):
        return None, f'상위 경로(..)는 허용되지 않습니다: {value}'

    workspace_root = WORKSPACE_DIR.resolve()
    resolved = (workspace_root / pure_path.as_posix()).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        return None, f'workspace 밖 경로는 허용되지 않습니다: {value}'
    normalized_path = pure_path.as_posix()
    blocked_prefix = _match_blocked_workspace_prefix(normalized_path)
    if blocked_prefix:
        return None, f'접근 제한 경로는 수정할 수 없습니다: {blocked_prefix}/'
    return normalized_path, None


def _collect_patch_paths(patch_text):
    files = []
    invalid = []
    seen = set()

    for raw_line in str(patch_text or '').splitlines():
        line = raw_line.rstrip('\n')
        tokens = []
        if line.startswith('diff --git '):
            parts = line.split()
            if len(parts) >= 4:
                tokens.extend([parts[2], parts[3]])
        elif line.startswith('--- '):
            tokens.append(_extract_patch_path_token(line[4:]))
        elif line.startswith('+++ '):
            tokens.append(_extract_patch_path_token(line[4:]))

        for token in tokens:
            normalized, error = _normalize_patch_path(token)
            if error:
                invalid.append(error)
                continue
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            files.append(normalized)
    return files, invalid


def _patch_section_mode(old_header, new_header, new_file_declared, deleted_file_declared):
    if new_file_declared or old_header == '/dev/null':
        return 'new'
    if deleted_file_declared or new_header == '/dev/null':
        return 'delete'
    return 'normal'


def _sanitize_create_delete_hunks(patch_text):
    text = str(patch_text or '')
    if not text:
        return text, False

    lines = text.split('\n')
    output = []
    changed = False
    old_header = ''
    new_header = ''
    new_file_declared = False
    deleted_file_declared = False
    in_hunk = False

    for line in lines:
        if line.startswith('diff --git '):
            old_header = ''
            new_header = ''
            new_file_declared = False
            deleted_file_declared = False
            in_hunk = False
        elif line.startswith('new file mode '):
            new_file_declared = True
            in_hunk = False
        elif line.startswith('deleted file mode '):
            deleted_file_declared = True
            in_hunk = False
        elif line.startswith('--- '):
            old_header = _extract_patch_path_token(line[4:])
            in_hunk = False
        elif line.startswith('+++ '):
            new_header = _extract_patch_path_token(line[4:])
            in_hunk = False
        elif line.startswith('@@ '):
            in_hunk = True

        section_mode = _patch_section_mode(
            old_header,
            new_header,
            new_file_declared,
            deleted_file_declared,
        )
        if in_hunk and section_mode == 'new' and line.startswith('-') and not line.startswith('--- '):
            changed = True
            continue
        if in_hunk and section_mode == 'new' and line.startswith(' '):
            changed = True
            output.append(f'+{line[1:]}')
            continue
        if in_hunk and section_mode == 'delete' and line.startswith('+') and not line.startswith('+++ '):
            changed = True
            continue
        if in_hunk and section_mode == 'delete' and line == '-':
            # Models sometimes emit an extra blank-line removal for deleted files.
            # Dropping it keeps delete hunks resilient when the source has no blank line.
            changed = True
            continue
        if in_hunk and section_mode == 'delete' and line.startswith(' '):
            changed = True
            output.append(f'-{line[1:]}')
            continue
        output.append(line)

    return '\n'.join(output), changed


def _recount_patch_hunk_headers(patch_text):
    text = str(patch_text or '')
    if not text:
        return text, False

    lines = text.split('\n')
    output = []
    changed = False
    index = 0

    while index < len(lines):
        line = lines[index]
        match = _HUNK_HEADER_PATTERN.match(line)
        if not match:
            output.append(line)
            index += 1
            continue

        old_start = int(match.group(1))
        new_start = int(match.group(3))
        suffix = match.group(5) or ''

        hunk_lines = []
        cursor = index + 1
        while cursor < len(lines):
            next_line = lines[cursor]
            if next_line.startswith('diff --git ') or next_line.startswith('@@ '):
                break
            if next_line.startswith('--- ') or next_line.startswith('+++ '):
                break
            hunk_lines.append(next_line)
            cursor += 1

        old_count = 0
        new_count = 0
        for hunk_line in hunk_lines:
            if hunk_line.startswith('-'):
                old_count += 1
                continue
            if hunk_line.startswith('+'):
                new_count += 1
                continue
            if hunk_line.startswith(' '):
                old_count += 1
                new_count += 1
                continue
            if hunk_line == '\\ No newline at end of file':
                continue
            old_count += 1
            new_count += 1

        old_range = str(old_start) if old_count == 1 else f'{old_start},{old_count}'
        new_range = str(new_start) if new_count == 1 else f'{new_start},{new_count}'
        normalized_header = f'@@ -{old_range} +{new_range} @@{suffix}'
        if normalized_header != line:
            changed = True
        output.append(normalized_header)
        output.extend(hunk_lines)
        index = cursor

    return '\n'.join(output), changed


def _normalize_patch_header_token(token, side):
    raw = _extract_patch_path_token(token)
    if not raw:
        return ''
    if raw == '/dev/null':
        return '/dev/null'

    normalized, _ = _normalize_patch_path(raw)
    if normalized:
        return f'{side}/{normalized}'

    stripped = raw
    if stripped.startswith('a/') or stripped.startswith('b/'):
        stripped = stripped[2:]
    stripped = stripped.strip().lstrip('./')
    if not stripped:
        return raw
    return f'{side}/{stripped}'


def _infer_diff_header_tokens(old_token, new_token):
    old_raw = _extract_patch_path_token(old_token)
    new_raw = _extract_patch_path_token(new_token)

    section_path = ''
    for candidate in (new_raw, old_raw):
        if not candidate or candidate == '/dev/null':
            continue
        normalized, _ = _normalize_patch_path(candidate)
        if normalized:
            section_path = normalized
            break
        stripped = candidate
        if stripped.startswith('a/') or stripped.startswith('b/'):
            stripped = stripped[2:]
        stripped = stripped.strip().lstrip('./')
        if stripped:
            section_path = stripped
            break

    if section_path:
        return f'a/{section_path}', f'b/{section_path}'

    left = _normalize_patch_header_token(old_raw, 'a') or 'a/patch'
    right = _normalize_patch_header_token(new_raw, 'b') or 'b/patch'

    if left == '/dev/null' and right.startswith('b/'):
        right_path = right[2:]
        if right_path:
            left = f'a/{right_path}'
    if right == '/dev/null' and left.startswith('a/'):
        left_path = left[2:]
        if left_path:
            right = f'b/{left_path}'

    return left, right


def _normalize_patch_headers_for_git_apply(patch_text):
    text = str(patch_text or '')
    if not text:
        return text, False

    lines = text.split('\n')
    output = []
    changed = False
    section_has_diff_header = False
    section_has_new_mode = False
    section_has_deleted_mode = False
    index = 0

    while index < len(lines):
        line = lines[index]

        if line.startswith('diff --git '):
            parts = line.split()
            if len(parts) >= 4:
                left, right = _infer_diff_header_tokens(parts[2], parts[3])
                normalized_line = f'diff --git {left} {right}'
                if normalized_line != line:
                    changed = True
                output.append(normalized_line)
            else:
                output.append(line)
            section_has_diff_header = True
            section_has_new_mode = False
            section_has_deleted_mode = False
            index += 1
            continue

        if line.startswith('new file mode '):
            section_has_new_mode = True
            output.append(line)
            index += 1
            continue

        if line.startswith('deleted file mode '):
            section_has_deleted_mode = True
            output.append(line)
            index += 1
            continue

        if line.startswith('--- ') and index + 1 < len(lines) and lines[index + 1].startswith('+++ '):
            old_raw = _extract_patch_path_token(line[4:])
            new_raw = _extract_patch_path_token(lines[index + 1][4:])
            old_header = _normalize_patch_header_token(old_raw, 'a') or old_raw
            new_header = _normalize_patch_header_token(new_raw, 'b') or new_raw

            if not section_has_diff_header:
                left, right = _infer_diff_header_tokens(old_raw, new_raw)
                output.append(f'diff --git {left} {right}')
                changed = True

            if old_header == '/dev/null' and not section_has_new_mode:
                output.append('new file mode 100644')
                changed = True
            if new_header == '/dev/null' and not section_has_deleted_mode:
                output.append('deleted file mode 100644')
                changed = True

            normalized_old_line = f'--- {old_header}'
            normalized_new_line = f'+++ {new_header}'
            if normalized_old_line != line or normalized_new_line != lines[index + 1]:
                changed = True
            output.append(normalized_old_line)
            output.append(normalized_new_line)
            section_has_diff_header = False
            section_has_new_mode = False
            section_has_deleted_mode = False
            index += 2
            continue

        if line.startswith('@@ '):
            section_has_diff_header = False

        output.append(line)
        index += 1

    return '\n'.join(output), changed


def _summarize_patch_error(result):
    message = (result.stderr or result.stdout or '').strip()
    if not message:
        message = f'git apply 실패 (exit={result.returncode})'
    return message


def _is_patch_already_applied(base_git_apply_cmd, patch_path, git_cwd, timeout_seconds):
    reverse_check_cmd = list(base_git_apply_cmd)
    reverse_check_cmd.extend([
        '--reverse',
        '--check',
        '--unidiff-zero',
        '--recount',
        '--whitespace=nowarn',
        patch_path,
    ])
    reverse_result = subprocess.run(
        reverse_check_cmd,
        cwd=git_cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return reverse_result.returncode == 0


def _resolve_git_apply_scope(workspace_dir, timeout_seconds):
    workspace_root = Path(workspace_dir).resolve()
    default_scope = {
        'git_cwd': str(workspace_root),
        'directory': None,
    }
    probe_timeout = max(2, min(10, int(timeout_seconds)))
    try:
        top_level_result = subprocess.run(
            ['git', '-C', str(workspace_root), 'rev-parse', '--show-toplevel'],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=probe_timeout,
            check=False,
        )
    except Exception:
        return default_scope

    if top_level_result.returncode != 0:
        return default_scope

    top_level_raw = str(top_level_result.stdout or '').strip()
    if not top_level_raw:
        return default_scope

    try:
        top_level_path = Path(top_level_raw).resolve()
    except Exception:
        return default_scope

    if top_level_path == workspace_root:
        return default_scope

    try:
        workspace_relative = workspace_root.relative_to(top_level_path).as_posix()
    except ValueError:
        return default_scope

    workspace_relative = workspace_relative.strip().strip('/')
    if not workspace_relative:
        return default_scope

    return {
        'git_cwd': str(top_level_path),
        'directory': workspace_relative,
    }


def _apply_patch_text_to_workspace(patch_text):
    payload = {
        'detected': True,
        'applied': False,
        'already_applied': False,
        'files': [],
        'error': None,
        'sanitized_hunks': False,
        'normalized_headers': False,
        'recounted_hunks': False,
    }
    normalized_patch = str(patch_text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not normalized_patch.strip():
        payload['detected'] = False
        return payload
    if not normalized_patch.endswith('\n'):
        normalized_patch = f'{normalized_patch}\n'
    normalized_patch, sanitized_hunks = _sanitize_create_delete_hunks(normalized_patch)
    payload['sanitized_hunks'] = bool(sanitized_hunks)
    normalized_patch, normalized_headers = _normalize_patch_headers_for_git_apply(normalized_patch)
    payload['normalized_headers'] = bool(normalized_headers)
    normalized_patch, recounted_hunks = _recount_patch_hunk_headers(normalized_patch)
    payload['recounted_hunks'] = bool(recounted_hunks)
    if not normalized_patch.endswith('\n'):
        normalized_patch = f'{normalized_patch}\n'
    if len(normalized_patch) > _PATCH_MAX_CHARS:
        payload['error'] = f'patch 크기가 너무 큽니다. ({len(normalized_patch)} chars)'
        return payload
    if not _looks_like_unified_diff(normalized_patch):
        payload['error'] = 'unified diff 형식이 아닙니다.'
        return payload

    files, invalid_paths = _collect_patch_paths(normalized_patch)
    if invalid_paths:
        payload['error'] = invalid_paths[0]
        payload['files'] = files
        return payload
    payload['files'] = files

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    patch_path = None
    timeout_seconds = max(10, min(300, int(MODEL_EXEC_TIMEOUT_SECONDS)))
    apply_scope = _resolve_git_apply_scope(WORKSPACE_DIR, timeout_seconds)
    git_cwd = apply_scope.get('git_cwd') or str(WORKSPACE_DIR)
    apply_directory = str(apply_scope.get('directory') or '').strip()

    base_git_apply_cmd = ['git', '-C', git_cwd, 'apply']
    if apply_directory:
        # If workspace_dir is nested under another Git repo, pin patch paths into workspace_dir.
        base_git_apply_cmd.extend(['--directory', apply_directory])
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            suffix='.diff',
            dir=str(WORKSPACE_DIR),
            delete=False,
        ) as handle:
            handle.write(normalized_patch)
            patch_path = handle.name

        check_cmd = list(base_git_apply_cmd)
        check_cmd.extend(['--check', '--unidiff-zero', '--recount', '--whitespace=nowarn', patch_path])
        check_result = subprocess.run(
            check_cmd,
            cwd=git_cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if check_result.returncode != 0:
            if _is_patch_already_applied(base_git_apply_cmd, patch_path, git_cwd, timeout_seconds):
                payload['applied'] = True
                payload['already_applied'] = True
                payload['error'] = None
                return payload
            payload['error'] = _summarize_patch_error(check_result)
            return payload

        apply_cmd = list(base_git_apply_cmd)
        apply_cmd.extend(['--unidiff-zero', '--recount', '--whitespace=nowarn', patch_path])
        apply_result = subprocess.run(
            apply_cmd,
            cwd=git_cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if apply_result.returncode != 0:
            if _is_patch_already_applied(base_git_apply_cmd, patch_path, git_cwd, timeout_seconds):
                payload['applied'] = True
                payload['already_applied'] = True
                payload['error'] = None
                return payload
            payload['error'] = _summarize_patch_error(apply_result)
            return payload

        payload['applied'] = True
        return payload
    except FileNotFoundError:
        payload['error'] = 'git 명령을 찾을 수 없습니다.'
        return payload
    except subprocess.TimeoutExpired:
        payload['error'] = 'patch 적용 시간이 초과되었습니다.'
        return payload
    except Exception as exc:
        payload['error'] = f'patch 적용 중 오류가 발생했습니다: {exc}'
        return payload
    finally:
        if patch_path:
            try:
                os.unlink(patch_path)
            except Exception:
                pass


def _is_allowed_tool_executable(value):
    token = str(value or '').strip()
    if not token:
        return False, '실행 명령이 비어 있습니다.'

    executable_name = os.path.basename(token).lower()
    if executable_name in _TOOL_RUN_ALLOWED_EXECUTABLES:
        return True, None

    normalized_token = token.replace('\\', '/')
    is_path_like = '/' in normalized_token or normalized_token.startswith('.')
    if not is_path_like:
        return False, f'허용되지 않은 실행 명령입니다: {token}'
    if normalized_token.startswith('./'):
        normalized_token = normalized_token[2:]
    normalized_path, error = _normalize_patch_path(normalized_token)
    if error:
        return False, error
    if not normalized_path:
        return False, f'허용되지 않은 실행 명령입니다: {token}'
    return True, None


def _requires_shell_wrapper(command_text):
    text = str(command_text or '')
    if not text:
        return False
    for token in ('&&', '||', ';', '|'):
        if token in text:
            return True
    return False


def _parse_tool_command(raw_command):
    command_text = str(raw_command or '').strip()
    if not command_text:
        return None, '실행 명령이 비어 있습니다.'

    lowered = command_text.lower()
    if _requires_shell_wrapper(command_text) and not (lowered.startswith('bash ') or lowered.startswith('sh ')):
        return ['bash', '-lc', command_text], None

    try:
        argv = shlex.split(command_text, posix=True)
    except ValueError as exc:
        return None, f'실행 명령 파싱에 실패했습니다: {exc}'

    if not argv:
        return None, '실행 명령이 비어 있습니다.'

    allowed, error = _is_allowed_tool_executable(argv[0])
    if not allowed:
        return None, error
    return argv, None


def _execute_tool_commands_in_workspace(commands):
    payload = {
        'detected': bool(commands),
        'executed': [],
        'error': None,
        'skipped': False,
    }
    if not commands:
        return payload

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    timeout_seconds = max(5, min(300, int(MODEL_EXEC_TIMEOUT_SECONDS)))

    for raw_command in commands:
        argv, parse_error = _parse_tool_command(raw_command)
        if parse_error:
            payload['error'] = parse_error
            payload['executed'].append(
                {
                    'command': str(raw_command or '').strip(),
                    'ok': False,
                    'exit_code': None,
                    'stdout': '',
                    'stderr': parse_error,
                }
            )
            break

        try:
            result = subprocess.run(
                argv,
                cwd=str(WORKSPACE_DIR),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            message = f'명령을 찾을 수 없습니다: {argv[0]}'
            payload['error'] = message
            payload['executed'].append(
                {
                    'command': str(raw_command or '').strip(),
                    'ok': False,
                    'exit_code': None,
                    'stdout': '',
                    'stderr': message,
                }
            )
            break
        except subprocess.TimeoutExpired:
            message = f'명령 실행 시간이 초과되었습니다: {raw_command}'
            payload['error'] = message
            payload['executed'].append(
                {
                    'command': str(raw_command or '').strip(),
                    'ok': False,
                    'exit_code': None,
                    'stdout': '',
                    'stderr': message,
                }
            )
            break
        except Exception as exc:
            message = f'명령 실행 중 오류가 발생했습니다: {exc}'
            payload['error'] = message
            payload['executed'].append(
                {
                    'command': str(raw_command or '').strip(),
                    'ok': False,
                    'exit_code': None,
                    'stdout': '',
                    'stderr': message,
                }
            )
            break

        stdout_text = _clip_text((result.stdout or '').strip(), _TOOL_RUN_MAX_OUTPUT_CHARS)
        stderr_text = _clip_text((result.stderr or '').strip(), _TOOL_RUN_MAX_OUTPUT_CHARS)
        ok = result.returncode == 0
        payload['executed'].append(
            {
                'command': str(raw_command or '').strip(),
                'ok': ok,
                'exit_code': int(result.returncode),
                'stdout': stdout_text,
                'stderr': stderr_text,
            }
        )
        if not ok:
            payload['error'] = stderr_text or stdout_text or f'명령 실행에 실패했습니다. (exit={result.returncode})'
            break

    return payload


def _format_tool_run_note(result):
    if not isinstance(result, dict) or not result.get('detected'):
        return ''

    if result.get('skipped'):
        reason = str(result.get('error') or '').strip() or '실행이 생략되었습니다.'
        return f'[Tool Run] 실행 생략: {reason}'

    executed = result.get('executed') if isinstance(result.get('executed'), list) else []
    if not executed:
        reason = str(result.get('error') or '').strip() or '실행 가능한 명령이 없습니다.'
        return f'[Tool Run] 실행 없음: {reason}'

    if result.get('error'):
        failed = None
        for item in reversed(executed):
            if not item.get('ok'):
                failed = item
                break
        if failed:
            detail = _single_line_text(failed.get('stderr') or failed.get('stdout') or '')
            detail = _clip_text(detail, 240)
            if detail:
                return (
                    f"[Tool Run] 실행 실패: {failed.get('command')} "
                    f"(exit={failed.get('exit_code')}) - {detail}"
                )
            return f"[Tool Run] 실행 실패: {failed.get('command')} (exit={failed.get('exit_code')})"
        return f"[Tool Run] 실행 실패: {result.get('error')}"

    command_preview = ', '.join(item.get('command') for item in executed[:3] if item.get('command'))
    if len(executed) > 3:
        command_preview = f'{command_preview}, ... (+{len(executed) - 3})'
    if command_preview:
        return f'[Tool Run] 실행 완료 ({len(executed)}개): {command_preview}'
    return f'[Tool Run] 실행 완료 ({len(executed)}개)'


def _format_patch_apply_note(result):
    if not isinstance(result, dict) or not result.get('detected'):
        return ''

    files = result.get('files') if isinstance(result.get('files'), list) else []
    sanitize_notes = []
    if result.get('normalized_headers'):
        sanitize_notes.append('헤더 자동 보정')
    if result.get('sanitized_hunks'):
        sanitize_notes.append('new/delete hunk 자동 보정')
    if result.get('recounted_hunks'):
        sanitize_notes.append('hunk header 자동 보정')
    sanitized_text = f" ({', '.join(sanitize_notes)})" if sanitize_notes else ''
    if result.get('applied'):
        status_text = '이미 적용된 변경으로 처리' if result.get('already_applied') else '적용 완료'
        file_text = ', '.join(files[:6])
        if len(files) > 6:
            file_text = f'{file_text}, ... (+{len(files) - 6})'
        if file_text:
            return f'[Patch Apply] {status_text}{sanitized_text}: {file_text}'
        return f'[Patch Apply] {status_text}{sanitized_text}'

    error_text = str(result.get('error') or '').strip() or '원인을 확인할 수 없습니다.'
    return f'[Patch Apply] 적용 실패{sanitized_text}: {error_text}'


def finalize_assistant_output(content, apply_side_effects=True):
    text = str(content or '').strip()
    if not text:
        return text, None

    if not apply_side_effects:
        return text, {
            'auto_actions': {
                'enabled': False,
                'reason': 'plan_mode',
            }
        }

    metadata = {}
    notes = []

    patch_text = _extract_patch_text_from_response(text)
    patch_result = None
    if patch_text:
        with _PATCH_APPLY_LOCK:
            patch_result = _apply_patch_text_to_workspace(patch_text)
        metadata['patch_apply'] = patch_result
        patch_note = _format_patch_apply_note(patch_result)
        if patch_note:
            notes.append(patch_note)

    tool_commands = _extract_tool_commands_from_response(text)
    if tool_commands:
        if patch_result and not patch_result.get('applied'):
            tool_result = {
                'detected': True,
                'executed': [],
                'error': 'Patch Apply 실패로 실행을 생략했습니다.',
                'skipped': True,
            }
        else:
            tool_result = _execute_tool_commands_in_workspace(tool_commands)
        metadata['tool_run'] = tool_result
        tool_note = _format_tool_run_note(tool_result)
        if tool_note:
            notes.append(tool_note)

    if notes:
        text = f"{text}\n\n" + '\n'.join(notes)

    return text, (metadata or None)


def _format_context_message(message, index):
    role = _normalize_context_role((message or {}).get('role'), fallback='user')
    content = _normalize_context_text((message or {}).get('content'))
    if role == 'assistant':
        content = _strip_context_auto_notes(content)
    if not content:
        content = '(empty)'
    max_chars = _CONTEXT_MESSAGE_ROLE_MAX_CHARS.get(role, _CONTEXT_MESSAGE_DEFAULT_MAX_CHARS)
    content = _clip_text(content, max_chars)
    return '\n'.join(
        [
            f'<message index="{index}" role="{role}">',
            content,
            '</message>',
        ]
    )


def _build_memory_lines(messages, max_chars):
    if max_chars <= 0:
        return []
    lines = []
    for index, message in enumerate(messages, start=1):
        role_key = _normalize_context_role((message or {}).get('role'), fallback='user')
        role = _ROLE_LABELS.get(role_key, 'User')
        content = _single_line_text((message or {}).get('content'))
        if not content:
            continue
        line_max_chars = _CONTEXT_MEMORY_ROLE_MAX_CHARS.get(role_key, _CONTEXT_MEMORY_DEFAULT_MAX_CHARS)
        lines.append(f"{index}. {role}: {_clip_text(content, line_max_chars)}")
    if not lines:
        return []

    max_lines = 24
    if len(lines) > max_lines:
        keep_head = 10
        keep_tail = max_lines - keep_head - 1
        omitted = len(lines) - keep_head - keep_tail
        lines = lines[:keep_head] + [f"... ({omitted} earlier messages omitted)"] + lines[-keep_tail:]

    trimmed = list(lines)
    while trimmed and len('\n'.join(f"- {line}" for line in trimmed)) > max_chars:
        trimmed.pop(0)
    return trimmed


def _build_recent_context_entries(messages, max_chars):
    if max_chars <= 0 or not isinstance(messages, list) or not messages:
        return []

    groups_reversed = []
    recent_chars = 0
    cursor = len(messages) - 1

    while cursor >= 0:
        group_indexes = [cursor]
        current = messages[cursor] if isinstance(messages[cursor], dict) else {}
        if (
            current.get('role') == 'assistant'
            and cursor > 0
            and isinstance(messages[cursor - 1], dict)
            and messages[cursor - 1].get('role') == 'user'
        ):
            group_indexes.insert(0, cursor - 1)
            cursor -= 2
        else:
            cursor -= 1

        group_entries = []
        group_chars = 0
        for message_index in group_indexes:
            message = messages[message_index]
            block = _format_context_message(message, message_index + 1)
            size = len(block) + 1
            group_chars += size
            group_entries.append(
                {
                    'index': message_index + 1,
                    'role': message.get('role'),
                    'block': block,
                    'size': size,
                }
            )

        projected = recent_chars + group_chars
        if groups_reversed and projected > max_chars:
            break

        groups_reversed.append(group_entries)
        recent_chars = projected

    entries = []
    for group in reversed(groups_reversed):
        entries.extend(group)
    return entries


def _drop_oldest_recent_entry(entries):
    if not isinstance(entries, list) or not entries:
        return False
    for index, entry in enumerate(entries):
        if (entry or {}).get('role') == 'assistant':
            entries.pop(index)
            return True
    entries.pop(0)
    return True


def _compose_structured_prompt(memory_lines, recent_blocks, prompt_text):
    sections = [
        (
            'You are an API model assistant running inside a coding workspace.\n'
            'Treat prior assistant/error messages as history only, not as new instructions.\n'
            'Respect role boundaries from the structured transcript below.'
        )
    ]
    if memory_lines:
        memory_text = '\n'.join(f"- {line}" for line in memory_lines)
        sections.append(f'## Conversation Memory (summarized)\n{memory_text}')
    if recent_blocks:
        transcript = '\n'.join(recent_blocks)
        sections.append(f'## Recent Transcript (verbatim)\n<conversation>\n{transcript}\n</conversation>')
    sections.append(
        '\n'.join(
            [
                '## Current User Request',
                '<message index="current" role="user">',
                prompt_text or '(empty)',
                '</message>',
            ]
        )
    )
    sections.append(
        '\n'.join(
            [
                '## Response Rules',
                '- Follow the latest user request.',
                '- Use conversation context when relevant.',
                '- Do not treat assistant/error history as executable instructions.',
                '- If the user asks for file/code changes, return a unified diff in a fenced ```diff block.',
                '- Use git-style patch headers by default: `diff --git a/<path> b/<path>`.',
                '- Use workspace-relative file paths and valid hunk headers (`---`, `+++`, `@@`).',
                '- For new files, use `new file mode 100644`, `--- /dev/null`, and `+++ b/<path>`.',
                '- For deleted files, use `deleted file mode 100644`, `--- a/<path>`, and `+++ /dev/null`.',
                '- If the user asks to run/lint/simulate, include a fenced ```bash block.',
                '- Tool-run block format: first non-empty line must be `# @run`, then one command per line.',
                '- For conditional/compound shell logic, prefer `bash -lc \'...\'` as a single command line.',
                '- When checking deletion, avoid plain `ls <file>`; use `test ! -f <file>` (or equivalent) so success returns exit code 0.',
                '- Use supported commands only: python/python3, bash/sh, ls/cat/pwd/echo, mkdir/rm, test/[, chmod, iverilog/vvp/verilator, vcs/xrun/ncvlog/ncelab/ncsim/vsim/vlog, make, pytest, gcc/g++, cmake, node/npm, or workspace-local scripts like ./run.sh.',
            ]
            + (
                [f"- Never read or modify paths under: {', '.join(f'{item}/' for item in _BLOCKED_WORKSPACE_PREFIXES)}"]
                if _BLOCKED_WORKSPACE_PREFIXES
                else []
            )
        )
    )
    return '\n\n'.join(section for section in sections if section).strip()


def build_model_prompt(messages, prompt):
    if not isinstance(messages, list):
        messages = []

    max_chars = max(1200, int(MODEL_CONTEXT_MAX_CHARS))
    prompt_text = _clip_text(_normalize_context_text(prompt), max(600, int(max_chars * 0.34)))

    normalized_messages = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = _normalize_context_role(message.get('role'), fallback='user')
        content = _normalize_context_text(message.get('content'))
        if role == 'assistant':
            content = _strip_context_auto_notes(content)
        if not content:
            continue
        normalized_messages.append({'role': role, 'content': content})

    recent_budget = max(1000, int(max_chars * 0.58))
    recent_entries = _build_recent_context_entries(normalized_messages, recent_budget)
    recent_blocks = [entry.get('block') for entry in recent_entries if entry.get('block')]
    recent_indexes = {entry.get('index') for entry in recent_entries if entry.get('index')}
    omitted_messages = [
        message
        for index, message in enumerate(normalized_messages, start=1)
        if index not in recent_indexes
    ]
    summary_budget = max(420, int(max_chars * 0.28))
    memory_lines = _build_memory_lines(omitted_messages, summary_budget)

    structured_prompt = _compose_structured_prompt(memory_lines, recent_blocks, prompt_text)
    if len(structured_prompt) <= max_chars:
        return structured_prompt

    while len(structured_prompt) > max_chars and memory_lines:
        memory_lines = memory_lines[1:]
        structured_prompt = _compose_structured_prompt(memory_lines, recent_blocks, prompt_text)
    while len(structured_prompt) > max_chars and recent_entries:
        _drop_oldest_recent_entry(recent_entries)
        recent_blocks = [entry.get('block') for entry in recent_entries if entry.get('block')]
        structured_prompt = _compose_structured_prompt(memory_lines, recent_blocks, prompt_text)
    if len(structured_prompt) <= max_chars:
        return structured_prompt

    prompt_text = _clip_text(prompt_text, max(200, max_chars // 4))
    structured_prompt = _compose_structured_prompt(memory_lines, recent_blocks, prompt_text)
    if len(structured_prompt) <= max_chars:
        return structured_prompt
    return structured_prompt[-max_chars:]


def _normalize_model_name(provider, value):
    normalized_provider = _normalize_provider_name(provider)
    raw = str(value or '').strip()
    if not raw:
        raw = _default_model_for_provider(normalized_provider)

    if normalized_provider == 'gemini':
        if raw.startswith('models/'):
            raw = raw[len('models/'):]
        alias_key = raw.lower()
        alias_map = {
            'auto': MODEL_GEMINI_DEFAULT_MODEL,
            'flash': 'gemini-flash-latest',
            'flash-lite': 'gemini-flash-lite-latest',
            'pro': 'gemini-pro-latest',
        }
        return alias_map.get(alias_key, raw)

    alias_key = raw.lower()
    if normalized_provider == 'dtgpt':
        alias_map = {
            'auto': MODEL_DTGPT_DEFAULT_MODEL,
            'k2.5': 'Kimi-K2.5',
            'kimi-k2.5': 'Kimi-K2.5',
            'glm4.7': 'GLM4.7',
            'oss-120b': 'openai/gpt-oss-120b',
            'gpt-oss-120b': 'openai/gpt-oss-120b',
        }
        return alias_map.get(alias_key, raw)

    if normalized_provider == 'claude':
        alias_map = {
            'auto': MODEL_CLAUDE_DEFAULT_MODEL,
            'opus': 'claude-opus-4-6',
            'sonnet': 'claude-sonnet-4-6',
            'haiku': 'claude-haiku-4-5-20251001',
            'claude-opus': 'claude-opus-4-6',
            'claude-sonnet': 'claude-sonnet-4-6',
            'claude-haiku': 'claude-haiku-4-5-20251001',
        }
        return alias_map.get(alias_key, raw)

    return raw


def _build_generation_config():
    return {'temperature': 0.2}


def _provider_label(provider):
    normalized = _normalize_provider_name(provider)
    if normalized == 'claude':
        return 'Claude CLI'
    if normalized in _OPENAI_COMPATIBLE_PROVIDERS:
        return 'Samsung DTGPT API'
    return 'Gemini API'


def _provider_api_key(provider):
    normalized = _normalize_provider_name(provider)
    if normalized == 'claude':
        return ''
    configured_key = ''
    fallback_env_name = ''
    if normalized in _OPENAI_COMPATIBLE_PROVIDERS:
        configured_key = MODEL_DTGPT_API_KEY
        fallback_env_name = MODEL_DTGPT_API_KEY_ENV
    else:
        configured_key = MODEL_GEMINI_API_KEY

    resolved = _resolve_env_reference(str(configured_key or '').strip())
    normalized_key = str(resolved or '').strip()
    if normalized_key:
        return normalized_key
    if fallback_env_name:
        from_env = str(os.getenv(fallback_env_name) or '').strip()
        if from_env:
            return from_env
    return ''


def _provider_api_key_header(provider):
    normalized = _normalize_provider_name(provider)
    if normalized in _OPENAI_COMPATIBLE_PROVIDERS:
        header_name = str(_resolve_env_reference(str(MODEL_DTGPT_API_KEY_HEADER or '').strip()) or '').strip()
        return header_name or 'Authorization'
    return ''


def _provider_api_key_prefix(provider):
    normalized = _normalize_provider_name(provider)
    if normalized in _OPENAI_COMPATIBLE_PROVIDERS:
        key_prefix = str(_resolve_env_reference(str(MODEL_DTGPT_API_KEY_PREFIX or '').strip()) or '').strip()
        return key_prefix or 'Bearer'
    return ''


def _provider_api_base_url(provider):
    normalized = _normalize_provider_name(provider)
    if normalized == 'claude':
        return ''
    base_url = ''
    if normalized in _OPENAI_COMPATIBLE_PROVIDERS:
        base_url = MODEL_DTGPT_API_BASE_URL
    else:
        base_url = MODEL_GEMINI_API_BASE_URL
    return str(_resolve_env_reference(str(base_url or '').strip()) or '').strip()


def _has_valid_api_key(provider):
    normalized = _normalize_provider_name(provider)
    if normalized == 'claude':
        return True
    key = str(_provider_api_key(provider) or '').strip()
    if not key:
        return False
    return not _is_placeholder_api_key(key)


def _resolve_env_reference(value):
    token = str(value or '').strip()
    if not token:
        return token
    match = _ENV_REFERENCE_PATTERN.match(token)
    if match:
        return os.environ.get(match.group(1), '')
    if token.lower().startswith('env:'):
        env_name = token[4:].strip()
        if env_name:
            return os.environ.get(env_name, '')
    return token


def _is_placeholder_api_key(value):
    token = str(value or '').strip()
    if not token:
        return False
    if _ENV_REFERENCE_PATTERN.match(token):
        return True
    if token.lower().startswith('env:'):
        return True
    if token.upper().startswith('YOUR_'):
        return True
    return False


def _build_auth_header_value(api_key, key_prefix='Bearer'):
    normalized_key = str(api_key or '').strip()
    normalized_prefix = str(key_prefix or '').strip()
    if not normalized_key:
        return ''
    if not normalized_prefix:
        return normalized_key
    prefix_with_space = f'{normalized_prefix} '
    if normalized_key.lower().startswith(prefix_with_space.lower()):
        return normalized_key
    return f'{normalized_prefix} {normalized_key}'.strip()


def _provider_api_base_urls(provider):
    normalized = _normalize_provider_name(provider)
    candidates = []
    primary = str(_provider_api_base_url(normalized) or '').strip()
    if primary:
        candidates.append(primary)

    if normalized in _OPENAI_COMPATIBLE_PROVIDERS:
        for item in MODEL_DTGPT_API_BASE_URLS:
            token = str(_resolve_env_reference(str(item or '').strip()) or '').strip()
            if token:
                candidates.append(token)
        if any('dtgpt.samsungds.net' in item.lower() for item in candidates):
            candidates.extend(_known_dtgpt_base_urls())
        if not _is_windows_platform():
            candidates = [item for item in candidates if not _is_dtgpt_cloud_endpoint(item)]
            if not candidates:
                candidates.extend(_known_dtgpt_base_urls())
        candidates = sorted(candidates, key=_dtgpt_endpoint_rank)

    deduped = []
    seen = set()
    for item in candidates:
        normalized_item = item.rstrip('/')
        if not normalized_item:
            continue
        key = normalized_item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized_item)
    return deduped


def _extract_api_error_message(payload):
    if not isinstance(payload, dict):
        return ''
    error_payload = payload.get('error')
    if isinstance(error_payload, dict):
        message = error_payload.get('message')
        if isinstance(message, str) and message.strip():
            return message.strip()
    message = payload.get('message')
    if isinstance(message, str) and message.strip():
        return message.strip()
    return ''


def _read_http_error_message(exc, provider):
    label = _provider_label(provider)
    try:
        raw = exc.read()
    except Exception:
        raw = b''
    if not raw:
        return f'{label} 요청이 실패했습니다. (HTTP {getattr(exc, "code", "unknown")})'
    try:
        payload = json.loads(raw.decode('utf-8', errors='replace'))
    except Exception:
        payload = {}
    message = _extract_api_error_message(payload)
    if message:
        return message
    text = raw.decode('utf-8', errors='replace').strip()
    if text:
        return text
    return f'{label} 요청이 실패했습니다. (HTTP {getattr(exc, "code", "unknown")})'


def _build_json_request(url, payload, headers=None):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    return urllib.request.Request(url=url, data=body, headers=headers or {}, method='POST')


def _build_gemini_api_url(model, stream=False):
    escaped_model = urllib.parse.quote(model, safe='-._~')
    endpoint = 'streamGenerateContent' if stream else 'generateContent'
    gemini_key = _provider_api_key('gemini')
    query = f"key={urllib.parse.quote_plus(gemini_key)}"
    if stream:
        query = f'{query}&alt=sse'
    return f'{MODEL_GEMINI_API_BASE_URL}/models/{escaped_model}:{endpoint}?{query}'


def _build_gemini_payload(prompt):
    return {
        'contents': [
            {
                'role': 'user',
                'parts': [{'text': str(prompt or '')}],
            }
        ],
        'generationConfig': _build_generation_config(),
    }


def _build_openai_compatible_api_urls(provider):
    endpoints = []
    for base_url in _provider_api_base_urls(provider):
        normalized = base_url.rstrip('/')
        if normalized.lower().endswith('/chat/completions'):
            endpoints.append(normalized)
        else:
            endpoints.append(f'{normalized}/chat/completions')
    return endpoints


def _build_openai_payload(prompt, model, stream=False):
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': str(prompt or '')}],
        'temperature': _build_generation_config()['temperature'],
    }
    if stream:
        payload['stream'] = True
        payload['stream_options'] = {'include_usage': True}
    return payload


def _extract_gemini_response_text(payload):
    if isinstance(payload, list):
        return ''.join(_extract_gemini_response_text(item) for item in payload)
    if not isinstance(payload, dict):
        return ''
    candidates = payload.get('candidates')
    if not isinstance(candidates, list):
        return ''
    chunks = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get('content')
        if not isinstance(content, dict):
            continue
        parts = content.get('parts')
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get('text')
            if isinstance(text, str) and text:
                chunks.append(text)
    return ''.join(chunks)


def _extract_openai_content_fragment(fragment):
    if isinstance(fragment, str):
        return fragment
    if isinstance(fragment, list):
        chunks = []
        for item in fragment:
            if not isinstance(item, dict):
                continue
            text = item.get('text')
            if isinstance(text, str) and text:
                chunks.append(text)
        return ''.join(chunks)
    return ''


def _extract_openai_response_text(payload):
    if not isinstance(payload, dict):
        return ''
    choices = payload.get('choices')
    if not isinstance(choices, list):
        return ''
    chunks = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get('message')
        if not isinstance(message, dict):
            continue
        content = _extract_openai_content_fragment(message.get('content'))
        if content:
            chunks.append(content)
    return ''.join(chunks)


def _extract_openai_stream_delta(payload):
    if not isinstance(payload, dict):
        return ''
    choices = payload.get('choices')
    if not isinstance(choices, list):
        return ''
    chunks = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get('delta')
        if not isinstance(delta, dict):
            continue
        content = _extract_openai_content_fragment(delta.get('content'))
        if content:
            chunks.append(content)
    return ''.join(chunks)


def _extract_openai_usage(payload):
    if not isinstance(payload, dict):
        return None
    usage = payload.get('usage')
    return usage if isinstance(usage, dict) else None


def _execute_gemini_prompt(prompt, model):
    if not _has_valid_api_key('gemini'):
        return None, 'Gemini API 키가 설정되지 않았습니다.'

    payload = _build_gemini_payload(prompt)
    url = _build_gemini_api_url(model, stream=False)
    request = _build_json_request(url, payload, headers={'Content-Type': 'application/json'})
    timeout_seconds = max(1, int(min(MODEL_EXEC_TIMEOUT_SECONDS, MODEL_API_TIMEOUT_SECONDS)))

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return None, _read_http_error_message(exc, 'gemini')
    except urllib.error.URLError as exc:
        return None, f'Gemini API 연결에 실패했습니다: {exc.reason}'
    except TimeoutError:
        return None, 'Gemini API 응답 시간이 초과되었습니다.'
    except Exception as exc:
        return None, f'Gemini API 실행 중 오류가 발생했습니다: {exc}'

    try:
        payload = json.loads(raw.decode('utf-8', errors='replace'))
    except Exception:
        return None, 'Gemini API 응답을 파싱하지 못했습니다.'

    text = _extract_gemini_response_text(payload).strip()
    usage_metadata = _extract_gemini_usage_metadata(payload)
    if usage_metadata:
        _update_usage_summary_from_gemini_metadata('gemini', usage_metadata)

    if text:
        return text, None

    error_text = _extract_api_error_message(payload)
    if error_text:
        return None, error_text
    return None, 'Gemini API 실행에 실패했습니다.'


def _execute_openai_compatible_prompt(provider, prompt, model):
    normalized_provider = _normalize_provider_name(provider)
    label = _provider_label(normalized_provider)
    api_key = _provider_api_key(normalized_provider)

    if not _has_valid_api_key(normalized_provider):
        return None, f'{label} 키가 설정되지 않았습니다.'

    endpoints = _build_openai_compatible_api_urls(normalized_provider)
    if not endpoints:
        return None, f'{label} API 주소가 비어 있습니다.'

    payload = _build_openai_payload(prompt, model, stream=False)
    auth_header = _provider_api_key_header(normalized_provider)
    auth_prefix = _provider_api_key_prefix(normalized_provider)
    auth_value = _build_auth_header_value(api_key, auth_prefix)
    headers = {'Content-Type': 'application/json'}
    if auth_value and auth_header:
        headers[auth_header] = auth_value

    timeout_seconds = max(1, int(min(MODEL_EXEC_TIMEOUT_SECONDS, MODEL_API_TIMEOUT_SECONDS)))
    last_error = None

    for endpoint in endpoints:
        request = _build_json_request(endpoint, payload, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            message = _read_http_error_message(exc, normalized_provider)
            status_code = getattr(exc, 'code', None)
            if status_code in {400, 401, 403, 404, 415, 422}:
                return None, message
            last_error = f'{message} (endpoint: {endpoint})'
            continue
        except urllib.error.URLError as exc:
            last_error = f'{label} 연결에 실패했습니다: {exc.reason} (endpoint: {endpoint})'
            continue
        except TimeoutError:
            last_error = f'{label} 응답 시간이 초과되었습니다. (endpoint: {endpoint})'
            continue
        except Exception as exc:
            last_error = f'{label} 실행 중 오류가 발생했습니다: {exc} (endpoint: {endpoint})'
            continue

        try:
            response_payload = json.loads(raw.decode('utf-8', errors='replace'))
        except Exception:
            last_error = f'{label} 응답을 파싱하지 못했습니다. (endpoint: {endpoint})'
            continue

        text = _extract_openai_response_text(response_payload).strip()
        usage_payload = _extract_openai_usage(response_payload)
        if usage_payload:
            _update_usage_summary_from_openai_usage(normalized_provider, usage_payload)

        if text:
            return text, None

        error_text = _extract_api_error_message(response_payload)
        if error_text:
            return None, error_text
        last_error = f'{label} 실행에 실패했습니다. (endpoint: {endpoint})'

    return None, last_error or f'{label} 실행에 실패했습니다.'


def _empty_claude_cli_capabilities():
    return {
        'has_print': False,
        'has_output_format': False,
        'has_stream_json': False,
        'has_include_partial_messages': False,
        'has_no_session_persistence': False,
        'has_model': False,
        'has_effort': False,
        'has_permission_mode': False,
        'has_tools': False,
        'has_verbose': False,
        'has_add_dir': False,
    }


def _detect_claude_cli_capabilities():
    capabilities = _empty_claude_cli_capabilities()
    timeout_seconds = max(3, min(15, int(MODEL_EXEC_TIMEOUT_SECONDS)))
    try:
        result = subprocess.run(
            ['claude', '--help'],
            cwd=str(WORKSPACE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception:
        return capabilities

    help_text = '\n'.join(
        part for part in ((result.stdout or '').strip(), (result.stderr or '').strip()) if part
    )
    if not help_text:
        return capabilities

    capabilities['has_print'] = '--print' in help_text or '-p,' in help_text
    capabilities['has_output_format'] = '--output-format' in help_text
    capabilities['has_stream_json'] = 'stream-json' in help_text and capabilities['has_output_format']
    capabilities['has_include_partial_messages'] = '--include-partial-messages' in help_text
    capabilities['has_no_session_persistence'] = '--no-session-persistence' in help_text
    capabilities['has_model'] = '--model' in help_text
    capabilities['has_effort'] = '--effort' in help_text
    capabilities['has_permission_mode'] = '--permission-mode' in help_text
    capabilities['has_tools'] = '--tools' in help_text
    capabilities['has_verbose'] = '--verbose' in help_text
    capabilities['has_add_dir'] = '--add-dir' in help_text
    return capabilities


def _get_claude_cli_capabilities(force_refresh=False):
    global _CLAUDE_CLI_CAPABILITIES
    with _CLAUDE_CLI_CAPABILITIES_LOCK:
        if force_refresh or not isinstance(_CLAUDE_CLI_CAPABILITIES, dict):
            _CLAUDE_CLI_CAPABILITIES = _detect_claude_cli_capabilities()
        return dict(_CLAUDE_CLI_CAPABILITIES)


def _normalize_existing_directory(value):
    text = str(value or '').strip()
    if not text:
        return None
    try:
        path = Path(text).expanduser().resolve(strict=False)
    except Exception:
        return None
    if not path.exists() or not path.is_dir():
        return None
    return path


def _resolve_claude_execution_paths(execution_cwd=None, allowed_dirs=None):
    workspace_root = _normalize_existing_directory(WORKSPACE_DIR)
    if workspace_root is None:
        workspace_root = WORKSPACE_DIR.resolve(strict=False)
        try:
            workspace_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        workspace_root = _normalize_existing_directory(workspace_root)

    server_root = _normalize_existing_directory(Path.cwd())
    cwd_path = _normalize_existing_directory(execution_cwd)
    if cwd_path is None:
        cwd_path = workspace_root or server_root

    normalized_dirs = []
    for candidate in (workspace_root, server_root, cwd_path):
        directory = _normalize_existing_directory(candidate)
        if directory is None:
            continue
        text = str(directory)
        if text and text not in normalized_dirs:
            normalized_dirs.append(text)

    if isinstance(allowed_dirs, (list, tuple, set)):
        for candidate in allowed_dirs:
            directory = _normalize_existing_directory(candidate)
            if directory is None:
                continue
            text = str(directory)
            if text and text not in normalized_dirs:
                normalized_dirs.append(text)

    normalized_cwd = _normalize_existing_directory(cwd_path)
    if normalized_cwd is None:
        if normalized_dirs:
            normalized_cwd = Path(normalized_dirs[0])
        else:
            normalized_cwd = _normalize_existing_directory(Path.cwd()) or Path.cwd().resolve(strict=False)

    return str(normalized_cwd), normalized_dirs


def _claude_command_output_format(cmd):
    if not isinstance(cmd, list):
        return ''
    for index, token in enumerate(cmd):
        if token != '--output-format':
            continue
        if index + 1 < len(cmd):
            return str(cmd[index + 1] or '').strip().lower()
        return ''
    return ''


def _extract_claude_text_fragment(payload):
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return ''.join(_extract_claude_text_fragment(item) for item in payload)
    if not isinstance(payload, dict):
        return ''

    for key in ('text', 'result', 'response', 'completion', 'output'):
        value = payload.get(key)
        if isinstance(value, str):
            return value

    for key in ('delta', 'content', 'message', 'content_block', 'contentBlock'):
        value = payload.get(key)
        text = _extract_claude_text_fragment(value)
        if text:
            return text

    return ''


def _extract_claude_usage(payload):
    if not isinstance(payload, dict):
        return None
    usage = payload.get('usage')
    if isinstance(usage, dict):
        return usage
    message = payload.get('message')
    if isinstance(message, dict):
        usage = message.get('usage')
        if isinstance(usage, dict):
            return usage
    return None


def _update_usage_summary_from_claude_usage(usage_payload):
    if not isinstance(usage_payload, dict):
        return
    input_tokens = _coerce_usage_field(usage_payload, 'input_tokens')
    output_tokens = _coerce_usage_field(usage_payload, 'output_tokens')
    total_tokens = _coerce_usage_field(usage_payload, 'total_tokens')
    reasoning_tokens = _coerce_usage_field(usage_payload, 'thinking_tokens', 'reasoning_tokens')
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    _update_usage_summary_tokens('claude', input_tokens, output_tokens, total_tokens, reasoning_tokens)


def _consume_claude_stream_payload(stream_id, state_holder, payload):
    if not isinstance(state_holder, dict):
        state_holder = {}

    if isinstance(payload, dict):
        payload_type = str(payload.get('type') or '').strip().lower()
        nested_event = payload.get('event')
        if payload_type == 'stream_event' and isinstance(nested_event, dict):
            payload = nested_event

    usage_payload = _extract_claude_usage(payload)
    if usage_payload:
        state_holder['claude_usage'] = usage_payload

    event_type = ''
    if isinstance(payload, dict):
        event_type = str(payload.get('type') or '').strip().lower()
        error_payload = payload.get('error')
        if isinstance(error_payload, dict):
            error_text = str(error_payload.get('message') or '').strip()
        else:
            error_text = str(error_payload or '').strip()
        if error_text and event_type in {'error', 'exception'}:
            state_holder['stream_error'] = error_text
            _append_stream_chunk(stream_id, 'error', f'{error_text}\n')
            return

    delta_text = ''
    if event_type.endswith('delta') and isinstance(payload, dict):
        delta_text = _extract_claude_text_fragment(payload.get('delta'))
        if not delta_text:
            delta_text = _extract_claude_text_fragment(payload)
        if delta_text:
            state_holder['rendered_text'] = f"{state_holder.get('rendered_text', '')}{delta_text}"
            _append_stream_chunk(stream_id, 'output', delta_text)
            return

    full_text = _extract_claude_text_fragment(payload)
    if not full_text:
        return

    previous = state_holder.get('rendered_text', '')
    delta_text = ''
    if full_text.startswith(previous):
        delta_text = full_text[len(previous):]
        state_holder['rendered_text'] = full_text
    elif not previous:
        delta_text = full_text
        state_holder['rendered_text'] = full_text

    if delta_text:
        _append_stream_chunk(stream_id, 'output', delta_text)


def _consume_claude_stream_line(stream_id, state_holder, line):
    text = str(line or '').strip()
    if not text:
        return
    try:
        payload = json.loads(text)
    except Exception:
        _append_stream_chunk(stream_id, 'output', line)
        return
    _consume_claude_stream_payload(stream_id, state_holder, payload)


def _stream_json_reader(stream_id, pipe, state_holder, line_handler):
    try:
        for line in iter(pipe.readline, ''):
            line_handler(stream_id, state_holder, line)
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _build_claude_command(
        prompt,
        model=None,
        effort=None,
        stream=False,
        plan_mode=False,
        allowed_dirs=None):
    capabilities = _get_claude_cli_capabilities()
    cmd = ['claude']
    if capabilities.get('has_print'):
        cmd.append('--print')
    else:
        cmd.append('-p')

    if capabilities.get('has_output_format'):
        if stream and capabilities.get('has_stream_json'):
            if capabilities.get('has_verbose'):
                cmd.append('--verbose')
            cmd.extend(['--output-format', 'stream-json'])
            if capabilities.get('has_include_partial_messages'):
                cmd.append('--include-partial-messages')
        else:
            cmd.extend(['--output-format', 'json'])

    if capabilities.get('has_no_session_persistence'):
        cmd.append('--no-session-persistence')
    if capabilities.get('has_model') and str(model or '').strip():
        cmd.extend(['--model', str(model).strip()])
    normalized_effort = _normalize_reasoning_effort(effort)
    if capabilities.get('has_effort') and normalized_effort:
        cmd.extend(['--effort', normalized_effort])
    if capabilities.get('has_permission_mode'):
        cmd.extend(['--permission-mode', 'plan' if plan_mode else 'bypassPermissions'])
    if capabilities.get('has_add_dir') and isinstance(allowed_dirs, (list, tuple)):
        directories = [str(item).strip() for item in allowed_dirs if str(item).strip()]
        if directories:
            cmd.append('--add-dir')
            cmd.extend(directories)

    # Terminate option parsing before the prompt.
    cmd.append('--')
    cmd.append(str(prompt or ''))
    return cmd


def _execute_claude_prompt(
        prompt,
        model=None,
        effort=None,
        plan_mode=False,
        execution_cwd=None,
        allowed_dirs=None):
    cwd_path, normalized_allowed_dirs = _resolve_claude_execution_paths(
        execution_cwd=execution_cwd,
        allowed_dirs=allowed_dirs,
    )
    cmd = _build_claude_command(
        prompt,
        model=model,
        effort=effort,
        plan_mode=plan_mode,
        allowed_dirs=normalized_allowed_dirs,
    )
    timeout_seconds = max(1, int(MODEL_EXEC_TIMEOUT_SECONDS))
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd_path,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return None, 'claude 명령을 찾을 수 없습니다.'
    except subprocess.TimeoutExpired:
        return None, 'Claude CLI 응답 시간이 초과되었습니다.'
    except Exception as exc:
        return None, f'Claude CLI 실행 중 오류가 발생했습니다: {exc}'

    output_text = (result.stdout or '').strip()
    error_text = (result.stderr or '').strip()

    if result.returncode != 0:
        return None, error_text or output_text or 'Claude CLI 실행에 실패했습니다.'
    if _claude_command_output_format(cmd) == 'json' and output_text:
        try:
            payload = json.loads(output_text)
        except Exception:
            payload = None
        if payload is not None:
            usage_payload = _extract_claude_usage(payload)
            if usage_payload:
                _update_usage_summary_from_claude_usage(usage_payload)
            parsed_text = _extract_claude_text_fragment(payload).strip()
            if parsed_text:
                return parsed_text, None
    if output_text:
        return output_text, None
    if error_text:
        return None, error_text
    return None, 'Claude CLI 응답이 비어 있습니다.'


def execute_model_prompt(
        prompt,
        provider_override=None,
        model_override=None,
        reasoning_override=None,
        plan_mode=False,
        execution_cwd=None,
        allowed_dirs=None):
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    base_provider = _normalize_provider_name(settings.get('provider'))
    provider = (
        _normalize_provider_name(provider_override)
        if provider_override is not None
        else base_provider
    )
    if model_override is None:
        if provider == base_provider:
            model = _normalize_model_name(provider, settings.get('model'))
        else:
            model = _default_model_for_provider(provider)
    else:
        model = _normalize_model_name(provider, model_override)
    reasoning_effort = _normalize_reasoning_effort(reasoning_override)
    if reasoning_effort is None:
        if plan_mode:
            reasoning_effort = _normalize_reasoning_effort(settings.get('plan_mode_reasoning_effort'))
        if reasoning_effort is None:
            reasoning_effort = _normalize_reasoning_effort(settings.get('reasoning_effort'))
        if reasoning_effort is None:
            reasoning_effort = _normalize_reasoning_effort(MODEL_DEFAULT_REASONING_EFFORT)

    if provider == 'claude':
        return _execute_claude_prompt(
            prompt,
            model=model,
            effort=reasoning_effort,
            plan_mode=plan_mode,
            execution_cwd=execution_cwd,
            allowed_dirs=allowed_dirs,
        )
    if provider in _OPENAI_COMPATIBLE_PROVIDERS:
        return _execute_openai_compatible_prompt(provider, prompt, model)
    return _execute_gemini_prompt(prompt, model)


def _coerce_positive_seconds(value, default_value, minimum=0.01):
    numeric = _coerce_float(value)
    if numeric is None:
        numeric = float(default_value)
    if numeric < minimum:
        numeric = minimum
    return float(numeric)


def _iso_timestamp_from_epoch(value):
    numeric = _coerce_float(value)
    if numeric is None:
        return None
    return normalize_timestamp(datetime.fromtimestamp(numeric))


def _epoch_to_millis(value):
    numeric = _coerce_float(value)
    if numeric is None:
        return None
    return int(numeric * 1000)


def _build_stream_message_metadata(started_at, completed_at, saved_at, finalize_reason):
    metadata = {}
    duration_ms = None
    if isinstance(started_at, (int, float)) and isinstance(completed_at, (int, float)):
        duration_ms = max(0, int((completed_at - started_at) * 1000))
        metadata['duration_ms'] = duration_ms

    started_iso = _iso_timestamp_from_epoch(started_at)
    completed_iso = _iso_timestamp_from_epoch(completed_at)
    saved_iso = _iso_timestamp_from_epoch(saved_at)

    if started_iso:
        metadata['started_at'] = started_iso
    if completed_iso:
        metadata['completed_at'] = completed_iso
    if saved_iso:
        metadata['saved_at'] = saved_iso
    if finalize_reason:
        metadata['finalize_reason'] = str(finalize_reason)
    if isinstance(completed_at, (int, float)) and isinstance(saved_at, (int, float)):
        metadata['finalize_lag_ms'] = max(0, int((saved_at - completed_at) * 1000))

    return metadata or None


def _stream_reader(stream_id, pipe, key):
    try:
        for line in iter(pipe.readline, ''):
            _append_stream_chunk(stream_id, key, line)
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _terminate_stream_process(process, grace_seconds):
    if process is None:
        return None
    try:
        if process.poll() is not None:
            return process.poll()
    except Exception:
        return None

    try:
        process.terminate()
    except Exception:
        pass
    try:
        process.wait(timeout=grace_seconds)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=grace_seconds)
        except Exception:
            pass
    try:
        return process.poll()
    except Exception:
        return None


def _append_stream_chunk(stream_id, key, chunk):
    if not chunk:
        return
    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if not stream:
            return
        if stream.get('cancelled'):
            return
        stream[key] += chunk
        now = time.time()
        stream['updated_at'] = now
        stream['last_output_at'] = now
        if key == 'output':
            stream['output_length'] = len(stream.get('output') or '')
        elif key == 'error':
            stream['error_length'] = len(stream.get('error') or '')


def _snapshot_stream_runtime_locked(stream):
    now = time.time()
    process = stream.get('process')
    process_running = bool(stream.get('request_running')) and not stream.get('done')
    process_pid = None

    if process is not None:
        process_pid = getattr(process, 'pid', None)
        try:
            return_code = process.poll()
        except Exception:
            return_code = None
        if return_code is None:
            process_running = True
        else:
            stream['done'] = True
            if stream.get('exit_code') is None:
                stream['exit_code'] = return_code
            stream['request_running'] = False
            stream['process'] = None
            stream['updated_at'] = now
            process_running = False
            process_pid = None

    started_at = stream.get('started_at') or stream.get('created_at')
    last_output_at = stream.get('last_output_at') or stream.get('updated_at')
    runtime_ms = None
    idle_ms = None

    if isinstance(started_at, (int, float)):
        runtime_ms = max(0, int((now - started_at) * 1000))
    if isinstance(last_output_at, (int, float)):
        idle_ms = max(0, int((now - last_output_at) * 1000))

    return {
        'process_running': process_running,
        'process_pid': process_pid,
        'runtime_ms': runtime_ms,
        'idle_ms': idle_ms,
    }


def _is_stream_cancelled(stream_id):
    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if not stream:
            return True
        return bool(stream.get('cancelled'))


def _append_gemini_stream_delta(stream_id, state_holder, event_payload):
    text = _extract_gemini_response_text(event_payload)
    if not text:
        return
    previous = state_holder.get('rendered_text', '')
    if text.startswith(previous):
        delta = text[len(previous):]
        state_holder['rendered_text'] = text
    else:
        delta = text
        state_holder['rendered_text'] = previous + text
    if delta:
        _append_stream_chunk(stream_id, 'output', delta)


def _consume_sse_payload(stream_id, provider, state_holder, payload_text):
    if not payload_text:
        return False
    if payload_text == '[DONE]':
        return True
    try:
        event_payload = json.loads(payload_text)
    except Exception:
        return False

    if _normalize_provider_name(provider) in _OPENAI_COMPATIBLE_PROVIDERS:
        delta = _extract_openai_stream_delta(event_payload)
        if delta:
            _append_stream_chunk(stream_id, 'output', delta)
        usage_payload = _extract_openai_usage(event_payload)
        if usage_payload:
            state_holder['openai_usage'] = usage_payload
        api_error = _extract_api_error_message(event_payload)
        if api_error and not delta:
            state_holder['stream_error'] = api_error
            _append_stream_chunk(stream_id, 'error', f'{api_error}\n')
            return True
        return False

    _append_gemini_stream_delta(stream_id, state_holder, event_payload)
    usage_metadata = _extract_gemini_usage_metadata(event_payload)
    if usage_metadata:
        state_holder['gemini_usage'] = usage_metadata
    return False


def _run_claude_cli_stream(
        stream_id,
        prompt,
        model,
        effort,
        exec_timeout_seconds,
        started_at,
        plan_mode=False,
        execution_cwd=None,
        allowed_dirs=None):
    cwd_path, normalized_allowed_dirs = _resolve_claude_execution_paths(
        execution_cwd=execution_cwd,
        allowed_dirs=allowed_dirs,
    )
    cmd = _build_claude_command(
        prompt,
        model=model,
        effort=effort,
        stream=True,
        plan_mode=plan_mode,
        allowed_dirs=normalized_allowed_dirs,
    )
    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        _append_stream_chunk(stream_id, 'error', 'claude 명령을 찾을 수 없습니다.\n')
        with state.model_streams_lock:
            stream = state.model_streams.get(stream_id)
            if stream:
                now = time.time()
                stream['done'] = True
                stream['exit_code'] = 127
                stream['completed_at'] = now
                stream['updated_at'] = now
                stream['finalize_reason'] = 'process_start_failed'
                stream['request_running'] = False
        return
    except Exception as exc:
        _append_stream_chunk(stream_id, 'error', f'Claude CLI 실행 중 오류가 발생했습니다: {exc}\n')
        with state.model_streams_lock:
            stream = state.model_streams.get(stream_id)
            if stream:
                now = time.time()
                stream['done'] = True
                stream['exit_code'] = 1
                stream['completed_at'] = now
                stream['updated_at'] = now
                stream['finalize_reason'] = 'process_start_failed'
                stream['request_running'] = False
        return

    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if stream:
            stream['process'] = process

    stdout_state_holder = {
        'rendered_text': '',
        'claude_usage': None,
        'stream_error': None,
    }
    stdout_target = _stream_reader
    stdout_args = (stream_id, process.stdout, 'output')
    if _claude_command_output_format(cmd) == 'stream-json':
        stdout_target = _stream_json_reader
        stdout_args = (
            stream_id,
            process.stdout,
            stdout_state_holder,
            _consume_claude_stream_line,
        )

    stdout_thread = threading.Thread(
        target=stdout_target,
        args=stdout_args,
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_reader,
        args=(stream_id, process.stderr, 'error'),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    cancelled = False
    while True:
        now = time.time()
        if isinstance(started_at, (int, float)) and now - started_at >= exec_timeout_seconds:
            _append_stream_chunk(stream_id, 'error', 'Claude CLI 응답 시간이 초과되었습니다.\n')
            _terminate_stream_process(process, 1)
            with state.model_streams_lock:
                stream = state.model_streams.get(stream_id)
                if stream:
                    stream['done'] = True
                    stream['exit_code'] = 124
                    stream['completed_at'] = now
                    stream['updated_at'] = now
                    stream['finalize_reason'] = 'exec_timeout'
                    stream['request_running'] = False
                    stream['process'] = None
            break

        if _is_stream_cancelled(stream_id):
            cancelled = True
            grace_seconds = _coerce_positive_seconds(
                MODEL_STREAM_TERMINATE_GRACE_SECONDS,
                default_value=3,
                minimum=0.5,
            )
            _terminate_stream_process(process, grace_seconds)
            break

        exit_code = process.poll()
        if exit_code is not None:
            with state.model_streams_lock:
                stream = state.model_streams.get(stream_id)
                if stream:
                    stream['done'] = True
                    stream['exit_code'] = exit_code
                    stream['completed_at'] = now
                    stream['updated_at'] = now
                    stream['request_running'] = False
                    stream['process'] = None
                    if exit_code == 0:
                        stream['finalize_reason'] = 'process_exit'
                    else:
                        stream['finalize_reason'] = 'process_exit_error'
            break

        time.sleep(0.1)

    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    if stdout_state_holder.get('claude_usage'):
        _update_usage_summary_from_claude_usage(stdout_state_holder['claude_usage'])

    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if stream:
            stream['request_running'] = False
            stream['process'] = None
            if cancelled:
                stream['saved'] = True
                stream['finalize_reason'] = 'user_cancelled'
                if stream.get('exit_code') is None:
                    stream['exit_code'] = 130
                if not isinstance(stream.get('completed_at'), (int, float)):
                    stream['completed_at'] = time.time()
                stream['updated_at'] = time.time()

    if not cancelled:
        finalize_model_stream(stream_id)


def _run_model_stream(
        stream_id,
        prompt,
        provider,
        model,
        reasoning_effort=None,
        plan_mode=False,
        execution_cwd=None,
        allowed_dirs=None):
    normalized_provider = _normalize_provider_name(provider)
    exec_timeout_seconds = _coerce_positive_seconds(
        min(MODEL_EXEC_TIMEOUT_SECONDS, MODEL_API_TIMEOUT_SECONDS),
        default_value=600,
        minimum=1,
    )

    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if stream:
            stream['request_running'] = True
            stream['updated_at'] = time.time()
            started_at = stream.get('started_at') or stream.get('created_at')
        else:
            started_at = time.time()

    if normalized_provider == 'claude':
        _run_claude_cli_stream(
            stream_id,
            prompt,
            model,
            reasoning_effort,
            exec_timeout_seconds,
            started_at,
            plan_mode=plan_mode,
            execution_cwd=execution_cwd,
            allowed_dirs=allowed_dirs,
        )
        return

    if not _has_valid_api_key(normalized_provider):
        missing_label = _provider_label(normalized_provider)
        _append_stream_chunk(stream_id, 'error', f'{missing_label} 키가 설정되지 않았습니다.\n')
        with state.model_streams_lock:
            stream = state.model_streams.get(stream_id)
            if stream:
                now = time.time()
                stream['done'] = True
                stream['exit_code'] = 401
                stream['completed_at'] = now
                stream['updated_at'] = now
                stream['finalize_reason'] = 'process_start_failed'
                stream['request_running'] = False
        return

    request_candidates = []
    if normalized_provider in _OPENAI_COMPATIBLE_PROVIDERS:
        payload = _build_openai_payload(prompt, model, stream=True)
        endpoints = _build_openai_compatible_api_urls(normalized_provider)
        auth_header = _provider_api_key_header(normalized_provider)
        auth_prefix = _provider_api_key_prefix(normalized_provider)
        auth_value = _build_auth_header_value(_provider_api_key(normalized_provider), auth_prefix)
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
        }
        if auth_value and auth_header:
            headers[auth_header] = auth_value
        for endpoint in endpoints:
            request_candidates.append((endpoint, _build_json_request(endpoint, payload, headers=headers)))
    else:
        endpoint = _build_gemini_api_url(model, stream=True)
        request_candidates.append(
            (
                endpoint,
                _build_json_request(
                    endpoint,
                    _build_gemini_payload(prompt),
                    headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream'},
                ),
            )
        )

    if not request_candidates:
        _append_stream_chunk(stream_id, 'error', f'{_provider_label(normalized_provider)} API 주소가 비어 있습니다.\n')
        with state.model_streams_lock:
            stream = state.model_streams.get(stream_id)
            if stream:
                now = time.time()
                stream['done'] = True
                stream['exit_code'] = 1
                stream['completed_at'] = now
                stream['updated_at'] = now
                stream['finalize_reason'] = 'process_start_failed'
                stream['request_running'] = False
        return

    timeout_seconds = max(1, int(exec_timeout_seconds))
    state_holder = {'rendered_text': '', 'gemini_usage': None, 'openai_usage': None, 'stream_error': None}
    cancelled = False
    stream_exception = None
    stream_exception_endpoint = ''

    for attempt_index, (endpoint, request) in enumerate(request_candidates):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                buffer = []
                while True:
                    if isinstance(started_at, (int, float)) and time.time() - started_at >= exec_timeout_seconds:
                        raise TimeoutError('model stream timed out')
                    if _is_stream_cancelled(stream_id):
                        cancelled = True
                        break

                    raw_line = response.readline()
                    if not raw_line:
                        if buffer:
                            payload_text = '\n'.join(buffer).strip()
                            if _consume_sse_payload(stream_id, normalized_provider, state_holder, payload_text):
                                break
                        break

                    line = raw_line.decode('utf-8', errors='replace').rstrip('\r\n')
                    if not line:
                        payload_text = '\n'.join(buffer).strip()
                        buffer = []
                        if _consume_sse_payload(stream_id, normalized_provider, state_holder, payload_text):
                            break
                        continue
                    if line.startswith(':'):
                        continue
                    if line.startswith('data:'):
                        buffer.append(line[5:].strip())
            stream_exception = None
            stream_exception_endpoint = ''
            break
        except Exception as exc:
            if _is_stream_cancelled(stream_id):
                cancelled = True
                stream_exception = None
                stream_exception_endpoint = ''
                break
            stream_exception = exc
            stream_exception_endpoint = endpoint
            should_retry = False
            if isinstance(exc, urllib.error.HTTPError):
                status_code = getattr(exc, 'code', None)
                should_retry = status_code in _RETRYABLE_HTTP_STATUS
            elif isinstance(exc, (urllib.error.URLError, TimeoutError)):
                should_retry = True
            if should_retry and attempt_index + 1 < len(request_candidates):
                continue
            break

    if stream_exception is not None and not cancelled:
        if isinstance(stream_exception, urllib.error.HTTPError):
            error_text = _read_http_error_message(stream_exception, normalized_provider)
        elif isinstance(stream_exception, urllib.error.URLError):
            error_text = f'{_provider_label(normalized_provider)} 연결에 실패했습니다: {stream_exception.reason}'
        elif isinstance(stream_exception, TimeoutError):
            error_text = f'{_provider_label(normalized_provider)} 응답 시간이 초과되었습니다.'
        else:
            error_text = f'{_provider_label(normalized_provider)} 실행 중 오류가 발생했습니다: {stream_exception}'
        if stream_exception_endpoint:
            error_text = f'{error_text} (endpoint: {stream_exception_endpoint})'
        _append_stream_chunk(stream_id, 'error', f'{error_text}\n')
        with state.model_streams_lock:
            stream = state.model_streams.get(stream_id)
            if stream:
                now = time.time()
                stream['done'] = True
                stream['exit_code'] = 1
                stream['completed_at'] = now
                stream['updated_at'] = now
                stream['finalize_reason'] = 'process_exit_error'
                stream['request_running'] = False
        return

    if state_holder.get('gemini_usage'):
        _update_usage_summary_from_gemini_metadata(normalized_provider, state_holder['gemini_usage'])
    if state_holder.get('openai_usage'):
        _update_usage_summary_from_openai_usage(normalized_provider, state_holder['openai_usage'])

    has_stream_error = bool(state_holder.get('stream_error'))
    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if stream:
            now = time.time()
            stream['done'] = True
            stream['exit_code'] = 130 if cancelled else (1 if has_stream_error else 0)
            stream['completed_at'] = now
            stream['updated_at'] = now
            stream['request_running'] = False
            if cancelled:
                stream['saved'] = True
                stream['finalize_reason'] = 'user_cancelled'
            elif has_stream_error:
                stream['finalize_reason'] = 'process_exit_error'
            else:
                stream['finalize_reason'] = 'process_exit'
    if not cancelled:
        finalize_model_stream(stream_id)


def create_model_stream(
        session_id,
        prompt,
        provider,
        model,
        reasoning_effort=None,
        apply_side_effects=True,
        plan_mode=False,
        execution_cwd=None,
        allowed_dirs=None,
        draft_message_id=None):
    stream_id = uuid.uuid4().hex
    created_at = time.time()
    stream = {
        'id': stream_id,
        'session_id': session_id,
        'provider': _normalize_provider_name(provider),
        'model': model,
        'reasoning_effort': _normalize_reasoning_effort(reasoning_effort),
        'plan_mode': bool(plan_mode),
        'apply_side_effects': bool(apply_side_effects),
        'execution_cwd': str(execution_cwd or ''),
        'allowed_dirs': (
            list(allowed_dirs)
            if isinstance(allowed_dirs, (list, tuple, set))
            else []
        ),
        'draft_message_id': draft_message_id or None,
        'output': '',
        'error': '',
        'done': False,
        'saved': False,
        'exit_code': None,
        'cancelled': False,
        'request_running': False,
        'process': None,
        'started_at': created_at,
        'last_output_at': created_at,
        'completed_at': None,
        'saved_at': None,
        'finalize_reason': None,
        'output_length': 0,
        'error_length': 0,
        'created_at': created_at,
        'updated_at': created_at,
    }
    with state.model_streams_lock:
        state.model_streams[stream_id] = stream

    thread = threading.Thread(
        target=_run_model_stream,
        args=(stream_id, prompt, provider, model, reasoning_effort, plan_mode, execution_cwd, allowed_dirs),
        daemon=True,
    )
    thread.start()
    return {
        'id': stream_id,
        'started_at': int(created_at * 1000),
        'created_at': int(created_at * 1000),
    }


def _get_session_submit_lock(session_id):
    session_key = str(session_id or '').strip()
    if not session_key:
        session_key = '__unknown__'
    with _SESSION_SUBMIT_LOCKS_GUARD:
        submit_lock = _SESSION_SUBMIT_LOCKS.get(session_key)
        if submit_lock is None:
            submit_lock = threading.Lock()
            _SESSION_SUBMIT_LOCKS[session_key] = submit_lock
    return submit_lock


def _find_active_stream_id_locked(session_id):
    for stream_id, stream in state.model_streams.items():
        if stream.get('session_id') != session_id:
            continue
        if stream.get('cancelled'):
            continue
        _snapshot_stream_runtime_locked(stream)
        if stream.get('done'):
            continue
        return stream_id
    return None


def get_active_stream_id_for_session(session_id):
    with state.model_streams_lock:
        return _find_active_stream_id_locked(session_id)


def _append_plan_mode_guardrails(prompt_text):
    normalized = str(prompt_text or '').strip()
    if not normalized:
        normalized = '(empty)'
    return f'{normalized}\n\n{_PLAN_MODE_PROMPT_SUFFIX}'


def _normalize_layout_root(value):
    normalized = str(value or '').strip().lower()
    if normalized in _LAYOUT_ROOT_KEYS:
        return normalized
    return _LAYOUT_ROOT_WORKSPACE


def _normalize_layout_relative_path(value):
    source = str(value or '').strip().replace('\\', '/')
    if not source or source == '.':
        return ''
    if len(source) > _LAYOUT_MAX_PATH_CHARS:
        source = source[:_LAYOUT_MAX_PATH_CHARS]
    if source.startswith('/') or source.startswith('~'):
        return ''
    normalized = source.strip('/')
    if not normalized:
        return ''
    if ':' in normalized:
        return ''
    parts = []
    for part in normalized.split('/'):
        if not part or part == '.':
            continue
        if part == '..' or '\x00' in part:
            return ''
        parts.append(part)
    return '/'.join(parts)


def _resolve_layout_root_path(root_key):
    normalized_root = _normalize_layout_root(root_key)
    if normalized_root == _LAYOUT_ROOT_SERVER:
        return Path.cwd().resolve()
    return WORKSPACE_DIR.resolve()


def _normalize_layout_context(value):
    payload = value if isinstance(value, dict) else {}
    context = {
        'work_mode_enabled': _parse_plan_mode(payload.get('work_mode_enabled')),
        'file_browser_open': _parse_plan_mode(payload.get('file_browser_open')),
        'active_root': _normalize_layout_root(payload.get('active_root')),
        'active_directory_path': _normalize_layout_relative_path(payload.get('active_directory_path')),
        'active_file_path': _normalize_layout_relative_path(payload.get('active_file_path')),
        'work_mode_root': _normalize_layout_root(payload.get('work_mode_root')),
        'work_mode_directory_path': _normalize_layout_relative_path(payload.get('work_mode_directory_path')),
        'work_mode_file_path': _normalize_layout_relative_path(payload.get('work_mode_file_path')),
    }

    if context['work_mode_enabled']:
        if not context['active_directory_path'] and context['work_mode_directory_path']:
            context['active_directory_path'] = context['work_mode_directory_path']
        if not context['active_file_path'] and context['work_mode_file_path']:
            context['active_file_path'] = context['work_mode_file_path']
    return context


def _resolve_layout_execution_cwd(layout_context):
    context = _normalize_layout_context(layout_context)
    root_path = _resolve_layout_root_path(context.get('active_root'))
    directory_path = context.get('active_directory_path') or ''
    file_path = context.get('active_file_path') or ''

    candidate = root_path
    if directory_path:
        candidate = root_path / directory_path
    elif file_path:
        candidate = (root_path / file_path).parent

    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root_path)
    except Exception:
        resolved = root_path

    if not resolved.exists() or not resolved.is_dir():
        return str(root_path)
    return str(resolved)


def _resolve_layout_allowed_dirs(layout_context):
    context = _normalize_layout_context(layout_context)
    workspace_root = WORKSPACE_DIR.resolve()
    server_root = Path.cwd().resolve()
    active_root = _resolve_layout_root_path(context.get('active_root'))
    allowed = []
    for candidate in (workspace_root, server_root, active_root):
        normalized = str(candidate)
        if normalized and normalized not in allowed:
            allowed.append(normalized)
    return allowed


def _append_layout_context_prompt(prompt_text, layout_context):
    context = _normalize_layout_context(layout_context)
    active_root_key = context.get('active_root') or _LAYOUT_ROOT_WORKSPACE
    active_root_path = _resolve_layout_root_path(active_root_key)
    active_directory = context.get('active_directory_path') or ''
    active_file = context.get('active_file_path') or ''

    if active_directory:
        active_cwd = str((active_root_path / active_directory).resolve(strict=False))
    elif active_file:
        active_cwd = str((active_root_path / active_file).resolve(strict=False).parent)
    else:
        active_cwd = str(active_root_path)

    active_file_abs = ''
    if active_file:
        active_file_abs = str((active_root_path / active_file).resolve(strict=False))

    lines = [
        str(prompt_text or ''),
        '',
        '## Workspace Layout Context',
        f"- work_mode_enabled: {'true' if context.get('work_mode_enabled') else 'false'}",
        f"- file_browser_open: {'true' if context.get('file_browser_open') else 'false'}",
        f"- active_root: {active_root_key}",
        f"- active_cwd: {active_cwd}",
        f"- active_directory_path: {active_directory or '(none)'}",
        f"- active_file_path: {active_file or '(none)'}",
    ]
    if active_file_abs:
        lines.append(f"- active_file_abs: {active_file_abs}")
    return '\n'.join(lines).strip()


def _start_model_stream_for_session_locked(
        session_id,
        prompt,
        prompt_with_context,
        provider_override=None,
        model_override=None,
        reasoning_override=None,
        apply_side_effects=True,
        plan_mode=False,
        execution_cwd=None,
        allowed_dirs=None):
    with state.model_streams_lock:
        active_stream_id = _find_active_stream_id_locked(session_id)
    if active_stream_id:
        return {
            'ok': False,
            'already_running': True,
            'active_stream_id': active_stream_id,
        }

    user_message = append_message(session_id, 'user', prompt)
    if not user_message:
        return {'ok': False, 'error': '메시지를 저장하지 못했습니다.'}

    draft_message = append_message(
        session_id, 'assistant', '[응답 생성 중...]', {'is_draft': True}
    )
    draft_message_id = draft_message.get('id') if draft_message else None

    settings = get_settings()
    base_provider = _normalize_provider_name(settings.get('provider'))
    if provider_override is None:
        provider = base_provider
    else:
        provider = _normalize_provider_name(provider_override)
    if model_override is None:
        if provider == base_provider:
            model = _normalize_model_name(provider, settings.get('model'))
        else:
            model = _default_model_for_provider(provider)
    else:
        model = _normalize_model_name(provider, model_override)
    reasoning_effort = _normalize_reasoning_effort(reasoning_override)
    if reasoning_effort is None:
        if plan_mode:
            reasoning_effort = _normalize_reasoning_effort(settings.get('plan_mode_reasoning_effort'))
        if reasoning_effort is None:
            reasoning_effort = _normalize_reasoning_effort(settings.get('reasoning_effort'))
        if reasoning_effort is None:
            reasoning_effort = _normalize_reasoning_effort(MODEL_DEFAULT_REASONING_EFFORT)

    stream_info = create_model_stream(
        session_id,
        prompt_with_context,
        provider,
        model,
        reasoning_effort=reasoning_effort,
        apply_side_effects=apply_side_effects,
        plan_mode=plan_mode,
        execution_cwd=execution_cwd,
        allowed_dirs=allowed_dirs,
        draft_message_id=draft_message_id,
    )
    return {
        'ok': True,
        'stream_id': stream_info.get('id'),
        'started_at': stream_info.get('started_at') or stream_info.get('created_at'),
        'user_message': user_message,
    }


def _build_model_pending_queue_entry(prompt, plan_mode=False, layout_context=None):
    return {
        'id': uuid.uuid4().hex,
        'prompt': str(prompt or '').strip(),
        'plan_mode': bool(plan_mode),
        'layout_context': _normalize_layout_context(layout_context),
        'created_at': normalize_timestamp(None),
    }


def _enqueue_pending_queue_entry(session_id, prompt, plan_mode=False, layout_context=None):
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        session = _find_session(sessions, session_id)
        if not session:
            return {'ok': False, 'error': '세션을 찾을 수 없습니다.'}
        queue = _normalize_session_pending_queue(session)
        entry = _build_model_pending_queue_entry(prompt, plan_mode=plan_mode, layout_context=layout_context)
        if not entry.get('prompt'):
            return {'ok': False, 'error': '프롬프트가 비어 있습니다.'}
        queue.append(entry)
        session['updated_at'] = normalize_timestamp(None)
        data['sessions'] = _sort_sessions(sessions)
        _save_data(data)
        return {
            'ok': True,
            'entry': entry,
            'queue_count': len(queue),
        }


def _start_next_queued_model_stream_locked(session_id):
    with state.model_streams_lock:
        active_stream_id = _find_active_stream_id_locked(session_id)
    if active_stream_id:
        return {
            'ok': True,
            'started': False,
            'already_running': True,
            'active_stream_id': active_stream_id,
            'queue_count': get_pending_queue_count_for_session(session_id),
        }

    max_drain_attempts = 16
    for _ in range(max_drain_attempts):
        pending_entry, _ = _peek_pending_queue_entry(session_id)
        if not pending_entry:
            return {
                'ok': True,
                'started': False,
                'queue_count': 0,
            }

        prompt = str(pending_entry.get('prompt') or '').strip()
        if not prompt:
            remaining = _remove_pending_queue_entry(session_id, pending_entry.get('id'))
            if remaining <= 0:
                return {'ok': True, 'started': False, 'queue_count': 0}
            continue

        plan_mode = bool(pending_entry.get('plan_mode'))
        layout_context = _normalize_layout_context(pending_entry.get('layout_context'))
        session = get_session(session_id)
        if not session:
            return {'ok': False, 'error': '세션을 찾을 수 없습니다.'}

        ensure_default_title(session_id, prompt)
        prompt_for_model = _append_layout_context_prompt(prompt, layout_context)
        prompt_with_context = build_model_prompt(session.get('messages', []), prompt_for_model)
        if plan_mode:
            prompt_with_context = _append_plan_mode_guardrails(prompt_with_context)

        execution_profile = resolve_execution_profile(plan_mode=plan_mode)
        execution_cwd = _resolve_layout_execution_cwd(layout_context)
        allowed_dirs = _resolve_layout_allowed_dirs(layout_context)
        start_result = _start_model_stream_for_session_locked(
            session_id,
            prompt,
            prompt_with_context,
            provider_override=execution_profile.get('provider'),
            model_override=execution_profile.get('model'),
            reasoning_override=execution_profile.get('reasoning_effort'),
            apply_side_effects=not plan_mode,
            plan_mode=plan_mode,
            execution_cwd=execution_cwd,
            allowed_dirs=allowed_dirs,
        )
        if not start_result.get('ok'):
            return start_result

        remaining_queue_count = _remove_pending_queue_entry(session_id, pending_entry.get('id'))
        start_result['started'] = True
        start_result['queued'] = False
        start_result['queue_count'] = remaining_queue_count
        return start_result

    return {
        'ok': False,
        'error': '대기열 처리 중 오류가 발생했습니다.',
    }


def start_model_stream_for_session(
        session_id,
        prompt,
        prompt_with_context,
        provider_override=None,
        model_override=None,
        reasoning_override=None,
        apply_side_effects=True,
        plan_mode=False,
        execution_cwd=None,
        allowed_dirs=None):
    submit_lock = _get_session_submit_lock(session_id)
    with submit_lock:
        return _start_model_stream_for_session_locked(
            session_id,
            prompt,
            prompt_with_context,
            provider_override=provider_override,
            model_override=model_override,
            reasoning_override=reasoning_override,
            apply_side_effects=apply_side_effects,
            plan_mode=plan_mode,
            execution_cwd=execution_cwd,
            allowed_dirs=allowed_dirs,
        )


def enqueue_model_stream_for_session(session_id, prompt, plan_mode=False, layout_context=None):
    submit_lock = _get_session_submit_lock(session_id)
    with submit_lock:
        queued = _enqueue_pending_queue_entry(
            session_id,
            prompt,
            plan_mode=plan_mode,
            layout_context=layout_context,
        )
        if not queued.get('ok'):
            return queued

        start_result = _start_next_queued_model_stream_locked(session_id)
        if start_result.get('ok') and start_result.get('started'):
            return start_result
        queue_count = start_result.get('queue_count')
        if not isinstance(queue_count, int):
            queue_count = int(queued.get('queue_count') or 0)
        return {
            'ok': bool(start_result.get('ok', True)),
            'queued': True,
            'started': False,
            'queue_count': max(0, queue_count),
            'active_stream_id': start_result.get('active_stream_id'),
            'error': start_result.get('error'),
        }


def trigger_next_queued_model_stream(session_id):
    if not session_id:
        return None
    submit_lock = _get_session_submit_lock(session_id)
    with submit_lock:
        return _start_next_queued_model_stream_locked(session_id)


def _resume_pending_model_queues_worker():
    with _DATA_LOCK:
        data = _load_data()
        sessions = data.get('sessions', [])
        session_ids = []
        for session in sessions:
            if not isinstance(session, dict):
                continue
            session_id = str(session.get('id') or '').strip()
            if not session_id:
                continue
            if _count_pending_queue_items(session) > 0:
                session_ids.append(session_id)

    for session_id in session_ids:
        try:
            trigger_next_queued_model_stream(session_id)
        except Exception:  # pragma: no cover - best effort bootstrap
            _LOGGER.exception('Failed to resume pending Model queue (session_id=%s)', session_id)


def ensure_pending_queue_background_worker():
    global _PENDING_QUEUE_BOOTSTRAP_STARTED
    with _PENDING_QUEUE_BOOTSTRAP_LOCK:
        if _PENDING_QUEUE_BOOTSTRAP_STARTED:
            return
        _PENDING_QUEUE_BOOTSTRAP_STARTED = True

    thread = threading.Thread(
        target=_resume_pending_model_queues_worker,
        daemon=True,
    )
    thread.start()
    return {'ok': True, 'started': True}


def list_model_streams(include_done=False):
    streams = []
    with state.model_streams_lock:
        for stream in state.model_streams.values():
            runtime = _snapshot_stream_runtime_locked(stream)
            if not include_done:
                if stream.get('done') or stream.get('cancelled'):
                    continue
            session_id = stream.get('session_id')
            streams.append(
                {
                    'id': stream.get('id'),
                    'session_id': session_id,
                    'provider': stream.get('provider'),
                    'model': stream.get('model'),
                    'done': stream.get('done', False),
                    'cancelled': stream.get('cancelled', False),
                    'pending_queue_count': get_pending_queue_count_for_session(session_id),
                    'output_length': int(stream.get('output_length') or len(stream.get('output') or '')),
                    'error_length': int(stream.get('error_length') or len(stream.get('error') or '')),
                    'started_at': _epoch_to_millis(stream.get('started_at') or stream.get('created_at')) or 0,
                    'created_at': _epoch_to_millis(stream.get('created_at')) or 0,
                    'completed_at': _epoch_to_millis(stream.get('completed_at')),
                    'saved_at': _epoch_to_millis(stream.get('saved_at')),
                    'updated_at': _epoch_to_millis(stream.get('updated_at')) or 0,
                    'finalize_reason': stream.get('finalize_reason'),
                    'process_running': runtime.get('process_running', False),
                    'process_pid': runtime.get('process_pid'),
                    'runtime_ms': runtime.get('runtime_ms'),
                    'idle_ms': runtime.get('idle_ms'),
                }
            )
    streams.sort(key=lambda item: item.get('updated_at', 0), reverse=True)
    return streams


def read_model_stream(stream_id, output_offset=0, error_offset=0):
    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if not stream:
            return None
        runtime = _snapshot_stream_runtime_locked(stream)
        output = stream['output']
        error = stream['error']
        session_id = stream['session_id']
        return {
            'output': output[output_offset:],
            'error': error[error_offset:],
            'output_length': int(stream.get('output_length') or len(output)),
            'error_length': int(stream.get('error_length') or len(error)),
            'done': stream['done'],
            'exit_code': stream['exit_code'],
            'saved': stream.get('saved', False),
            'session_id': session_id,
            'pending_queue_count': get_pending_queue_count_for_session(session_id),
            'provider': stream.get('provider'),
            'model': stream.get('model'),
            'started_at': _epoch_to_millis(stream.get('started_at') or stream.get('created_at')) or 0,
            'created_at': _epoch_to_millis(stream.get('created_at')) or 0,
            'completed_at': _epoch_to_millis(stream.get('completed_at')),
            'saved_at': _epoch_to_millis(stream.get('saved_at')),
            'updated_at': _epoch_to_millis(stream.get('updated_at')) or 0,
            'finalize_reason': stream.get('finalize_reason'),
            'process_running': runtime.get('process_running', False),
            'process_pid': runtime.get('process_pid'),
            'runtime_ms': runtime.get('runtime_ms'),
            'idle_ms': runtime.get('idle_ms'),
        }


def finalize_model_stream(stream_id):
    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if not stream or stream.get('saved') or not stream.get('done'):
            return None
        now = time.time()
        started_at = stream.get('started_at') or stream.get('created_at')
        completed_at = stream.get('completed_at') or stream.get('updated_at') or now
        stream['completed_at'] = completed_at
        stream['saved_at'] = now
        stream['updated_at'] = now

        finalize_reason = stream.get('finalize_reason')
        if not finalize_reason:
            if stream.get('cancelled'):
                finalize_reason = 'user_cancelled'
            elif stream.get('exit_code') == 0:
                finalize_reason = 'process_exit'
            else:
                finalize_reason = 'process_exit_error'
            stream['finalize_reason'] = finalize_reason

        stream['saved'] = True
        stream['process'] = None
        output = (stream.get('output') or '').strip()
        error = (stream.get('error') or '').strip()
        session_id = stream.get('session_id')
        exit_code = stream.get('exit_code')
        apply_side_effects = bool(stream.get('apply_side_effects', True))
        draft_message_id = stream.get('draft_message_id')
    metadata = _build_stream_message_metadata(started_at, completed_at, now, finalize_reason)
    created_at_value = _iso_timestamp_from_epoch(completed_at)
    if metadata:
        finalize_lag_ms = metadata.get('finalize_lag_ms')
        if isinstance(finalize_lag_ms, (int, float)) and finalize_lag_ms >= _FINALIZE_LAG_WARNING_MS:
            _LOGGER.warning(
                'Model stream finalize lag is high (stream_id=%s, lag_ms=%s, reason=%s)',
                stream_id,
                finalize_lag_ms,
                finalize_reason,
            )

    if exit_code == 0:
        final_output, patch_metadata = finalize_assistant_output(
            output,
            apply_side_effects=apply_side_effects,
        )
        merged_metadata = dict(metadata or {})
        if isinstance(patch_metadata, dict):
            merged_metadata.update(patch_metadata)
        if draft_message_id:
            saved_message = update_message(
                session_id,
                draft_message_id,
                final_output,
                role='assistant',
                metadata=merged_metadata or None,
                created_at=created_at_value,
            )
        else:
            saved_message = append_message(
                session_id,
                'assistant',
                final_output,
                merged_metadata or None,
                created_at=created_at_value,
            )
        trigger_next_queued_model_stream(session_id)
        return saved_message
    message_text = error or output or 'Model API 실행에 실패했습니다.'
    if draft_message_id:
        saved_message = update_message(
            session_id,
            draft_message_id,
            message_text,
            role='error',
            metadata=metadata or None,
            created_at=created_at_value,
        )
    else:
        saved_message = append_message(
            session_id,
            'error',
            message_text,
            metadata or None,
            created_at=created_at_value,
        )
    trigger_next_queued_model_stream(session_id)
    return saved_message


def stop_model_stream(stream_id):
    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if not stream:
            return None
        if stream.get('cancelled'):
            return {'status': 'already_cancelled'}
        now = time.time()
        stream['cancelled'] = True
        stream['done'] = True
        stream['saved'] = True
        stream['exit_code'] = 130
        stream['completed_at'] = now
        stream['updated_at'] = now
        stream['finalize_reason'] = 'user_cancelled'
        stream['request_running'] = False
        process = stream.get('process')
        session_id = stream.get('session_id')
        output = (stream.get('output') or '').strip()
        error = (stream.get('error') or '').strip()
        started_at = stream.get('started_at') or stream.get('created_at')
        completed_at = stream.get('completed_at')
        draft_message_id = stream.get('draft_message_id')

    grace_seconds = _coerce_positive_seconds(
        MODEL_STREAM_TERMINATE_GRACE_SECONDS,
        default_value=3,
        minimum=0.5,
    )
    _terminate_stream_process(process, grace_seconds)

    if output or error:
        combined = output or error
        if output and error:
            combined = f'{output}\n{error}'
        message_text = f'{combined}\n\n[사용자 중지]'
    else:
        message_text = '사용자에 의해 중지되었습니다.'

    saved_at = time.time()
    metadata = _build_stream_message_metadata(
        started_at,
        completed_at,
        saved_at,
        'user_cancelled',
    )
    if draft_message_id:
        saved_message = update_message(
            session_id,
            draft_message_id,
            message_text,
            role='error',
            metadata=metadata,
            created_at=_iso_timestamp_from_epoch(completed_at),
        )
    else:
        saved_message = append_message(
            session_id,
            'error',
            message_text,
            metadata,
            created_at=_iso_timestamp_from_epoch(completed_at),
        )

    with state.model_streams_lock:
        stream = state.model_streams.get(stream_id)
        if stream:
            stream['saved'] = True
            stream['saved_at'] = saved_at
            stream['updated_at'] = saved_at
            stream['process'] = None
    trigger_next_queued_model_stream(session_id)
    return {'status': 'stopped', 'saved_message': saved_message}


def cleanup_model_streams():
    now = time.time()
    stale_ids = []
    with state.model_streams_lock:
        for stream_id, stream in state.model_streams.items():
            if not stream.get('done'):
                continue
            if now - stream.get('updated_at', now) > MODEL_STREAM_TTL_SECONDS:
                stale_ids.append(stream_id)
        for stream_id in stale_ids:
            state.model_streams.pop(stream_id, None)


def get_claude_monitor_usage(plan='pro', hours_back=96, use_cache=True):
    """Return claude-monitor usage analysis as a plain dict.

    Calls ``claude_monitor.data.analysis.analyze_usage`` directly so that
    no TUI / terminal is needed.  The result is augmented with plan-limit
    metadata when a recognised *plan* name is supplied.

    Args:
        plan: Subscription plan name ('pro', 'max5', 'max20'). Defaults to 'pro'.
        hours_back: How many hours of history to analyse. Defaults to 96.

    Returns:
        dict with keys: blocks, metadata, entries_count, total_tokens,
        total_cost, plan_info (optional).
    """
    try:
        from claude_monitor.data.analysis import analyze_usage
    except ImportError as exc:
        return {'error': f'claude-monitor not installed: {exc}'}

    try:
        hours = int(hours_back) if hours_back is not None else None
    except (TypeError, ValueError):
        hours = 96

    try:
        result = analyze_usage(hours_back=hours, use_cache=bool(use_cache))
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception('claude_monitor analyze_usage failed')
        return {'error': str(exc)}

    # Attach plan limit info if plan is recognised.
    try:
        from claude_monitor.core.plans import PLAN_LIMITS, PlanType
        plan_type = PlanType.from_string(str(plan).lower())
        limits = PLAN_LIMITS.get(plan_type, {})
        result['plan_info'] = {
            'plan': plan_type.value,
            'display_name': limits.get('display_name', plan_type.value),
            'token_limit': limits.get('token_limit'),
            'cost_limit': limits.get('cost_limit'),
            'message_limit': limits.get('message_limit'),
        }
    except Exception:  # noqa: BLE001
        result['plan_info'] = {'plan': plan, 'error': 'unknown plan'}

    return result


def get_monitor_rate_limits(plan='pro', use_cache=False):
    """Return five_hour and weekly rate-limit dicts derived from claude-monitor.

    Returns a dict ``{'five_hour': {...}, 'weekly': {...}}`` where each entry
    has ``used_percent`` (0-100 float) and ``resets_at`` (ISO timestamp str),
    or ``None`` if the data cannot be obtained.
    """
    try:
        monitor = get_claude_monitor_usage(plan=plan, hours_back=168, use_cache=use_cache)
    except Exception:
        return None

    if monitor.get('error'):
        return None

    plan_info = monitor.get('plan_info') or {}
    token_limit = plan_info.get('token_limit')
    cost_limit = plan_info.get('cost_limit')
    blocks = monitor.get('blocks') or []

    # 5h: use the active block (or most recent)
    active_block = next((b for b in reversed(blocks) if b.get('isActive')), None)
    if active_block is None and blocks:
        active_block = blocks[-1]

    five_hour = None
    if active_block and token_limit and token_limit > 0:
        used_tokens = active_block.get('totalTokens') or 0
        five_hour = {
            'used_percent': round((used_tokens / token_limit) * 100, 2),
            'resets_at': active_block.get('endTime'),
        }

    # Weekly: sum all block costs against the plan cost_limit
    weekly = None
    if cost_limit and cost_limit > 0:
        total_cost = sum((b.get('costUSD') or 0.0) for b in blocks)
        from datetime import datetime, timedelta, timezone as _tz
        now = datetime.now(_tz.utc)
        days_to_monday = (7 - now.weekday()) % 7 or 7
        next_monday = (now + timedelta(days=days_to_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        weekly = {
            'used_percent': round((total_cost / cost_limit) * 100, 2),
            'resets_at': next_monday.isoformat(),
        }

    return {'five_hour': five_hour, 'weekly': weekly}
