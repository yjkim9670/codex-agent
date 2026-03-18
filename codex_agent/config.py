"""Configuration and constants for Codex chat server."""

import os
from datetime import timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
_workspace_override = os.environ.get('CODEX_WORKSPACE_DIR')
if _workspace_override:
    WORKSPACE_DIR = Path(_workspace_override).expanduser().resolve()
else:
    WORKSPACE_DIR = REPO_ROOT / 'workspace'

CODEX_CHAT_STORE_PATH = WORKSPACE_DIR / 'codex_chat_sessions.json'
CODEX_HOME = Path.home() / '.codex'
CODEX_CONFIG_PATH = CODEX_HOME / 'config.toml'
CODEX_SESSIONS_PATH = CODEX_HOME / 'sessions'
CODEX_SETTINGS_PATH = WORKSPACE_DIR / 'codex_settings.json'
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
_default_model_options = sorted({
    'gpt-5.1-codex-max',
    'gpt-5.2',
    'gpt-5.2-codex',
    'gpt-5.3-codex',
    'gpt-5.3-codex-spark',
    'gpt-5.4'
})
CODEX_MODEL_OPTIONS = [
    item.strip()
    for item in os.environ.get('CODEX_MODEL_OPTIONS', '').split(',')
    if item.strip()
]
if not CODEX_MODEL_OPTIONS:
    CODEX_MODEL_OPTIONS = _default_model_options
CODEX_REASONING_OPTIONS = [
    item.strip()
    for item in os.environ.get('CODEX_REASONING_OPTIONS', 'low,medium,high,xhigh').split(',')
    if item.strip()
]

CODEX_SKIP_GIT_REPO_CHECK = os.environ.get('CODEX_SKIP_GIT_REPO_CHECK', '').strip().lower() in {
    '1',
    'true',
    'yes',
    'on'
}

KST = timezone(timedelta(hours=9))
KST_ZONEINFO = ZoneInfo('Asia/Seoul') if ZoneInfo else None

SECRET_KEY = os.environ.get('CODEX_CHAT_SECRET_KEY', 'codex-chat-secret-key-change-in-production')
