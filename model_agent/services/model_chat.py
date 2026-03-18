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
    LEGACY_MODEL_CHAT_STORE_PATH,
    LEGACY_MODEL_SETTINGS_PATH,
    LEGACY_MODEL_USAGE_SNAPSHOT_PATH,
    MODEL_API_TIMEOUT_SECONDS,
    MODEL_CLAUDE_DEFAULT_MODEL,
    MODEL_CHAT_STORE_PATH,
    MODEL_CONTEXT_MAX_CHARS,
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
    MODEL_SETTINGS_PATH,
    MODEL_STREAM_TERMINATE_GRACE_SECONDS,
    MODEL_STREAM_TTL_SECONDS,
    MODEL_USAGE_SNAPSHOT_PATH,
    MODEL_WORKSPACE_BLOCKED_PATHS,
    WORKSPACE_DIR,
)
from ..utils.time import normalize_timestamp

_DATA_LOCK = threading.Lock()
_CONFIG_LOCK = threading.Lock()
_USAGE_LOCK = threading.Lock()
_SESSION_SUBMIT_LOCKS_GUARD = threading.Lock()
_SESSION_SUBMIT_LOCKS = {}
_PATCH_APPLY_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)
_FINALIZE_LAG_WARNING_MS = 5000
_SUPPORTED_PROVIDERS = ('gemini', 'dtgpt', 'claude')
_OPENAI_COMPATIBLE_PROVIDERS = ('dtgpt',)
_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_ENV_REFERENCE_PATTERN = re.compile(r'^\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}$')
_PATCH_BLOCK_PATTERN = re.compile(r'```(?:diff|patch)\s*\n(.*?)```', re.IGNORECASE | re.DOTALL)
_TOOL_RUN_BLOCK_PATTERN = re.compile(r'```(?:bash|sh|shell)\s*\n(.*?)```', re.IGNORECASE | re.DOTALL)
_HUNK_HEADER_PATTERN = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')
_PATCH_MAX_CHARS = 400_000
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
    else:
        for provider in _SUPPORTED_PROVIDERS:
            if provider not in options:
                options.append(provider)
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
    if normalized == 'claude':
        return [_default_model_for_provider('claude')]
    configured = MODEL_PROVIDER_MODEL_OPTIONS.get(normalized)
    if not isinstance(configured, list):
        configured = []
    options = []
    for item in configured:
        text = str(item or '').strip()
        if not text or text in options:
            continue
        options.append(text)
    default_model = _default_model_for_provider(normalized)
    if default_model not in options:
        options.insert(0, default_model)
    return options


def _resolve_existing_path(primary_path, legacy_path):
    if primary_path.exists():
        return primary_path
    if legacy_path.exists():
        return legacy_path
    return primary_path


