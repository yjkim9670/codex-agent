"""Configuration and constants for Codex chat server."""

import json
import os
from datetime import timedelta, timezone
from pathlib import Path

try:
    import pwd
except ImportError:
    pwd = None

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


def _expand_path_value(value):
    token = str(value or '').strip()
    if not token:
        return None
    try:
        return Path(token).expanduser().resolve()
    except Exception:
        return Path(token).expanduser()


def _resolve_codex_home():
    configured_home = _expand_path_value(os.environ.get('CODEX_HOME'))
    if configured_home is not None:
        return configured_home
    return Path.home() / '.codex'


def _get_login_codex_home():
    if pwd is None:
        return None
    try:
        home_dir = pwd.getpwuid(os.getuid()).pw_dir
    except Exception:
        return None
    login_home = _expand_path_value(home_dir)
    if login_home is None:
        return None
    return login_home / '.codex'


def _unique_paths(paths):
    unique = []
    seen = set()
    for path in paths:
        if path is None:
            continue
        candidate = Path(path).expanduser()
        key = str(candidate)
        if not key or key in seen:
            continue
        unique.append(candidate)
        seen.add(key)
    return unique


def _parse_cli_text_env(name, max_chars=120):
    token = str(os.environ.get(name) or '').strip()
    if not token or '\x00' in token:
        return ''
    if len(token) > max_chars:
        return ''
    return token


def _parse_choice_env(name, default, allowed_values):
    token = _parse_cli_text_env(name, max_chars=80)
    if token in allowed_values:
        return token
    return default


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
CODEX_HOME = _resolve_codex_home()
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
CODEX_STREAM_IMAGEGEN_FINAL_RESPONSE_TIMEOUT_SECONDS = float(
    os.environ.get('CODEX_STREAM_IMAGEGEN_FINAL_RESPONSE_TIMEOUT_SECONDS', '180')
)
# `CODEX_CLI_SERIALIZE_EXEC` was used briefly as an opt-in global lock. Keep
# the runtime default lock-free even when that older environment variable leaks
# in from launch managers; use the explicit new name only for manual debugging.
CODEX_CLI_EXEC_LOCK = _parse_bool_env('CODEX_CLI_EXEC_LOCK', default=False)
CODEX_MAX_TITLE_CHARS = 80
CODEX_MAX_MODEL_CHARS = 80
CODEX_MAX_REASONING_CHARS = 40
CODEX_MAX_SERVICE_TIER_CHARS = 40
CODEX_MAX_AGENT_BACKEND_CHARS = 40
CODEX_CLI_PROFILE = _parse_cli_text_env('CODEX_CLI_PROFILE')
CODEX_CLI_MODEL_PROVIDER = _parse_cli_text_env('CODEX_CLI_MODEL_PROVIDER')
_CODEX_CLI_SANDBOX_VALUES = ('read-only', 'workspace-write', 'danger-full-access')
CODEX_CLI_SANDBOX = _parse_choice_env(
    'CODEX_CLI_SANDBOX',
    'workspace-write',
    _CODEX_CLI_SANDBOX_VALUES,
)
CODEX_CLI_READ_ONLY_SANDBOX = _parse_choice_env(
    'CODEX_CLI_READ_ONLY_SANDBOX',
    'read-only',
    _CODEX_CLI_SANDBOX_VALUES,
)


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


def _normalize_service_tier_options(options):
    normalized_options = []
    seen = set()
    for item in options:
        if isinstance(item, dict):
            tier_id = str(item.get('id') or '').strip()
            name = str(item.get('name') or item.get('label') or tier_id).strip()
            description = str(item.get('description') or '').strip()
        else:
            tier_id = str(item or '').strip()
            name = tier_id
            description = ''
        if not tier_id or tier_id in seen:
            continue
        normalized_options.append({
            'id': tier_id,
            'name': name or tier_id,
            'description': description,
        })
        seen.add(tier_id)
    return normalized_options


_DEFAULT_REASONING_OPTIONS = _normalize_reasoning_options(
    item.strip()
    for item in os.environ.get('CODEX_REASONING_OPTIONS', 'low,medium,high,xhigh').split(',')
    if item.strip()
)
_DEFAULT_SERVICE_TIER_OPTIONS = _normalize_service_tier_options([
    {
        'id': 'priority',
        'name': 'Fast',
        'description': '1.5x speed, increased usage',
    },
])
_AGENT_BACKEND_DEFINITIONS = {
    'dtgpt': {
        'id': 'dtgpt',
        'name': 'DTGPT',
        'description': 'Codex CLI',
    },
    'claude': {
        'id': 'claude',
        'name': 'Claude',
        'description': 'Claude CLI',
    },
}
_AGENT_BACKEND_ALIASES = {
    'codex': 'dtgpt',
    'codex-cli': 'dtgpt',
    'codex_cli': 'dtgpt',
    'dtgpt_oa': 'dtgpt',
    'anthropic': 'claude',
    'claude-cli': 'claude',
    'claude_cli': 'claude',
}
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


