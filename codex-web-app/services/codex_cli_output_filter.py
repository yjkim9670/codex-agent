"""Keep raw Codex CLI/tool diagnostics out of the normal chat transcript.

Codex exec JSONL can report a failed work item with a very verbose error value,
for example a full shell command followed by ``CreateProcess { ... Rejected(...) }``.
Those values are useful for diagnostics but should not be appended to the user-facing
assistant message.

This module installs narrow runtime wrappers around the existing stream helpers. It
intentionally does not change Codex execution, event collection, work-item tracking,
or the normal assistant/progress output path.

The existing Workbench stream keeps structured ``codex_events`` and ``raw_stderr``
for diagnostics. This filter only prevents implementation-level command/runtime text
from being copied into the user-facing ``error`` field and persisted chat content.
"""

from __future__ import annotations

import re
import time

from . import codex_chat as _codex_chat
from .. import state

_GENERIC_CLI_FAILURE = "Codex CLI 작업 중 오류가 발생했습니다. 상세 로그에서 원인을 확인하세요."
_DIAGNOSTIC_LIMIT = 12
_DIAGNOSTIC_TEXT_LIMIT = 12000

_INTERNAL_PATTERNS = (
    re.compile(r"\bCreateProcess\s*\{", re.IGNORECASE),
    re.compile(r"\bCreateProcess\b.{0,200}\bRejected\s*\(", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bRejected\s*\(\s*[\"']", re.IGNORECASE),
    re.compile(r"`[^`\n]{8,}`\s*:\s*CreateProcess\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\brm\s+-f\s+style commands are not permitted\b", re.IGNORECASE),
)


def _normalize(value) -> str:
    normalizer = getattr(_codex_chat, "_normalize_stream_log_text", None)
    if callable(normalizer):
        try:
            return normalizer(value)
        except Exception:
            pass
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _looks_like_internal_cli_detail(value) -> bool:
    text = _normalize(value)
    if not text:
        return False
    if any(pattern.search(text) for pattern in _INTERNAL_PATTERNS):
        return True
    lowered = text.lower()
    execution_keys = sum(
        token in lowered
        for token in (
            '"cmd"',
            '"yield_time_ms"',
            '"session_name"',
            '"workdir"',
            '"timeout"',
        )
    )
    return text.lstrip().startswith("{") and execution_keys >= 2


def _remember_cli_diagnostic(stream_id, value) -> None:
    text = _normalize(value)
    if not text:
        return
    if len(text) > _DIAGNOSTIC_TEXT_LIMIT:
        text = text[-_DIAGNOSTIC_TEXT_LIMIT:]
        text = "(truncated)\n" + text
    try:
        with state.codex_streams_lock:
            stream = state.codex_streams.get(stream_id)
            if not stream:
                return
            diagnostics = stream.setdefault("cli_diagnostics", [])
            if not isinstance(diagnostics, list):
                diagnostics = []
                stream["cli_diagnostics"] = diagnostics
            if text not in diagnostics:
                diagnostics.append(text)
                if len(diagnostics) > _DIAGNOSTIC_LIMIT:
                    del diagnostics[:-_DIAGNOSTIC_LIMIT]
            stream["cli_diagnostic_seen"] = True
            stream["updated_at"] = time.time()
    except Exception:
        return


def install_codex_cli_output_filter() -> None:
    current_append_error = getattr(_codex_chat, "_append_stream_exec_error", None)
    current_append_chunk = getattr(_codex_chat, "_append_stream_chunk", None)
    current_combine = getattr(_codex_chat, "_combine_stream_output_and_error", None)
    current_hidden_stderr = getattr(_codex_chat, "_is_chat_hidden_codex_stderr_line", None)
    if not all(callable(item) for item in (
        current_append_error,
        current_append_chunk,
        current_combine,
        current_hidden_stderr,
    )):
        return
    if getattr(current_append_error, "_codex_cli_output_filter_installed", False):
        return

    original_append_error = current_append_error
    original_append_chunk = current_append_chunk
    original_combine = current_combine
    original_hidden_stderr = current_hidden_stderr

    def filtered_append_stream_exec_error(stream_id, text):
        if _looks_like_internal_cli_detail(text):
            _remember_cli_diagnostic(stream_id, text)
            return True
        return original_append_error(stream_id, text)

    def filtered_append_stream_chunk(stream_id, key, text):
        if str(key or "").strip().lower() == "error" and _looks_like_internal_cli_detail(text):
            _remember_cli_diagnostic(stream_id, text)
            return
        return original_append_chunk(stream_id, key, text)

    def filtered_hidden_codex_stderr_line(line):
        if _looks_like_internal_cli_detail(line):
            return True
        return original_hidden_stderr(line)

    def filtered_combine_stream_output_and_error(output_text, error_text):
        if _looks_like_internal_cli_detail(error_text):
            output_value = "" if output_text is None else str(output_text).strip()
            if output_value:
                return str(output_text)
            return _GENERIC_CLI_FAILURE
        return original_combine(output_text, error_text)

    filtered_append_stream_exec_error._codex_cli_output_filter_installed = True
    filtered_append_stream_exec_error._codex_cli_output_filter_original = original_append_error
    filtered_append_stream_chunk._codex_cli_output_filter_installed = True
    filtered_append_stream_chunk._codex_cli_output_filter_original = original_append_chunk
    filtered_hidden_codex_stderr_line._codex_cli_output_filter_installed = True
    filtered_hidden_codex_stderr_line._codex_cli_output_filter_original = original_hidden_stderr
    filtered_combine_stream_output_and_error._codex_cli_output_filter_installed = True
    filtered_combine_stream_output_and_error._codex_cli_output_filter_original = original_combine

    _codex_chat._append_stream_exec_error = filtered_append_stream_exec_error
    _codex_chat._append_stream_chunk = filtered_append_stream_chunk
    _codex_chat._is_chat_hidden_codex_stderr_line = filtered_hidden_codex_stderr_line
    _codex_chat._combine_stream_output_and_error = filtered_combine_stream_output_and_error
