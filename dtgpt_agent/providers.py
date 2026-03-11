"""Provider access helpers for Gemini, DTGPT, and Claude Code."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from .config import (
    API_TIMEOUT_SECONDS,
    CLAUDE_CODE_COMMAND,
    CLAUDE_CODE_DEFAULT_MODEL,
    CLAUDE_CODE_PERMISSION_MODE,
    CLAUDE_CODE_TOOLS,
    DEFAULT_PROVIDER,
    DTGPT_API_KEY,
    DTGPT_API_KEY_ENV,
    DTGPT_API_KEY_HEADER,
    DTGPT_API_KEY_PREFIX,
    DTGPT_CAE_API_BASE_URL,
    DTGPT_CAE_API_BASE_URLS,
    DTGPT_CAE_DEFAULT_API_BASE_URL,
    DTGPT_DEFAULT_MODEL,
    DTGPT_OA_API_BASE_URL,
    DTGPT_OA_API_BASE_URLS,
    DTGPT_OA_DEFAULT_API_BASE_URL,
    GEMINI_API_BASE_URL,
    GEMINI_API_KEY,
    GEMINI_DEFAULT_MODEL,
    PROVIDER_DEFAULT_MODELS,
    PROVIDER_MODEL_OPTIONS,
    PROVIDER_OPTIONS,
    WORKSPACE_DIR,
)

SUPPORTED_PROVIDERS = ("gemini", "dtgpt_oa", "dtgpt_cae", "claude_code")
OPENAI_COMPATIBLE_PROVIDERS = ("dtgpt_oa", "dtgpt_cae")
ENV_REFERENCE_PATTERN = re.compile(r"^\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}$")


class ProviderError(RuntimeError):
    """Raised when provider-specific execution fails."""


def _is_dtgpt_cloud_endpoint(url: str | None) -> bool:
    lowered = str(url or "").strip().lower()
    return "://cloud." in lowered or "cloud.dtgpt.samsungds.net" in lowered


def _force_cloud_base_url(url: str | None) -> str:
    normalized = str(url or "").strip().rstrip("/")
    if not normalized:
        return ""
    if _is_dtgpt_cloud_endpoint(normalized):
        return normalized

    parsed = urllib.parse.urlsplit(normalized)
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc
    if not netloc:
        return normalized

    if netloc.startswith("cloud."):
        cloud_netloc = netloc
    elif netloc.startswith("dtgpt."):
        cloud_netloc = f"cloud.{netloc}"
    else:
        cloud_netloc = f"cloud.{netloc}"

    rebuilt = urllib.parse.urlunsplit(
        (scheme, cloud_netloc, parsed.path, parsed.query, parsed.fragment)
    )
    return rebuilt.rstrip("/")


def _dedupe_urls(candidates: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized_item = str(item or "").strip().rstrip("/")
        if not normalized_item:
            continue
        key = normalized_item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized_item)
    return deduped


def canonical_provider_name(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "gemini": "gemini",
        "google": "gemini",
        "dtgpt": "dtgpt_cae",
        "dt-gpt": "dtgpt_cae",
        "dt_gpt": "dtgpt_cae",
        "dt gpt": "dtgpt_cae",
        "samsung_dtgpt": "dtgpt_cae",
        "samsung-dtgpt": "dtgpt_cae",
        "samsung dtgpt": "dtgpt_cae",
        "samsungds dtgpt": "dtgpt_cae",
        "openai": "dtgpt_cae",
        "gpt": "dtgpt_cae",
        "kimi": "dtgpt_cae",
        "moonshot": "dtgpt_cae",
        "moonshotai": "dtgpt_cae",
        "glm": "dtgpt_cae",
        "bigmodel": "dtgpt_cae",
        "zhipu": "dtgpt_cae",
        "dtgpt_oa": "dtgpt_oa",
        "dtgpt-oa": "dtgpt_oa",
        "dtgpt oa": "dtgpt_oa",
        "oa": "dtgpt_oa",
        "dtgpt_cae": "dtgpt_cae",
        "dtgpt-cae": "dtgpt_cae",
        "dtgpt cae": "dtgpt_cae",
        "cae": "dtgpt_cae",
        "claude": "claude_code",
        "claude_code": "claude_code",
        "claude-code": "claude_code",
        "claude code": "claude_code",
        "anthropic": "claude_code",
        "anthropic claude": "claude_code",
    }
    return aliases.get(raw, "")


def normalize_provider_name(value: str | None) -> str:
    canonical = canonical_provider_name(value)
    if canonical in SUPPORTED_PROVIDERS:
        return canonical
    fallback = canonical_provider_name(DEFAULT_PROVIDER)
    if fallback in SUPPORTED_PROVIDERS:
        return fallback
    return "gemini"


def get_provider_options() -> list[str]:
    options: list[str] = []
    for item in PROVIDER_OPTIONS:
        provider = canonical_provider_name(item)
        if not provider or provider in options:
            continue
        options.append(provider)
    if not options:
        options = list(SUPPORTED_PROVIDERS)
    default_provider = normalize_provider_name(DEFAULT_PROVIDER)
    if default_provider not in options:
        options.insert(0, default_provider)
    return options


def default_model_for_provider(provider: str | None) -> str:
    normalized = normalize_provider_name(provider)
    configured = PROVIDER_DEFAULT_MODELS.get(normalized)
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    if normalized in OPENAI_COMPATIBLE_PROVIDERS:
        return DTGPT_DEFAULT_MODEL
    if normalized == "claude_code":
        return CLAUDE_CODE_DEFAULT_MODEL
    return GEMINI_DEFAULT_MODEL


def normalize_model_name(provider: str | None, value: str | None) -> str:
    normalized_provider = normalize_provider_name(provider)
    raw = str(value or "").strip()
    if not raw:
        raw = default_model_for_provider(normalized_provider)

    if normalized_provider == "gemini":
        if raw.startswith("models/"):
            raw = raw[len("models/") :]
        alias_key = raw.lower()
        alias_map = {
            "auto": GEMINI_DEFAULT_MODEL,
            "flash": "gemini-flash-latest",
            "flash-lite": "gemini-flash-lite-latest",
            "pro": "gemini-pro-latest",
        }
        return alias_map.get(alias_key, raw)

    if normalized_provider in OPENAI_COMPATIBLE_PROVIDERS:
        alias_key = raw.lower()
        alias_map = {
            "auto": DTGPT_DEFAULT_MODEL,
            "k2.5": "Kimi-K2.5",
            "kimi-k2.5": "Kimi-K2.5",
            "glm4.7": "GLM4.7",
            "oss-120b": "openai/gpt-oss-120b",
            "gpt-oss-120b": "openai/gpt-oss-120b",
        }
        return alias_map.get(alias_key, raw)

    if normalized_provider == "claude_code":
        alias_key = raw.lower()
        alias_map = {
            "auto": CLAUDE_CODE_DEFAULT_MODEL,
            "sonnet": "sonnet",
            "opus": "opus",
            "haiku": "haiku",
        }
        return alias_map.get(alias_key, raw)

    return raw


def get_model_options(provider: str | None = None) -> list[str]:
    normalized = normalize_provider_name(provider)
    configured = PROVIDER_MODEL_OPTIONS.get(normalized)
    if not isinstance(configured, list):
        configured = []
    options: list[str] = []
    for item in configured:
        token = str(item or "").strip()
        if not token or token in options:
            continue
        options.append(token)
    default_model = default_model_for_provider(normalized)
    if default_model not in options:
        options.insert(0, default_model)
    return options


def _resolve_env_reference(value: str | None) -> str:
    token = str(value or "").strip()
    if not token:
        return token
    match = ENV_REFERENCE_PATTERN.match(token)
    if match:
        return os.environ.get(match.group(1), "")
    if token.lower().startswith("env:"):
        env_name = token[4:].strip()
        if env_name:
            return os.environ.get(env_name, "")
    return token


def _is_placeholder_api_key(value: str | None) -> bool:
    token = str(value or "").strip()
    if not token:
        return False
    if ENV_REFERENCE_PATTERN.match(token):
        return True
    if token.lower().startswith("env:"):
        return True
    if token.upper().startswith("YOUR_"):
        return True
    return False


def _provider_api_key(provider: str) -> str:
    normalized = normalize_provider_name(provider)
    configured_key = ""
    fallback_env_name = ""
    if normalized in OPENAI_COMPATIBLE_PROVIDERS:
        configured_key = DTGPT_API_KEY
        fallback_env_name = DTGPT_API_KEY_ENV
    else:
        configured_key = GEMINI_API_KEY

    resolved = _resolve_env_reference(configured_key)
    normalized_key = str(resolved or "").strip()
    if normalized_key:
        return normalized_key
    if fallback_env_name:
        from_env = str(os.getenv(fallback_env_name) or "").strip()
        if from_env:
            return from_env
    return ""


def _provider_api_key_header(provider: str) -> str:
    normalized = normalize_provider_name(provider)
    if normalized in OPENAI_COMPATIBLE_PROVIDERS:
        header_name = str(_resolve_env_reference(DTGPT_API_KEY_HEADER) or "").strip()
        return header_name or "Authorization"
    return ""


def _provider_api_key_prefix(provider: str) -> str:
    normalized = normalize_provider_name(provider)
    if normalized in OPENAI_COMPATIBLE_PROVIDERS:
        prefix = str(_resolve_env_reference(DTGPT_API_KEY_PREFIX) or "").strip()
        return prefix or "Bearer"
    return ""


def _provider_api_base_url(provider: str) -> str:
    normalized = normalize_provider_name(provider)
    if normalized == "dtgpt_oa":
        value = DTGPT_OA_API_BASE_URL
    elif normalized == "dtgpt_cae":
        value = DTGPT_CAE_API_BASE_URL
    else:
        value = GEMINI_API_BASE_URL
    return str(_resolve_env_reference(value) or "").strip().rstrip("/")


def _provider_api_base_urls(provider: str) -> list[str]:
    normalized = normalize_provider_name(provider)
    candidates: list[str] = []

    primary = _provider_api_base_url(normalized)
    if primary:
        candidates.append(primary)

    if normalized == "dtgpt_oa":
        for item in DTGPT_OA_API_BASE_URLS:
            token = str(_resolve_env_reference(item) or "").strip().rstrip("/")
            if token:
                candidates.append(token)
        candidates.append(DTGPT_OA_DEFAULT_API_BASE_URL)
        cloud_only: list[str] = []
        for item in candidates:
            forced = _force_cloud_base_url(item)
            if _is_dtgpt_cloud_endpoint(forced):
                cloud_only.append(forced)
        return _dedupe_urls(cloud_only)

    if normalized == "dtgpt_cae":
        for item in DTGPT_CAE_API_BASE_URLS:
            token = str(_resolve_env_reference(item) or "").strip().rstrip("/")
            if token:
                candidates.append(token)
        candidates.append(DTGPT_CAE_DEFAULT_API_BASE_URL)
        non_cloud = [item for item in candidates if not _is_dtgpt_cloud_endpoint(item)]
        return _dedupe_urls(non_cloud)

    return _dedupe_urls(candidates)


def _has_valid_api_key(provider: str) -> bool:
    key = _provider_api_key(provider)
    if not key:
        return False
    return not _is_placeholder_api_key(key)


def _build_auth_header_value(api_key: str, key_prefix: str = "Bearer") -> str:
    normalized_key = str(api_key or "").strip()
    normalized_prefix = str(key_prefix or "").strip()
    if not normalized_key:
        return ""
    if not normalized_prefix:
        return normalized_key
    prefix_with_space = f"{normalized_prefix} "
    if normalized_key.lower().startswith(prefix_with_space.lower()):
        return normalized_key
    return f"{normalized_prefix} {normalized_key}".strip()


def _extract_api_error_message(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        message = error_payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return ""


def _read_http_error_message(exc: urllib.error.HTTPError, label: str) -> str:
    try:
        raw = exc.read()
    except Exception:
        raw = b""
    if not raw:
        return f"{label} request failed. (HTTP {getattr(exc, 'code', 'unknown')})"
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        payload = {}
    message = _extract_api_error_message(payload)
    if message:
        return message
    text = raw.decode("utf-8", errors="replace").strip()
    if text:
        return text
    return f"{label} request failed. (HTTP {getattr(exc, 'code', 'unknown')})"


def _build_json_request(
    url: str, payload: dict, headers: dict[str, str] | None = None
) -> urllib.request.Request:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(url=url, data=body, headers=headers or {}, method="POST")


def _build_gemini_payload(prompt: str) -> dict:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": str(prompt or "")}],
            }
        ],
        "generationConfig": {"temperature": 0.2},
    }


def _build_gemini_api_url(model: str) -> str:
    escaped_model = urllib.parse.quote(model, safe="-._~")
    api_key = urllib.parse.quote_plus(_provider_api_key("gemini"))
    base_url = _provider_api_base_url("gemini")
    return f"{base_url}/models/{escaped_model}:generateContent?key={api_key}"


def _extract_gemini_response_text(payload) -> str:
    if isinstance(payload, list):
        return "".join(_extract_gemini_response_text(item) for item in payload)
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return ""
    chunks: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
    return "".join(chunks)


def _build_openai_payload(prompt: str, model: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": str(prompt or "")}],
        "temperature": 0.2,
    }


def _build_openai_compatible_api_urls(provider: str) -> list[str]:
    endpoints: list[str] = []
    for base_url in _provider_api_base_urls(provider):
        normalized = base_url.rstrip("/")
        if normalized.lower().endswith("/chat/completions"):
            endpoints.append(normalized)
        else:
            endpoints.append(f"{normalized}/chat/completions")
    return endpoints


def _extract_openai_content_fragment(fragment) -> str:
    if isinstance(fragment, str):
        return fragment
    if isinstance(fragment, list):
        chunks: list[str] = []
        for item in fragment:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
        return "".join(chunks)
    return ""


def _extract_openai_response_text(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return ""
    chunks: list[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        content = _extract_openai_content_fragment(message.get("content"))
        if content:
            chunks.append(content)
    return "".join(chunks)


def _extract_claude_code_result_text(raw_text: str) -> tuple[str, bool]:
    text = str(raw_text or "").strip()
    if not text:
        return "", False

    payload = None
    try:
        payload = json.loads(text)
    except Exception:
        for line in reversed(text.splitlines()):
            candidate = line.strip()
            if not candidate:
                continue
            try:
                payload = json.loads(candidate)
                break
            except Exception:
                continue

    if not isinstance(payload, dict):
        return text, False

    result_text = str(payload.get("result") or "").strip()
    is_error = bool(payload.get("is_error"))
    if result_text:
        return result_text, is_error
    return "", is_error


def _build_claude_code_command(prompt: str, model: str) -> list[str]:
    command = [CLAUDE_CODE_COMMAND, "-p", "--output-format", "json", "--no-session-persistence"]

    permission_mode = str(_resolve_env_reference(CLAUDE_CODE_PERMISSION_MODE) or "").strip()
    if permission_mode:
        command.extend(["--permission-mode", permission_mode])

    tools_configured = str(_resolve_env_reference(CLAUDE_CODE_TOOLS))
    command.extend(["--tools", tools_configured])

    normalized_model = str(model or "").strip()
    if normalized_model:
        command.extend(["--model", normalized_model])

    command.append(str(prompt or ""))
    return command


def execute_gemini_prompt(prompt: str, model: str) -> tuple[str | None, str | None]:
    if not _has_valid_api_key("gemini"):
        return None, "Gemini API key is not configured."

    payload = _build_gemini_payload(prompt)
    url = _build_gemini_api_url(model)
    request = _build_json_request(url, payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(request, timeout=max(1, int(API_TIMEOUT_SECONDS))) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return None, _read_http_error_message(exc, "Gemini API")
    except urllib.error.URLError as exc:
        return None, f"Gemini API connection failed: {exc.reason}"
    except TimeoutError:
        return None, "Gemini API request timed out."
    except Exception as exc:
        return None, f"Gemini API request failed: {exc}"

    try:
        response_payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None, "Failed to parse Gemini API response."

    text = _extract_gemini_response_text(response_payload).strip()
    if text:
        return text, None

    error_text = _extract_api_error_message(response_payload)
    if error_text:
        return None, error_text
    return None, "Gemini API returned an empty response."


def execute_dtgpt_prompt(
    provider: str, prompt: str, model: str
) -> tuple[str | None, str | None]:
    normalized_provider = normalize_provider_name(provider)
    if normalized_provider not in OPENAI_COMPATIBLE_PROVIDERS:
        normalized_provider = "dtgpt_cae"

    provider_label = "DTGPT OA API" if normalized_provider == "dtgpt_oa" else "DTGPT CAE API"

    if not _has_valid_api_key(normalized_provider):
        return None, f"{provider_label} key is not configured."

    endpoints = _build_openai_compatible_api_urls(normalized_provider)
    if not endpoints:
        return None, f"{provider_label} endpoint is empty."

    payload = _build_openai_payload(prompt, model)
    api_key = _provider_api_key(normalized_provider)
    auth_header = _provider_api_key_header(normalized_provider)
    auth_prefix = _provider_api_key_prefix(normalized_provider)
    auth_value = _build_auth_header_value(api_key, auth_prefix)

    headers = {"Content-Type": "application/json"}
    if auth_header and auth_value:
        headers[auth_header] = auth_value

    last_error: str | None = None

    for endpoint in endpoints:
        request = _build_json_request(endpoint, payload, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=max(1, int(API_TIMEOUT_SECONDS))) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            message = _read_http_error_message(exc, provider_label)
            status_code = getattr(exc, "code", None)
            if status_code in {400, 401, 403, 404, 415, 422}:
                return None, message
            last_error = f"{message} (endpoint: {endpoint})"
            continue
        except urllib.error.URLError as exc:
            last_error = f"{provider_label} connection failed: {exc.reason} (endpoint: {endpoint})"
            continue
        except TimeoutError:
            last_error = f"{provider_label} request timed out. (endpoint: {endpoint})"
            continue
        except Exception as exc:
            last_error = f"{provider_label} request failed: {exc} (endpoint: {endpoint})"
            continue

        try:
            response_payload = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception:
            last_error = f"Failed to parse {provider_label} response. (endpoint: {endpoint})"
            continue

        text = _extract_openai_response_text(response_payload).strip()
        if text:
            return text, None

        error_text = _extract_api_error_message(response_payload)
        if error_text:
            return None, error_text
        last_error = f"{provider_label} returned an empty response. (endpoint: {endpoint})"

    return None, last_error or f"{provider_label} request failed."


def execute_claude_code_prompt(prompt: str, model: str) -> tuple[str | None, str | None]:
    workspace_path = WORKSPACE_DIR
    try:
        workspace_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    cmd = _build_claude_code_command(prompt, model)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=max(1, int(API_TIMEOUT_SECONDS)),
            check=False,
        )
    except FileNotFoundError:
        return None, f"Claude Code command not found: {CLAUDE_CODE_COMMAND}"
    except subprocess.TimeoutExpired:
        return None, "Claude Code request timed out."
    except Exception as exc:
        return None, f"Claude Code request failed: {exc}"

    response_text, response_is_error = _extract_claude_code_result_text(result.stdout)
    stderr_text = str(result.stderr or "").strip()

    if response_is_error:
        if response_text:
            return None, response_text
        if stderr_text:
            return None, stderr_text
        return None, "Claude Code returned an error."

    if response_text:
        return response_text, None

    if result.returncode != 0:
        return None, stderr_text or "Claude Code execution failed."
    return None, "Claude Code returned an empty response."


def execute_prompt(
    provider: str | None, prompt: str, model: str | None
) -> tuple[str | None, str | None]:
    normalized_provider = normalize_provider_name(provider)
    normalized_model = normalize_model_name(normalized_provider, model)

    if normalized_provider == "claude_code":
        return execute_claude_code_prompt(prompt, normalized_model)
    if normalized_provider in OPENAI_COMPATIBLE_PROVIDERS:
        return execute_dtgpt_prompt(normalized_provider, prompt, normalized_model)
    return execute_gemini_prompt(prompt, normalized_model)