def normalize_codex_agent_backend(value):
    normalized = str(value or '').strip().lower()
    if not normalized:
        return ''
    normalized = _AGENT_BACKEND_ALIASES.get(normalized, normalized)
    if normalized not in _AGENT_BACKEND_DEFINITIONS:
        return ''
    return normalized


def _normalize_agent_backend_options(options):
    normalized_options = []
    seen = set()
    for item in options:
        backend_id = normalize_codex_agent_backend(item)
        if not backend_id or backend_id in seen:
            continue
        normalized_options.append(dict(_AGENT_BACKEND_DEFINITIONS[backend_id]))
        seen.add(backend_id)
    if not normalized_options:
        normalized_options.append(dict(_AGENT_BACKEND_DEFINITIONS['dtgpt']))
    return normalized_options


def get_codex_agent_backend_options():
    raw_options = str(os.environ.get('CODEX_AGENT_BACKEND_OPTIONS') or '').strip()
    requested = [
        item.strip()
        for item in raw_options.replace('\n', ',').split(',')
        if item.strip()
    ]
    default_backend = normalize_codex_agent_backend(os.environ.get('CODEX_AGENT_BACKEND'))
    requested_ids = {normalize_codex_agent_backend(item) for item in requested}
    if not requested:
        requested = [default_backend or 'dtgpt']
    elif default_backend and default_backend not in requested_ids:
        requested.insert(0, default_backend)
    return _normalize_agent_backend_options(requested)


def _build_model_catalog_entry(slug, default_reasoning_effort=None, reasoning_options=None):
    normalized_slug = normalize_codex_model_name(slug)
    if not normalized_slug:
        return None
    raw_reasoning_options = _DEFAULT_REASONING_OPTIONS if reasoning_options is None else reasoning_options
    normalized_reasoning_options = _normalize_reasoning_options(raw_reasoning_options)
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


def _iter_model_cache_paths():
    explicit_cache_path = _expand_path_value(os.environ.get('CODEX_MODEL_CACHE_PATH'))
    if explicit_cache_path is not None:
        return _unique_paths([explicit_cache_path])
    auth_home = _expand_path_value(os.environ.get('CODEX_WORKBENCH_AUTH_HOME'))
    env_home = _expand_path_value(os.environ.get('CODEX_HOME'))
    login_home = _get_login_codex_home()
    return _unique_paths([
        auth_home / 'models_cache.json' if auth_home is not None else None,
        env_home / 'models_cache.json' if env_home is not None else None,
        CODEX_HOME / 'models_cache.json',
        Path.home() / '.codex' / 'models_cache.json',
        login_home / 'models_cache.json' if login_home is not None else None,
    ])


def _read_model_catalog_from_models_cache_path(models_cache_path):
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


def _read_model_catalog_from_models_cache():
    catalog, _path = _read_model_catalog_with_source_from_models_cache()
    return catalog


def _read_model_catalog_with_source_from_models_cache():
    for models_cache_path in _iter_model_cache_paths():
        model_catalog = _read_model_catalog_from_models_cache_path(models_cache_path)
        if model_catalog:
            return model_catalog, models_cache_path
    return [], None


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
    cache_catalog, _cache_path = _read_model_catalog_with_source_from_models_cache()
    if env_options:
        return _select_model_catalog_entries(
            env_options,
            cache_catalog or _default_model_catalog,
        )
    if cache_catalog:
        return _normalize_model_catalog(cache_catalog)
    return _normalize_model_catalog(_default_model_catalog)


def get_codex_model_catalog_source():
    env_options = _read_model_options_from_env()
    cache_catalog, cache_path = _read_model_catalog_with_source_from_models_cache()
    if env_options:
        return {
            'type': 'env',
            'env': 'CODEX_MODEL_OPTIONS',
            'models_cache_path': str(cache_path) if cache_path else None,
        }
    if cache_catalog:
        return {
            'type': 'models_cache',
            'models_cache_path': str(cache_path),
        }
    return {
        'type': 'fallback',
        'models_cache_path': None,
        'model_cache_candidates': [str(path) for path in _iter_model_cache_paths()],
    }


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


def _read_claude_model_options_from_env():
    return _normalize_model_options(
        item.strip()
        for item in os.environ.get('CODEX_CLAUDE_MODEL_OPTIONS', '').split(',')
        if item.strip()
    )


