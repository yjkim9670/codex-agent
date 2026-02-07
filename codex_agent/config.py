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
CODEX_MAX_PROMPT_CHARS = 4000
CODEX_CONTEXT_MAX_CHARS = 12000
CODEX_EXEC_TIMEOUT_SECONDS = 600
CODEX_STREAM_TTL_SECONDS = 900
CODEX_MAX_TITLE_CHARS = 80
CODEX_MAX_MODEL_CHARS = 80
CODEX_MAX_REASONING_CHARS = 40
CODEX_MODEL_OPTIONS = [
    item.strip()
    for item in os.environ.get('CODEX_MODEL_OPTIONS', '').split(',')
    if item.strip()
]
CODEX_REASONING_OPTIONS = [
    item.strip()
    for item in os.environ.get('CODEX_REASONING_OPTIONS', 'low,medium,high').split(',')
    if item.strip()
]

KST = timezone(timedelta(hours=9))
KST_ZONEINFO = ZoneInfo('Asia/Seoul') if ZoneInfo else None

SECRET_KEY = os.environ.get('CODEX_CHAT_SECRET_KEY', 'codex-chat-secret-key-change-in-production')
