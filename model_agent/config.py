"""Configuration and constants for Model Agent server."""

import os
from datetime import timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
_workspace_override = os.environ.get('MODEL_WORKSPACE_DIR')
if _workspace_override:
    WORKSPACE_DIR = Path(_workspace_override).expanduser().resolve()
else:
    WORKSPACE_DIR = REPO_ROOT / 'workspace'


def _read_positive_int_env(name, default, minimum=1):
    raw_value = os.environ.get(name, '').strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    if parsed < minimum:
        return default
    return parsed


def _read_csv_env(name):
    raw = os.environ.get(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


def _normalize_relative_prefix(value):
    token = str(value or '').strip().replace('\\', '/')
    while token.startswith('./'):
        token = token[2:]
    token = token.strip().strip('/')
    if not token:
        return ''
    if token.startswith('/') or token.startswith('../') or '/..' in token:
        return ''
    return token


MODEL_CHAT_STORE_PATH = WORKSPACE_DIR / 'model_chat_sessions.json'
MODEL_SETTINGS_PATH = WORKSPACE_DIR / 'model_settings.json'
MODEL_USAGE_SNAPSHOT_PATH = WORKSPACE_DIR / 'model_usage_summary.json'
LEGACY_MODEL_CHAT_STORE_PATH = WORKSPACE_DIR / 'gemini_chat_sessions.json'
LEGACY_MODEL_SETTINGS_PATH = WORKSPACE_DIR / 'gemini_settings.json'
LEGACY_MODEL_USAGE_SNAPSHOT_PATH = WORKSPACE_DIR / 'gemini_usage_summary.json'

MODEL_MAX_PROMPT_CHARS = _read_positive_int_env('MODEL_MAX_PROMPT_CHARS', 4000)
MODEL_CONTEXT_MAX_CHARS = _read_positive_int_env('MODEL_CONTEXT_MAX_CHARS', 12000)
MODEL_EXEC_TIMEOUT_SECONDS = _read_positive_int_env('MODEL_EXEC_TIMEOUT_SECONDS', 600)
MODEL_API_TIMEOUT_SECONDS = _read_positive_int_env('MODEL_API_TIMEOUT_SECONDS', MODEL_EXEC_TIMEOUT_SECONDS)
MODEL_STREAM_TTL_SECONDS = _read_positive_int_env('MODEL_STREAM_TTL_SECONDS', 900)
MODEL_MAX_TITLE_CHARS = _read_positive_int_env('MODEL_MAX_TITLE_CHARS', 80)
MODEL_MAX_PROVIDER_CHARS = _read_positive_int_env('MODEL_MAX_PROVIDER_CHARS', 32)
MODEL_MAX_MODEL_CHARS = _read_positive_int_env('MODEL_MAX_MODEL_CHARS', 80)

MODEL_DEFAULT_PROVIDER = os.environ.get('MODEL_DEFAULT_PROVIDER', 'gemini').strip().lower() or 'gemini'
_default_provider_options = ['gemini', 'dtgpt']
MODEL_PROVIDER_OPTIONS = _read_csv_env('MODEL_PROVIDER_OPTIONS')
if not MODEL_PROVIDER_OPTIONS:
    MODEL_PROVIDER_OPTIONS = list(_default_provider_options)
if MODEL_DEFAULT_PROVIDER not in MODEL_PROVIDER_OPTIONS:
    MODEL_PROVIDER_OPTIONS.insert(0, MODEL_DEFAULT_PROVIDER)

_workspace_blocked_paths = []
for item in _read_csv_env('MODEL_WORKSPACE_BLOCKED_PATHS'):
    normalized = _normalize_relative_prefix(item)
    if normalized and normalized not in _workspace_blocked_paths:
        _workspace_blocked_paths.append(normalized)
if not _workspace_blocked_paths:
    try:
        relative_repo_path = REPO_ROOT.resolve().relative_to(WORKSPACE_DIR.resolve()).as_posix()
    except ValueError:
        relative_repo_path = ''
    normalized_repo_path = _normalize_relative_prefix(relative_repo_path)
    if normalized_repo_path:
        _workspace_blocked_paths.append(normalized_repo_path)
MODEL_WORKSPACE_BLOCKED_PATHS = _workspace_blocked_paths

MODEL_GEMINI_API_KEY = os.environ.get('MODEL_GEMINI_API_KEY', os.environ.get('MODEL_API_KEY', '')).strip()
MODEL_GEMINI_API_BASE_URL = (
    os.environ.get('MODEL_GEMINI_API_BASE_URL', os.environ.get('MODEL_API_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta')).strip().rstrip('/')
    or 'https://generativelanguage.googleapis.com/v1beta'
)
MODEL_DTGPT_API_KEY = os.environ.get('MODEL_DTGPT_API_KEY', '').strip()
MODEL_DTGPT_API_KEY_ENV = os.environ.get('MODEL_DTGPT_API_KEY_ENV', 'DTGPT_API_KEY').strip() or 'DTGPT_API_KEY'
MODEL_DTGPT_API_KEY_HEADER = os.environ.get('MODEL_DTGPT_API_KEY_HEADER', 'Authorization').strip() or 'Authorization'
MODEL_DTGPT_API_KEY_PREFIX = os.environ.get('MODEL_DTGPT_API_KEY_PREFIX', 'Bearer').strip() or 'Bearer'
MODEL_DTGPT_API_BASE_URL = (
    os.environ.get('MODEL_DTGPT_API_BASE_URL', 'http://cloud.dtgpt.samsungds.net/llm/v1').strip().rstrip('/')
    or 'http://cloud.dtgpt.samsungds.net/llm/v1'
)
MODEL_DTGPT_API_BASE_URLS = _read_csv_env('MODEL_DTGPT_API_BASE_URLS')
if not MODEL_DTGPT_API_BASE_URLS:
    MODEL_DTGPT_API_BASE_URLS = [
        MODEL_DTGPT_API_BASE_URL,
        'https://cloud.dtgpt.samsungds.net/llm/v1',
    ]

MODEL_GEMINI_DEFAULT_MODEL = (
    os.environ.get('MODEL_GEMINI_DEFAULT_MODEL', os.environ.get('MODEL_DEFAULT_MODEL', 'gemini-flash-latest')).strip()
    or 'gemini-flash-latest'
)
MODEL_DTGPT_DEFAULT_MODEL = os.environ.get('MODEL_DTGPT_DEFAULT_MODEL', 'Kimi-K2.5').strip() or 'Kimi-K2.5'
MODEL_PROVIDER_DEFAULT_MODELS = {
    'gemini': MODEL_GEMINI_DEFAULT_MODEL,
    'dtgpt': MODEL_DTGPT_DEFAULT_MODEL,
}
MODEL_DEFAULT_MODEL = MODEL_PROVIDER_DEFAULT_MODELS.get(MODEL_DEFAULT_PROVIDER, MODEL_GEMINI_DEFAULT_MODEL)

_default_gemini_model_options = sorted({
    MODEL_GEMINI_DEFAULT_MODEL,
    'gemini-flash-lite-latest',
    'gemini-pro-latest',
    'gemini-3.1-pro-preview',
})
MODEL_GEMINI_MODEL_OPTIONS = _read_csv_env('MODEL_GEMINI_MODEL_OPTIONS')
if not MODEL_GEMINI_MODEL_OPTIONS:
    MODEL_GEMINI_MODEL_OPTIONS = _default_gemini_model_options

_default_dtgpt_model_options = sorted({
    MODEL_DTGPT_DEFAULT_MODEL,
    'GLM4.7',
    'Kimi-K2.5',
    'openai/gpt-oss-120b',
})
MODEL_DTGPT_MODEL_OPTIONS = _read_csv_env('MODEL_DTGPT_MODEL_OPTIONS')
if not MODEL_DTGPT_MODEL_OPTIONS:
    MODEL_DTGPT_MODEL_OPTIONS = _default_dtgpt_model_options

MODEL_PROVIDER_MODEL_OPTIONS = {
    'gemini': MODEL_GEMINI_MODEL_OPTIONS,
    'dtgpt': MODEL_DTGPT_MODEL_OPTIONS,
}

KST = timezone(timedelta(hours=9))
KST_ZONEINFO = ZoneInfo('Asia/Seoul') if ZoneInfo else None

SECRET_KEY = os.environ.get('MODEL_CHAT_SECRET_KEY', 'model-chat-secret-key-change-in-production')