def _iter_claude_settings_paths():
    candidates = []
    explicit_settings_path = _expand_path_value(os.environ.get('CODEX_CLAUDE_SETTINGS_PATH'))
    if explicit_settings_path is not None:
        candidates.append(explicit_settings_path)
    userprofile = _expand_path_value(os.environ.get('USERPROFILE'))
    if userprofile is not None:
        candidates.append(userprofile / '.claude' / 'settings.json')
    candidates.append(Path.home() / '.claude' / 'settings.json')
    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        yield path


def _read_claude_model_options_from_settings_path(settings_path):
    try:
        payload = json.loads(settings_path.read_text(encoding='utf-8'))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    raw_models = payload.get('availableModels')
    if not isinstance(raw_models, list):
        return []
    return _normalize_model_options(
        item.strip()
        for item in raw_models
        if isinstance(item, str) and item.strip()
    )


def _read_claude_model_options_from_settings():
    for settings_path in _iter_claude_settings_paths():
        model_options = _read_claude_model_options_from_settings_path(settings_path)
        if model_options:
            return model_options
    return []


def _read_claude_model_options():
    options = _read_claude_model_options_from_env()
    if not options:
        options = _read_claude_model_options_from_settings()
    default_model = normalize_codex_model_name(os.environ.get('CODEX_CLAUDE_MODEL'))
    if default_model and default_model not in options:
        options.insert(0, default_model)
    return options


def get_claude_model_catalog():
    return _normalize_model_catalog(
        {
            'slug': model_name,
            'default_reasoning_effort': None,
            'reasoning_options': [],
        }
        for model_name in _read_claude_model_options()
    )


def get_codex_model_catalog_for_backend(agent_backend=None):
    backend = normalize_codex_agent_backend(agent_backend) or 'dtgpt'
    if backend == 'claude':
        return get_claude_model_catalog()
    return get_codex_model_catalog()


def get_codex_model_options_for_backend(agent_backend=None):
    return [
        entry['slug']
        for entry in get_codex_model_catalog_for_backend(agent_backend)
    ]


def get_codex_reasoning_options_for_backend(agent_backend=None, model_name=None):
    backend = normalize_codex_agent_backend(agent_backend) or 'dtgpt'
    if backend == 'claude':
        return []
    return get_codex_reasoning_options(model_name=model_name)


def get_codex_model_catalogs_by_agent_backend():
    catalogs = {'dtgpt': get_codex_model_catalog()}
    option_ids = {
        str(item.get('id') or '').strip()
        for item in get_codex_agent_backend_options()
        if isinstance(item, dict)
    }
    if 'claude' in option_ids:
        catalogs['claude'] = get_claude_model_catalog()
    return catalogs


def get_codex_service_tier_options():
    if not _parse_bool_env('CODEX_ENABLE_SERVICE_TIER', default=True):
        return []
    return [dict(item) for item in _DEFAULT_SERVICE_TIER_OPTIONS]


def normalize_codex_service_tier(service_tier):
    if not _parse_bool_env('CODEX_ENABLE_SERVICE_TIER', default=True):
        return None
    normalized = str(service_tier or '').strip().lower()
    if normalized in {'', 'standard', 'default', 'auto'}:
        return None
    if normalized == 'fast':
        normalized = 'priority'
    allowed_ids = {item['id'] for item in _DEFAULT_SERVICE_TIER_OPTIONS}
    if normalized not in allowed_ids:
        return normalized
    return normalized


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
CODEX_SERVICE_TIER_OPTIONS = get_codex_service_tier_options()
CODEX_AGENT_BACKEND_OPTIONS = get_codex_agent_backend_options()
_CODEX_AGENT_BACKEND_IDS = tuple(
    item['id'] for item in CODEX_AGENT_BACKEND_OPTIONS if item.get('id')
)
_REQUESTED_AGENT_BACKEND = normalize_codex_agent_backend(os.environ.get('CODEX_AGENT_BACKEND'))
CODEX_AGENT_BACKEND_DEFAULT = (
    _REQUESTED_AGENT_BACKEND
    if _REQUESTED_AGENT_BACKEND in _CODEX_AGENT_BACKEND_IDS
    else (_CODEX_AGENT_BACKEND_IDS[0] if _CODEX_AGENT_BACKEND_IDS else 'dtgpt')
)

