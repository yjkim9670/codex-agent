"""Configuration and constants for Codex chat server."""

import json
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


def _parse_int_env(name, default, minimum=None, maximum=None):
    raw_value = os.environ.get(name)
    try:
        parsed = int(str(raw_value).strip()) if raw_value is not None else int(default)
    except (TypeError, ValueError):
        parsed = int(default)
    if minimum is not None:
        parsed = max(int(minimum), parsed)
    if maximum is not None:
        parsed = min(int(maximum), parsed)
    return parsed


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


def _parse_path_list_env(name):
    raw_value = os.environ.get(name)
    text = str(raw_value or '').strip()
    if not text:
        return tuple()
    paths = []
    seen = set()
    for chunk in text.replace('\n', ',').split(','):
        token = chunk.strip()
        if not token:
            continue
        try:
            path = Path(token).expanduser().resolve()
        except Exception:
            path = Path(token).expanduser()
        key = str(path)
        if key in seen:
            continue
        paths.append(path)
        seen.add(key)
    return tuple(paths)


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
CODEX_MAX_ATTACHMENTS_PER_TURN = _parse_int_env('CODEX_MAX_ATTACHMENTS_PER_TURN', 8, minimum=0, maximum=32)
CODEX_MAX_ATTACHMENT_BYTES = _parse_int_env(
    'CODEX_MAX_ATTACHMENT_BYTES',
    20 * 1024 * 1024,
    minimum=1024,
    maximum=128 * 1024 * 1024,
)
CODEX_STREAM_TTL_SECONDS = 900
CODEX_STREAM_POLL_INTERVAL_SECONDS = float(os.environ.get('CODEX_STREAM_POLL_INTERVAL_SECONDS', '0.5'))
CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS = float(os.environ.get('CODEX_STREAM_POST_OUTPUT_IDLE_SECONDS', '15'))
CODEX_STREAM_TERMINATE_GRACE_SECONDS = float(os.environ.get('CODEX_STREAM_TERMINATE_GRACE_SECONDS', '3'))
CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS = float(
    os.environ.get('CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS', '15')
)
CODEX_MAX_TITLE_CHARS = 80
CODEX_MAX_MODEL_CHARS = 80
CODEX_MAX_REASONING_CHARS = 40


def _normalize_reasoning_options(options):
    normalized_options = []
    seen = set()
    for item in options:
        normalized = str(item or '').strip()
        if not normalized or normalized in seen:
            continue
        normalized_options.append(normalized)
        seen.add(normalized)
    return normalized_options