def _load_data():
    source_path = _resolve_existing_path(MODEL_CHAT_STORE_PATH, LEGACY_MODEL_CHAT_STORE_PATH)
    if not source_path.exists():
        return {'sessions': []}
    try:
        data = json.loads(source_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {'sessions': []}
    if not isinstance(data, dict):
        return {'sessions': []}
    sessions = data.get('sessions')
    if not isinstance(sessions, list):
        data['sessions'] = []
    return data


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
    return {
        'provider': provider,
        'model': _default_model_for_provider(provider),
    }


def _read_workspace_settings():
    source_path = _resolve_existing_path(MODEL_SETTINGS_PATH, LEGACY_MODEL_SETTINGS_PATH)
    try:
        raw = source_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return _default_settings()
    except Exception:
        return _default_settings()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _default_settings()
    if not isinstance(data, dict):
        return _default_settings()

    provider = _normalize_provider_name(data.get('provider'))
    model = str(data.get('model') or '').strip() or _default_model_for_provider(provider)
    return {
        'provider': provider,
        'model': model,
    }


def _write_workspace_settings(settings):
    provider = _normalize_provider_name(settings.get('provider'))
    model = str(settings.get('model') or '').strip() or _default_model_for_provider(provider)
    payload = {
        'provider': provider,
        'model': model,
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


def _resolve_settings_values(current, provider=None, model=None):
    current_provider = _normalize_provider_name(current.get('provider'))
    current_raw_model = str(current.get('model') or '').strip()
    current_model = _normalize_model_name(current_provider, current_raw_model)
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

    return {
        'provider': next_provider,
        'model': next_model,
    }


def resolve_settings_preview(provider=None, model=None):
    with _CONFIG_LOCK:
        current = _read_workspace_settings()
        return _resolve_settings_values(
            current,
            provider=provider,
            model=model,
        )


def update_settings(provider=None, model=None):
    with _CONFIG_LOCK:
        current = _read_workspace_settings()
        payload = _resolve_settings_values(
            current,
            provider=provider,
            model=model,
        )
        _write_workspace_settings(payload)
        return payload


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
    return {
        'provider': provider,
        'five_hour': None,
        'weekly': None,
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
        summary.append(
            {
                'id': session.get('id'),
                'title': session.get('title') or 'New session',
                'created_at': session.get('created_at'),
                'updated_at': session.get('updated_at'),
                'message_count': len(session.get('messages', [])),
                'token_count': _estimate_session_tokens(session),
            }
        )
    return summary


def get_session(session_id):
    with _DATA_LOCK:
        data = _load_data()
        session = _find_session(data.get('sessions', []), session_id)
    return deepcopy(session) if session else None


def create_session(title=None):
    now = normalize_timestamp(None)
    session = {
        'id': uuid.uuid4().hex,
        'title': (title or '').strip() or 'New session',
        'created_at': now,
        'updated_at': now,
        'messages': [],
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


def finalize_assistant_output(content):
    text = str(content or '').strip()
    if not text:
        return text, None

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


def _format_context_message(message, index, max_chars=1400):
    role = str((message or {}).get('role') or 'user').strip().lower() or 'user'
    content = _normalize_context_text((message or {}).get('content'))
    if not content:
        content = '(empty)'
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
        role = _ROLE_LABELS.get((message or {}).get('role'), 'User')
        content = _single_line_text((message or {}).get('content'))
        if not content:
            continue
        lines.append(f"{index}. {role}: {_clip_text(content, 180)}")
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
        content = _normalize_context_text(message.get('content'))
        if not content:
            continue
        normalized_messages.append({'role': message.get('role'), 'content': content})

    recent_budget = max(1200, int(max_chars * 0.62))
    recent_blocks = []
    recent_chars = 0
    total_messages = len(normalized_messages)
    for reverse_index, message in enumerate(reversed(normalized_messages), start=1):
        original_index = total_messages - reverse_index + 1
        block = _format_context_message(message, original_index)
        projected = recent_chars + len(block) + 1
        if recent_blocks and projected > recent_budget:
            break
        recent_blocks.append(block)
        recent_chars = projected
    recent_blocks.reverse()

    summary_count = max(0, total_messages - len(recent_blocks))
    summary_budget = max(360, int(max_chars * 0.24))
    memory_lines = _build_memory_lines(normalized_messages[:summary_count], summary_budget)

    structured_prompt = _compose_structured_prompt(memory_lines, recent_blocks, prompt_text)
    if len(structured_prompt) <= max_chars:
        return structured_prompt

    while len(structured_prompt) > max_chars and memory_lines:
        memory_lines = memory_lines[1:]
        structured_prompt = _compose_structured_prompt(memory_lines, recent_blocks, prompt_text)
    while len(structured_prompt) > max_chars and recent_blocks:
        recent_blocks = recent_blocks[1:]
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


def _build_claude_command(prompt):
    return ['claude', '-p', str(prompt or '')]


def _execute_claude_prompt(prompt):
    cmd = _build_claude_command(prompt)
    timeout_seconds = max(1, int(MODEL_EXEC_TIMEOUT_SECONDS))
    try:
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE_DIR),
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
    if output_text:
        return output_text, None
    if error_text:
        return None, error_text
    return None, 'Claude CLI 응답이 비어 있습니다.'


def execute_model_prompt(prompt):
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    provider = _normalize_provider_name(settings.get('provider'))
    model = _normalize_model_name(provider, settings.get('model'))

    if provider == 'claude':
        return _execute_claude_prompt(prompt)
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


def _run_claude_cli_stream(stream_id, prompt, exec_timeout_seconds, started_at):
    cmd = _build_claude_command(prompt)
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(WORKSPACE_DIR),
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

    stdout_thread = threading.Thread(
        target=_stream_reader,
        args=(stream_id, process.stdout, 'output'),
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


def _run_model_stream(stream_id, prompt, provider, model):
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
        _run_claude_cli_stream(stream_id, prompt, exec_timeout_seconds, started_at)
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


def create_model_stream(session_id, prompt, provider, model):
    stream_id = uuid.uuid4().hex
    created_at = time.time()
    stream = {
        'id': stream_id,
        'session_id': session_id,
        'provider': _normalize_provider_name(provider),
        'model': model,
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
        args=(stream_id, prompt, provider, model),
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


def start_model_stream_for_session(session_id, prompt, prompt_with_context):
    submit_lock = _get_session_submit_lock(session_id)
    with submit_lock:
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

        settings = get_settings()
        provider = _normalize_provider_name(settings.get('provider'))
        model = _normalize_model_name(provider, settings.get('model'))

        stream_info = create_model_stream(
            session_id,
            prompt_with_context,
            provider,
            model,
        )
        return {
            'ok': True,
            'stream_id': stream_info.get('id'),
            'started_at': stream_info.get('started_at') or stream_info.get('created_at'),
            'user_message': user_message,
        }


def list_model_streams(include_done=False):
    streams = []
    with state.model_streams_lock:
        for stream in state.model_streams.values():
            runtime = _snapshot_stream_runtime_locked(stream)
            if not include_done:
                if stream.get('done') or stream.get('cancelled'):
                    continue
            streams.append(
                {
                    'id': stream.get('id'),
                    'session_id': stream.get('session_id'),
                    'provider': stream.get('provider'),
                    'model': stream.get('model'),
                    'done': stream.get('done', False),
                    'cancelled': stream.get('cancelled', False),
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
        return {
            'output': output[output_offset:],
            'error': error[error_offset:],
            'output_length': int(stream.get('output_length') or len(output)),
            'error_length': int(stream.get('error_length') or len(error)),
            'done': stream['done'],
            'exit_code': stream['exit_code'],
            'saved': stream.get('saved', False),
            'session_id': stream['session_id'],
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
        final_output, patch_metadata = finalize_assistant_output(output)
        merged_metadata = dict(metadata or {})
        if isinstance(patch_metadata, dict):
            merged_metadata.update(patch_metadata)
        return append_message(
            session_id,
            'assistant',
            final_output,
            merged_metadata or None,
            created_at=created_at_value,
        )
    message_text = error or output or 'Model API 실행에 실패했습니다.'
    return append_message(
        session_id,
        'error',
        message_text,
        metadata or None,
        created_at=created_at_value,
    )


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
