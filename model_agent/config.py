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
MODEL_MAX_REASONING_CHARS = _read_positive_int_env('MODEL_MAX_REASONING_CHARS', 40)

MODEL_DEFAULT_PROVIDER = os.environ.get('MODEL_DEFAULT_PROVIDER', 'gemini').strip().lower() or 'gemini'
_default_provider_options = ['gemini', 'openai', 'kimi', 'glm']
MODEL_PROVIDER_OPTIONS = _read_csv_env('MODEL_PROVIDER_OPTIONS')
if not MODEL_PROVIDER_OPTIONS:
    MODEL_PROVIDER_OPTIONS = list(_default_provider_options)
if MODEL_DEFAULT_PROVIDER not in MODEL_PROVIDER_OPTIONS:
    MODEL_PROVIDER_OPTIONS.insert(0, MODEL_DEFAULT_PROVIDER)

MODEL_GEMINI_API_KEY = os.environ.get('MODEL_GEMINI_API_KEY', os.environ.get('MODEL_API_KEY', '')).strip()
MODEL_GEMINI_API_BASE_URL = (
    os.environ.get('MODEL_GEMINI_API_BASE_URL', os.environ.get('MODEL_API_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta')).strip().rstrip('/')
    or 'https://generativelanguage.googleapis.com/v1beta'
)
MODEL_OPENAI_API_KEY = os.environ.get('MODEL_OPENAI_API_KEY', '').strip()
MODEL_OPENAI_API_BASE_URL = (
    os.environ.get('MODEL_OPENAI_API_BASE_URL', 'https://api.openai.com/v1').strip().rstrip('/')
    or 'https://api.openai.com/v1'
)
MODEL_KIMI_API_KEY = os.environ.get('MODEL_KIMI_API_KEY', '').strip()
MODEL_KIMI_API_BASE_URL = (
    os.environ.get('MODEL_KIMI_API_BASE_URL', 'https://api.moonshot.cn/v1').strip().rstrip('/')
    or 'https://api.moonshot.cn/v1'
)
MODEL_GLM_API_KEY = os.environ.get('MODEL_GLM_API_KEY', '').strip()
MODEL_GLM_API_BASE_URL = (
    os.environ.get('MODEL_GLM_API_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4').strip().rstrip('/')
    or 'https://open.bigmodel.cn/api/paas/v4'
)

MODEL_GEMINI_DEFAULT_MODEL = (
    os.environ.get('MODEL_GEMINI_DEFAULT_MODEL', os.environ.get('MODEL_DEFAULT_MODEL', 'gemini-flash-latest')).strip()
    or 'gemini-flash-latest'
)
MODEL_OPENAI_DEFAULT_MODEL = os.environ.get('MODEL_OPENAI_DEFAULT_MODEL', 'gpt-5.4').strip() or 'gpt-5.4'
MODEL_KIMI_DEFAULT_MODEL = os.environ.get('MODEL_KIMI_DEFAULT_MODEL', 'kimi-k2-0905-preview').strip() or 'kimi-k2-0905-preview'
MODEL_GLM_DEFAULT_MODEL = os.environ.get('MODEL_GLM_DEFAULT_MODEL', 'glm-5').strip() or 'glm-5'
MODEL_PROVIDER_DEFAULT_MODELS = {
    'gemini': MODEL_GEMINI_DEFAULT_MODEL,
    'openai': MODEL_OPENAI_DEFAULT_MODEL,
    'kimi': MODEL_KIMI_DEFAULT_MODEL,
    'glm': MODEL_GLM_DEFAULT_MODEL,
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

_default_openai_model_options = sorted({
    MODEL_OPENAI_DEFAULT_MODEL,
    'gpt-5.3-codex',
    'gpt-5.2-codex',
    'gpt-5.2',
})
MODEL_OPENAI_MODEL_OPTIONS = _read_csv_env('MODEL_OPENAI_MODEL_OPTIONS')
if not MODEL_OPENAI_MODEL_OPTIONS:
    MODEL_OPENAI_MODEL_OPTIONS = _default_openai_model_options

_default_kimi_model_options = sorted({
    MODEL_KIMI_DEFAULT_MODEL,
    'kimi-k2-turbo-preview',
    'kimi-latest',
    'kimi-thinking-preview',
})
MODEL_KIMI_MODEL_OPTIONS = _read_csv_env('MODEL_KIMI_MODEL_OPTIONS')
if not MODEL_KIMI_MODEL_OPTIONS:
    MODEL_KIMI_MODEL_OPTIONS = _default_kimi_model_options

_default_glm_model_options = sorted({
    MODEL_GLM_DEFAULT_MODEL,
    'glm-4.7',
    'glm-4.7-flash',
    'glm-4.7-flashx',
})
MODEL_GLM_MODEL_OPTIONS = _read_csv_env('MODEL_GLM_MODEL_OPTIONS')
if not MODEL_GLM_MODEL_OPTIONS:
    MODEL_GLM_MODEL_OPTIONS = _default_glm_model_options

MODEL_PROVIDER_MODEL_OPTIONS = {
    'gemini': MODEL_GEMINI_MODEL_OPTIONS,
    'openai': MODEL_OPENAI_MODEL_OPTIONS,
    'kimi': MODEL_KIMI_MODEL_OPTIONS,
    'glm': MODEL_GLM_MODEL_OPTIONS,
}

MODEL_REASONING_OPTIONS = _read_csv_env('MODEL_REASONING_OPTIONS')
if not MODEL_REASONING_OPTIONS:
    MODEL_REASONING_OPTIONS = ['default', 'auto_edit', 'yolo', 'low', 'medium', 'high', 'xhigh']

KST = timezone(timedelta(hours=9))
KST_ZONEINFO = ZoneInfo('Asia/Seoul') if ZoneInfo else None

SECRET_KEY = os.environ.get('MODEL_CHAT_SECRET_KEY', 'model-chat-secret-key-change-in-production')
