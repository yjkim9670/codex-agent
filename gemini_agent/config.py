"""Configuration and constants for Gemini chat server."""

import os
from datetime import timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
_workspace_override = os.environ.get('GEMINI_WORKSPACE_DIR')
if _workspace_override:
    WORKSPACE_DIR = Path(_workspace_override).expanduser().resolve()
else:
    WORKSPACE_DIR = REPO_ROOT / 'workspace'

GEMINI_CHAT_STORE_PATH = WORKSPACE_DIR / 'gemini_chat_sessions.json'
GEMINI_HOME = Path.home() / '.gemini'
GEMINI_CONFIG_PATH = GEMINI_HOME / 'config.toml'
GEMINI_SESSIONS_PATH = GEMINI_HOME / 'sessions'
GEMINI_SETTINGS_PATH = WORKSPACE_DIR / 'gemini_settings.json'
GEMINI_MAX_PROMPT_CHARS = 4000
GEMINI_CONTEXT_MAX_CHARS = 12000
GEMINI_EXEC_TIMEOUT_SECONDS = 600
GEMINI_STREAM_TTL_SECONDS = 900
GEMINI_MAX_TITLE_CHARS = 80
GEMINI_MAX_MODEL_CHARS = 80
GEMINI_MAX_REASONING_CHARS = 40
_default_model_options = sorted({
    'auto',
    'flash',
    'flash-lite',
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
    'gemini-2.5-pro',
    'pro'
})
GEMINI_MODEL_OPTIONS = [
    item.strip()
    for item in os.environ.get('GEMINI_MODEL_OPTIONS', '').split(',')
    if item.strip()
]
if not GEMINI_MODEL_OPTIONS:
    GEMINI_MODEL_OPTIONS = _default_model_options
GEMINI_REASONING_OPTIONS = [
    item.strip()
    for item in os.environ.get('GEMINI_REASONING_OPTIONS', 'default,auto_edit,yolo').split(',')
    if item.strip()
]

KST = timezone(timedelta(hours=9))
KST_ZONEINFO = ZoneInfo('Asia/Seoul') if ZoneInfo else None

SECRET_KEY = os.environ.get('GEMINI_CHAT_SECRET_KEY', 'gemini-chat-secret-key-change-in-production')
