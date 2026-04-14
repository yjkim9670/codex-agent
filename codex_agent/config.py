"""Configuration and constants for Codex chat server."""

import os
from datetime import timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

_TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}
_FALSY_VALUES = {'0', 'false', 'no', 'off'}


def _parse_bool_env(name, default=False):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    token = str(raw_value).strip().lower()
    if not token:
        return default
    if token in _TRUTHY_VALUES:
        return True
    if token in _FALSY_VALUES:
        return False
    return default


def _parse_allowed_origins(raw_value):
    text = str(raw_value or '').strip()
    if not text:
        return tuple()
    normalized_origins = []
    seen = set()
    for chunk in text.replace('\n', ',').split(','):
        origin = chunk.strip()
        if not origin or origin in seen:
            continue
        normalized_origins.append(origin)
        seen.add(origin)
    return tuple(normalized_origins)


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
_workspace_override = os.environ.get('CODEX_WORKSPACE_DIR')
if _workspace_override:
    WORKSPACE_DIR = Path(_workspace_override).expanduser().resolve()
else:
    WORKSPACE_DIR = REPO_ROOT / 'workspace'


def _normalize_storage_subdir(value, default='.agent_state'):
    token = str(value or '').strip().replace('\\', '/')
    while token.startswith('./'):
        token = token[2:]
    token = token.strip().strip('/')
    if not token:
        return default
    if token.startswith('/') or token.startswith('../') or '/..' in token:
        return default
    return token


def _default_storage_subdir():
    if WORKSPACE_DIR.resolve() == REPO_ROOT.parent.resolve():
        return f'{REPO_ROOT.name}/workspace/.agent_state'
    return '.agent_state'


def _uses_parent_workspace_storage():
    try:
        return WORKSPACE_DIR.resolve() == REPO_ROOT.parent.resolve()
    except Exception:
        return False


CODEX_STORAGE_SUBDIR = _normalize_storage_subdir(
    os.environ.get('CODEX_STORAGE_SUBDIR'),
    default=_default_storage_subdir(),
)
# Keep parent-workspace Codex state under the repo-local standard storage path.
# A bare ".agent_state" at the workspace root is a legacy location that can
# split chat history across two stores when old environment values leak in.
if _uses_parent_workspace_storage() and CODEX_STORAGE_SUBDIR == '.agent_state':
    CODEX_STORAGE_SUBDIR = _default_storage_subdir()
CODEX_STORAGE_DIR = WORKSPACE_DIR / CODEX_STORAGE_SUBDIR
LEGACY_CODEX_CHAT_STORE_PATH = WORKSPACE_DIR / 'codex_chat_sessions.json'
LEGACY_CODEX_SETTINGS_PATH = WORKSPACE_DIR / 'codex_settings.json'
LEGACY_CODEX_TOKEN_USAGE_PATH = WORKSPACE_DIR / 'codex_token_usage.json'
LEGACY_CODEX_USAGE_HISTORY_PATH = WORKSPACE_DIR / 'codex_usage_history.json'
CODEX_CHAT_STORE_PATH = CODEX_STORAGE_DIR / 'codex_chat_sessions.json'
CODEX_HOME = Path.home() / '.codex'
CODEX_CONFIG_PATH = CODEX_HOME / 'config.toml'
CODEX_SESSIONS_PATH = CODEX_HOME / 'sessions'
CODEX_SETTINGS_PATH = CODEX_STORAGE_DIR / 'codex_settings.json'
CODEX_TOKEN_USAGE_PATH = CODEX_STORAGE_DIR / 'codex_token_usage.json'
CODEX_ACCOUNT_TOKEN_USAGE_PATH = CODEX_HOME / 'codex_account_token_usage.json'
CODEX_USAGE_HISTORY_PATH = CODEX_STORAGE_DIR / 'codex_usage_history.json'
CODEX_MAX_PROMPT_CHARS = 4000
CODEX_CONTEXT_MAX_CHARS = 12000
CODEX_STREAM_TTL_SECONDS = 900
CODEX_STREAM_POLL_INTERVAL_SECONDS = float(os.environ.get('CODEX_STREAM_POLL_INTERVAL_SECONDS', '0.5'))
CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS = float(os.environ.get('CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', '15'))
CODEX_STREAM_TERMINATE_GRACE_SECONDS = float(os.environ.get('CODEX_STREAM_TERMINATE_GRACE_SECONDS', '3'))
CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS = float(
    os.environ.get('CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', '60')
)
CODEX_MAX_TITLE_CHARS = 80
CODEX_MAX_MODEL_CHARS = 80
CODEX_MAX_REASONING_CHARS = 40
CODEX_MODEL_ALIASES = {
    'gpt-5.3-codex-spark': 'gpt-5.3-codex-mini'
}


def normalize_codex_model_name(model_name):
    normalized = str(model_name or '').strip()
    if not normalized:
        return ''
    return CODEX_MODEL_ALIASES.get(normalized, normalized)


def _normalize_model_options(options):
    normalized_options = []
    seen = set()
    for item in options:
        normalized = normalize_codex_model_name(item)
        if not normalized or normalized in seen:
            continue
        normalized_options.append(normalized)
        seen.add(normalized)
    return normalized_options


_default_model_options = sorted(_normalize_model_options([
    'gpt-5.1-codex-max',
    'gpt-5.2',
    'gpt-5.2-codex',
    'gpt-5.3-codex',
    'gpt-5.3-codex-mini',
    'gpt-5.4'
]))
CODEX_MODEL_OPTIONS = _normalize_model_options(
    item.strip()
    for item in os.environ.get('CODEX_MODEL_OPTIONS', '').split(',')
    if item.strip()
)
if not CODEX_MODEL_OPTIONS:
    CODEX_MODEL_OPTIONS = _default_model_options
CODEX_REASONING_OPTIONS = [
    item.strip()
    for item in os.environ.get('CODEX_REASONING_OPTIONS', 'low,medium,high,xhigh').split(',')
    if item.strip()
]

CODEX_ALLOWED_ORIGINS = _parse_allowed_origins(
    os.environ.get(
        'CODEX_ALLOWED_ORIGINS',
        'http://localhost:4000,http://127.0.0.1:4000',
    )
)
CODEX_API_ONLY_MODE = _parse_bool_env('CODEX_API_ONLY_MODE', default=False)
CODEX_ENABLE_FILES_API = _parse_bool_env('CODEX_ENABLE_FILES_API', default=True)
CODEX_ENABLE_GIT_API = _parse_bool_env('CODEX_ENABLE_GIT_API', default=True)
CODEX_SKIP_GIT_REPO_CHECK = _parse_bool_env('CODEX_SKIP_GIT_REPO_CHECK', default=False)

KST = timezone(timedelta(hours=9))
KST_ZONEINFO = ZoneInfo('Asia/Seoul') if ZoneInfo else None

SECRET_KEY = os.environ.get('CODEX_CHAT_SECRET_KEY', 'codex-chat-secret-key-change-in-production')