_DEFAULT_REASONING_OPTIONS = _normalize_reasoning_options(
    item.strip()
    for item in os.environ.get('CODEX_REASONING_OPTIONS', 'low,medium,high,xhigh').split(',')
    if item.strip()
)
CODEX_MODEL_ALIASES = {
    # Keep backward compatibility for legacy saved settings.
    'gpt-5.3-codex-mini': 'gpt-5.3-codex-spark',
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


def _build_model_catalog_entry(slug, default_reasoning_effort=None, reasoning_options=None):
    normalized_slug = normalize_codex_model_name(slug)
    if not normalized_slug:
        return None
    normalized_reasoning_options = _normalize_reasoning_options(
        reasoning_options or _DEFAULT_REASONING_OPTIONS
    )
    normalized_default_reasoning = str(default_reasoning_effort or '').strip()
    if normalized_default_reasoning and normalized_default_reasoning not in normalized_reasoning_options:
        normalized_reasoning_options.insert(0, normalized_default_reasoning)
    if not normalized_default_reasoning and normalized_reasoning_options:
        normalized_default_reasoning = normalized_reasoning_options[0]
    return {
        'slug': normalized_slug,
        'default_reasoning_effort': normalized_default_reasoning or None,
        'reasoning_options': normalized_reasoning_options,
    }


def _clone_model_catalog_entry(entry):
    if not isinstance(entry, dict):
        return None
    catalog_entry = _build_model_catalog_entry(
        entry.get('slug'),
        default_reasoning_effort=entry.get('default_reasoning_effort'),
        reasoning_options=entry.get('reasoning_options'),
    )
    if not catalog_entry:
        return None
    return catalog_entry


def _normalize_model_catalog(entries):
    normalized_catalog = []
    seen = set()
    for entry in entries:
        catalog_entry = _clone_model_catalog_entry(entry)
        if not catalog_entry:
            continue
        slug = catalog_entry['slug']
        if slug in seen:
            continue
        normalized_catalog.append(catalog_entry)
        seen.add(slug)
    return normalized_catalog


_default_model_catalog = _normalize_model_catalog([
    {
        'slug': 'gpt-5.4',
        'default_reasoning_effort': 'medium',
        'reasoning_options': _DEFAULT_REASONING_OPTIONS,
    },
    {
        'slug': 'gpt-5.4-mini',
        'default_reasoning_effort': 'medium',
        'reasoning_options': _DEFAULT_REASONING_OPTIONS,
    },
    {
        'slug': 'gpt-5.3-codex',
        'default_reasoning_effort': 'medium',
        'reasoning_options': _DEFAULT_REASONING_OPTIONS,
    },
    {
        'slug': 'gpt-5.3-codex-spark',
        'default_reasoning_effort': 'high',
        'reasoning_options': _DEFAULT_REASONING_OPTIONS,
    },
    {
        'slug': 'gpt-5.2',
        'default_reasoning_effort': 'medium',
        'reasoning_options': _DEFAULT_REASONING_OPTIONS,
    },
])
_default_model_catalog_by_slug = {
    entry['slug']: entry
    for entry in _default_model_catalog
}


def _read_model_options_from_env():
    return _normalize_model_options(
        item.strip()
        for item in os.environ.get('CODEX_MODEL_OPTIONS', '').split(',')
        if item.strip()
    )


def _read_model_options_from_models_cache():
    return [
        entry['slug']
        for entry in _read_model_catalog_from_models_cache()
    ]


def _read_model_catalog_from_models_cache():
    models_cache_path = CODEX_HOME / 'models_cache.json'
    try:
        payload = json.loads(models_cache_path.read_text(encoding='utf-8'))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    raw_models = payload.get('models')
    if not isinstance(raw_models, list):
        return []
    model_catalog = []
    seen = set()
    for entry in raw_models:
        if not isinstance(entry, dict):
            continue
        visibility = str(entry.get('visibility') or '').strip().lower()
        if visibility != 'list':
            continue
        slug = entry.get('slug') or entry.get('display_name')
        if not slug:
            continue
        catalog_entry = _build_model_catalog_entry(
            slug,
            default_reasoning_effort=entry.get('default_reasoning_level'),
            reasoning_options=[
                item.get('effort') if isinstance(item, dict) else item
                for item in entry.get('supported_reasoning_levels') or []
            ],
        )
        if not catalog_entry:
            continue
        normalized_slug = catalog_entry['slug']
        if normalized_slug in seen:
            continue
        model_catalog.append(catalog_entry)
        seen.add(normalized_slug)
    return model_catalog


def _select_model_catalog_entries(model_options, source_catalog):
    source_map = {
        entry['slug']: entry
        for entry in _normalize_model_catalog(source_catalog)
    }
    selected_catalog = []
    seen = set()
    for item in model_options:
        slug = normalize_codex_model_name(item)
        if not slug or slug in seen:
            continue
        catalog_entry = _clone_model_catalog_entry(
            source_map.get(slug)
            or _default_model_catalog_by_slug.get(slug)
            or {'slug': slug}
        )
        if not catalog_entry:
            continue
        selected_catalog.append(catalog_entry)
        seen.add(slug)
    return selected_catalog


def get_codex_model_catalog():
    env_options = _read_model_options_from_env()
    cache_catalog = _read_model_catalog_from_models_cache()
    if env_options:
        return _select_model_catalog_entries(
            env_options,
            cache_catalog or _default_model_catalog,
        )
    if cache_catalog:
        return _normalize_model_catalog(cache_catalog)
    return _normalize_model_catalog(_default_model_catalog)


def get_codex_model_options():
    return [
        entry['slug']
        for entry in get_codex_model_catalog()
    ]


def get_codex_model_metadata(model_name):
    normalized_model_name = normalize_codex_model_name(model_name)
    if not normalized_model_name:
        return None
    for entry in get_codex_model_catalog():
        if entry['slug'] == normalized_model_name:
            return entry
    fallback_entry = _default_model_catalog_by_slug.get(normalized_model_name)
    return _clone_model_catalog_entry(fallback_entry)


def get_codex_default_reasoning_effort(model_name):
    metadata = get_codex_model_metadata(model_name)
    if not metadata:
        return None
    default_reasoning = str(metadata.get('default_reasoning_effort') or '').strip()
    return default_reasoning or None


def get_codex_reasoning_options(model_name=None):
    metadata = get_codex_model_metadata(model_name) if model_name else None
    if metadata and metadata.get('reasoning_options'):
        return list(metadata['reasoning_options'])
    if model_name:
        return list(_DEFAULT_REASONING_OPTIONS)
    reasoning_options = _normalize_reasoning_options(
        item
        for entry in get_codex_model_catalog()
        for item in entry.get('reasoning_options') or []
    )
    if reasoning_options:
        return reasoning_options
    return list(_DEFAULT_REASONING_OPTIONS)


def resolve_codex_reasoning_effort(model_name=None, reasoning_effort=None):
    normalized_reasoning = str(reasoning_effort or '').strip()
    supported_reasoning = get_codex_reasoning_options(model_name=model_name)
    if normalized_reasoning:
        if supported_reasoning and normalized_reasoning not in supported_reasoning:
            return get_codex_default_reasoning_effort(model_name) or normalized_reasoning
        return normalized_reasoning
    return get_codex_default_reasoning_effort(model_name)


CODEX_MODEL_OPTIONS = get_codex_model_options()
CODEX_REASONING_OPTIONS = get_codex_reasoning_options()

CODEX_ALLOWED_ORIGINS = _parse_allowed_origins(
    os.environ.get(
        'CODEX_ALLOWED_ORIGINS',
        'http://localhost:4000,http://127.0.0.1:4000',
    )
)
CODEX_API_ONLY_MODE = _parse_bool_env('CODEX_API_ONLY_MODE', default=False)
CODEX_ENABLE_FILES_API = _parse_bool_env('CODEX_ENABLE_FILES_API', default=True)
CODEX_ENABLE_GIT_API = _parse_bool_env('CODEX_ENABLE_GIT_API', default=True)
CODEX_ENABLE_LEGACY_STATE_IMPORT = _parse_bool_env(
    'CODEX_ENABLE_LEGACY_STATE_IMPORT',
    default=False,
)
CODEX_SKIP_GIT_REPO_CHECK = _parse_bool_env('CODEX_SKIP_GIT_REPO_CHECK', default=False)
CODEX_CLI_SELF_PROTECT = _parse_bool_env('CODEX_CLI_SELF_PROTECT', default=False)
CODEX_CLI_PROTECTED_PATHS = _parse_path_list_env('CODEX_CLI_PROTECTED_PATHS')

KST = timezone(timedelta(hours=9))
KST_ZONEINFO = ZoneInfo('Asia/Seoul') if ZoneInfo else None

SECRET_KEY = os.environ.get('CODEX_CHAT_SECRET_KEY', 'codex-chat-secret-key-change-in-production')
