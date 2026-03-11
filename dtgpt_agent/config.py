"""Configuration values for the Tkinter DTGPT agent."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent


def _read_positive_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    if parsed < minimum:
        return default
    return parsed


def _read_csv_env(name: str) -> list[str]:
    raw_value = os.environ.get(name, "")
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _read_path_env(name: str, fallback: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    return Path(raw).expanduser().resolve()


def _has_cloud_prefix(url: str | None) -> bool:
    return "://cloud." in str(url or "").strip().lower()


workspace_override = os.environ.get("DTGPT_AGENT_WORKSPACE_DIR", "").strip()
if not workspace_override:
    workspace_override = os.environ.get("MODEL_WORKSPACE_DIR", "").strip()
if workspace_override:
    WORKSPACE_DIR = Path(workspace_override).expanduser().resolve()
else:
    WORKSPACE_DIR = REPO_ROOT / "workspace"

CHAT_STORE_PATH = _read_path_env(
    "DTGPT_AGENT_CHAT_STORE_PATH",
    WORKSPACE_DIR / "dtgpt_chat_sessions.json",
)
SETTINGS_PATH = _read_path_env(
    "DTGPT_AGENT_SETTINGS_PATH",
    WORKSPACE_DIR / "dtgpt_settings.json",
)

MAX_PROMPT_CHARS = _read_positive_int_env("DTGPT_AGENT_MAX_PROMPT_CHARS", 4000)
MAX_TITLE_CHARS = _read_positive_int_env("DTGPT_AGENT_MAX_TITLE_CHARS", 80)
CONTEXT_MAX_CHARS = _read_positive_int_env("DTGPT_AGENT_CONTEXT_MAX_CHARS", 12000)
API_TIMEOUT_SECONDS = _read_positive_int_env("DTGPT_AGENT_API_TIMEOUT_SECONDS", 120)

DEFAULT_PROVIDER = (
    os.environ.get("DTGPT_AGENT_DEFAULT_PROVIDER", os.environ.get("MODEL_DEFAULT_PROVIDER", "gemini"))
    .strip()
    .lower()
    or "gemini"
)

PROVIDER_OPTIONS = _read_csv_env("DTGPT_AGENT_PROVIDER_OPTIONS")
if not PROVIDER_OPTIONS:
    PROVIDER_OPTIONS = ["gemini", "dtgpt_oa", "dtgpt_cae"]

GEMINI_API_KEY = os.environ.get("MODEL_GEMINI_API_KEY", os.environ.get("MODEL_API_KEY", "")).strip()
GEMINI_API_BASE_URL = (
    os.environ.get(
        "MODEL_GEMINI_API_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta",
    )
    .strip()
    .rstrip("/")
    or "https://generativelanguage.googleapis.com/v1beta"
)

DTGPT_API_KEY = os.environ.get("MODEL_DTGPT_API_KEY", "").strip()
DTGPT_API_KEY_ENV = os.environ.get("MODEL_DTGPT_API_KEY_ENV", "DTGPT_API_KEY").strip() or "DTGPT_API_KEY"
DTGPT_API_KEY_HEADER = os.environ.get("MODEL_DTGPT_API_KEY_HEADER", "Authorization").strip() or "Authorization"
DTGPT_API_KEY_PREFIX = os.environ.get("MODEL_DTGPT_API_KEY_PREFIX", "Bearer").strip() or "Bearer"

DTGPT_OA_DEFAULT_API_BASE_URL = "http://cloud.dtgpt.samsungds.net/llm/v1"
DTGPT_CAE_DEFAULT_API_BASE_URL = "http://dtgpt.samsungds.net/llm/v1"
_legacy_dtgpt_api_base_url = os.environ.get("MODEL_DTGPT_API_BASE_URL", "").strip().rstrip("/")
_legacy_dtgpt_api_base_urls = _read_csv_env("MODEL_DTGPT_API_BASE_URLS")

DTGPT_OA_API_BASE_URL = (
    os.environ.get("MODEL_DTGPT_OA_API_BASE_URL", "").strip().rstrip("/")
    or (
        _legacy_dtgpt_api_base_url
        if _legacy_dtgpt_api_base_url and _has_cloud_prefix(_legacy_dtgpt_api_base_url)
        else DTGPT_OA_DEFAULT_API_BASE_URL
    )
)
DTGPT_CAE_API_BASE_URL = (
    os.environ.get("MODEL_DTGPT_CAE_API_BASE_URL", "").strip().rstrip("/")
    or (
        _legacy_dtgpt_api_base_url
        if _legacy_dtgpt_api_base_url and not _has_cloud_prefix(_legacy_dtgpt_api_base_url)
        else DTGPT_CAE_DEFAULT_API_BASE_URL
    )
)

DTGPT_OA_API_BASE_URLS = _read_csv_env("MODEL_DTGPT_OA_API_BASE_URLS")
if not DTGPT_OA_API_BASE_URLS:
    DTGPT_OA_API_BASE_URLS = [
        item for item in _legacy_dtgpt_api_base_urls if _has_cloud_prefix(item)
    ]
if not DTGPT_OA_API_BASE_URLS:
    DTGPT_OA_API_BASE_URLS = [
        DTGPT_OA_API_BASE_URL,
        DTGPT_OA_DEFAULT_API_BASE_URL,
    ]

DTGPT_CAE_API_BASE_URLS = _read_csv_env("MODEL_DTGPT_CAE_API_BASE_URLS")
if not DTGPT_CAE_API_BASE_URLS:
    DTGPT_CAE_API_BASE_URLS = [
        item for item in _legacy_dtgpt_api_base_urls if not _has_cloud_prefix(item)
    ]
if not DTGPT_CAE_API_BASE_URLS:
    DTGPT_CAE_API_BASE_URLS = [
        DTGPT_CAE_API_BASE_URL,
        DTGPT_CAE_DEFAULT_API_BASE_URL,
    ]

GEMINI_DEFAULT_MODEL = (
    os.environ.get("MODEL_GEMINI_DEFAULT_MODEL", os.environ.get("MODEL_DEFAULT_MODEL", "gemini-flash-latest"))
    .strip()
    or "gemini-flash-latest"
)
DTGPT_DEFAULT_MODEL = os.environ.get("MODEL_DTGPT_DEFAULT_MODEL", "Kimi-K2.5").strip() or "Kimi-K2.5"

PROVIDER_DEFAULT_MODELS = {
    "gemini": GEMINI_DEFAULT_MODEL,
    "dtgpt_oa": DTGPT_DEFAULT_MODEL,
    "dtgpt_cae": DTGPT_DEFAULT_MODEL,
}

_default_gemini_options = sorted(
    {
        GEMINI_DEFAULT_MODEL,
        "gemini-flash-lite-latest",
        "gemini-pro-latest",
        "gemini-3.1-pro-preview",
    }
)
GEMINI_MODEL_OPTIONS = _read_csv_env("MODEL_GEMINI_MODEL_OPTIONS")
if not GEMINI_MODEL_OPTIONS:
    GEMINI_MODEL_OPTIONS = _default_gemini_options

_default_dtgpt_options = sorted(
    {
        DTGPT_DEFAULT_MODEL,
        "GLM4.7",
        "Kimi-K2.5",
        "openai/gpt-oss-120b",
    }
)
DTGPT_MODEL_OPTIONS = _read_csv_env("MODEL_DTGPT_MODEL_OPTIONS")
if not DTGPT_MODEL_OPTIONS:
    DTGPT_MODEL_OPTIONS = _default_dtgpt_options

PROVIDER_MODEL_OPTIONS = {
    "gemini": GEMINI_MODEL_OPTIONS,
    "dtgpt_oa": DTGPT_MODEL_OPTIONS,
    "dtgpt_cae": DTGPT_MODEL_OPTIONS,
}