CODEX_ALLOWED_ORIGINS = _parse_allowed_origins(
    os.environ.get(
        'CODEX_ALLOWED_ORIGINS',
        'http://localhost:4000,http://127.0.0.1:4000',
    )
)
CODEX_API_ONLY_MODE = _parse_bool_env('CODEX_API_ONLY_MODE', default=False)
CODEX_ENABLE_FILES_API = _parse_bool_env('CODEX_ENABLE_FILES_API', default=True)
CODEX_REQUIRE_ENCRYPTED_FILE_WRITES = _parse_bool_env(
    'CODEX_REQUIRE_ENCRYPTED_FILE_WRITES',
    default=True,
)
CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS = _parse_bool_env(
    'CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS',
    default=True,
)
CODEX_SHOW_USAGE_LIMITS = _parse_bool_env('CODEX_SHOW_USAGE_LIMITS', default=True)
CODEX_ALLOW_TRUSTED_HTTP_CRYPTO_FALLBACK = _parse_bool_env(
    'CODEX_ALLOW_TRUSTED_HTTP_CRYPTO_FALLBACK',
    default=True,
)
CODEX_TRUSTED_HTTP_CRYPTO_FALLBACK_HOSTS = _parse_allowed_origins(
    os.environ.get(
        'CODEX_TRUSTED_HTTP_CRYPTO_FALLBACK_HOSTS',
        'localhost,*.localhost,127.0.0.1,127.0.0.0/8,::1,100.64.0.0/10,fd7a:115c:a1e0::/48,*.ts.net',
    )
)
CODEX_ENABLE_GIT_API = _parse_bool_env('CODEX_ENABLE_GIT_API', default=True)
CODEX_ENABLE_LEGACY_STATE_IMPORT = _parse_bool_env(
    'CODEX_ENABLE_LEGACY_STATE_IMPORT',
    default=False,
)
CODEX_SKIP_GIT_REPO_CHECK = _parse_bool_env('CODEX_SKIP_GIT_REPO_CHECK', default=False)
CODEX_CLI_SELF_PROTECT = _parse_bool_env('CODEX_CLI_SELF_PROTECT', default=False)
CODEX_CLI_SELF_PROTECT_GIT_RW = _parse_bool_env('CODEX_CLI_SELF_PROTECT_GIT_RW', default=False)
CODEX_CLI_PROTECTED_PATHS = _parse_path_list_env('CODEX_CLI_PROTECTED_PATHS')

CODEX_FILE_MAX_SINGLE_DOWNLOAD_BYTES = _parse_int_env(
    'CODEX_FILE_MAX_SINGLE_DOWNLOAD_BYTES',
    64 * 1024 * 1024,
    minimum=1024,
    maximum=512 * 1024 * 1024,
)
CODEX_FILE_MAX_ARCHIVE_DOWNLOAD_BYTES = _parse_int_env(
    'CODEX_FILE_MAX_ARCHIVE_DOWNLOAD_BYTES',
    128 * 1024 * 1024,
    minimum=1024,
    maximum=512 * 1024 * 1024,
)
CODEX_MAIL_SMTP_HOST = os.environ.get('CODEX_MAIL_SMTP_HOST', 'smtp.naver.com').strip() or 'smtp.naver.com'
CODEX_MAIL_SMTP_PORT = _parse_int_env('CODEX_MAIL_SMTP_PORT', 465, minimum=1, maximum=65535)
CODEX_MAIL_SMTP_SSL = _parse_bool_env('CODEX_MAIL_SMTP_SSL', default=True)
CODEX_MAIL_SMTP_STARTTLS = _parse_bool_env('CODEX_MAIL_SMTP_STARTTLS', default=not CODEX_MAIL_SMTP_SSL)
CODEX_MAIL_SMTP_TIMEOUT_SECONDS = _parse_int_env(
    'CODEX_MAIL_SMTP_TIMEOUT_SECONDS',
    30,
    minimum=5,
    maximum=120,
)
CODEX_MAIL_USERNAME = os.environ.get('CODEX_MAIL_USERNAME', 'kyjabc@naver.com').strip()
CODEX_MAIL_PASSWORD = os.environ.get('CODEX_MAIL_PASSWORD', '')
CODEX_MAIL_FROM = os.environ.get('CODEX_MAIL_FROM', CODEX_MAIL_USERNAME).strip()
CODEX_MAIL_FROM_NAME = os.environ.get('CODEX_MAIL_FROM_NAME', '').strip()
CODEX_MAIL_MAX_ARCHIVE_BYTES = _parse_int_env(
    'CODEX_MAIL_MAX_ARCHIVE_BYTES',
    20 * 1024 * 1024,
    minimum=1024,
    maximum=128 * 1024 * 1024,
)
CODEX_MAIL_MAX_ARCHIVE_ENTRIES = _parse_int_env(
    'CODEX_MAIL_MAX_ARCHIVE_ENTRIES',
    5000,
    minimum=1,
    maximum=100000,
)


def get_codex_security_policy():
    return {
        'chat_prompt_encryption_required': bool(CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS),
        'file_write_encryption_required': bool(CODEX_REQUIRE_ENCRYPTED_FILE_WRITES),
    }

KST = timezone(timedelta(hours=9))
KST_ZONEINFO = ZoneInfo('Asia/Seoul') if ZoneInfo else None

SECRET_KEY = os.environ.get('CODEX_CHAT_SECRET_KEY', 'codex-chat-secret-key-change-in-production')
