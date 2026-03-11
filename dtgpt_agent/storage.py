"""Session and settings storage for the Tkinter DTGPT agent."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .config import (
    CHAT_STORE_PATH,
    DEFAULT_PROVIDER,
    SETTINGS_PATH,
)
from .providers import (
    default_model_for_provider,
    normalize_model_name,
    normalize_provider_name,
)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sort_sessions(sessions: list[dict]) -> list[dict]:
    return sorted(
        sessions,
        key=lambda item: item.get("updated_at") or item.get("created_at") or "",
        reverse=True,
    )


def _find_session(sessions: list[dict], session_id: str) -> dict | None:
    for session in sessions:
        if session.get("id") == session_id:
            return session
    return None


def _has_user_message(session: dict) -> bool:
    messages = session.get("messages", [])
    if not isinstance(messages, list):
        return False
    return any(message.get("role") == "user" for message in messages if isinstance(message, dict))


def generate_session_title(prompt: str | None) -> str:
    normalized = " ".join(str(prompt or "").strip().split())
    if not normalized:
        return "New session"
    if len(normalized) > 24:
        return f"{normalized[:24]}..."
    return normalized


class Storage:
    """Thread-safe storage for session history and provider settings."""

    def __init__(self, chat_store_path: Path | None = None, settings_path: Path | None = None) -> None:
        self.chat_store_path = Path(chat_store_path or CHAT_STORE_PATH)
        self.settings_path = Path(settings_path or SETTINGS_PATH)
        self._data_lock = threading.Lock()
        self._settings_lock = threading.Lock()

    def _load_data(self) -> dict:
        if not self.chat_store_path.exists():
            return {"sessions": []}
        try:
            data = json.loads(self.chat_store_path.read_text(encoding="utf-8"))
        except Exception:
            return {"sessions": []}
        if not isinstance(data, dict):
            return {"sessions": []}
        sessions = data.get("sessions")
        if not isinstance(sessions, list):
            data["sessions"] = []
        return data

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(serialized)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
                temp_path = Path(handle.name)
            os.replace(temp_path, path)
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def _save_data(self, data: dict) -> None:
        self._atomic_write_json(self.chat_store_path, data)

    def _default_settings(self) -> dict:
        provider = normalize_provider_name(DEFAULT_PROVIDER)
        return {
            "provider": provider,
            "model": default_model_for_provider(provider),
        }

    def _read_settings(self) -> dict:
        try:
            raw = self.settings_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            return self._default_settings()
        if not isinstance(data, dict):
            return self._default_settings()
        provider = normalize_provider_name(data.get("provider"))
        model = normalize_model_name(provider, data.get("model"))
        return {
            "provider": provider,
            "model": model,
        }

    def _write_settings(self, settings: dict) -> None:
        provider = normalize_provider_name(settings.get("provider"))
        model = normalize_model_name(provider, settings.get("model"))
        self._atomic_write_json(
            self.settings_path,
            {
                "provider": provider,
                "model": model,
            },
        )

    def list_sessions(self) -> list[dict]:
        with self._data_lock:
            data = self._load_data()
            sessions = _sort_sessions(data.get("sessions", []))
        summary: list[dict] = []
        for session in sessions:
            messages = session.get("messages", [])
            summary.append(
                {
                    "id": session.get("id"),
                    "title": session.get("title") or "New session",
                    "created_at": session.get("created_at"),
                    "updated_at": session.get("updated_at"),
                    "message_count": len(messages) if isinstance(messages, list) else 0,
                }
            )
        return summary

    def get_session(self, session_id: str) -> dict | None:
        with self._data_lock:
            data = self._load_data()
            session = _find_session(data.get("sessions", []), session_id)
        return deepcopy(session) if session else None

    def create_session(self, title: str | None = None) -> dict:
        now = _now_iso()
        session = {
            "id": uuid.uuid4().hex,
            "title": (title or "").strip() or "New session",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        with self._data_lock:
            data = self._load_data()
            sessions = data.get("sessions", [])
            sessions.append(session)
            data["sessions"] = _sort_sessions(sessions)
            self._save_data(data)
        return deepcopy(session)

    def append_message(self, session_id: str, role: str, content: str | None, metadata: dict | None = None) -> dict | None:
        message = {
            "id": uuid.uuid4().hex,
            "role": str(role or "assistant"),
            "content": str(content or ""),
            "created_at": _now_iso(),
        }
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if key not in message:
                    message[key] = value

        with self._data_lock:
            data = self._load_data()
            sessions = data.get("sessions", [])
            session = _find_session(sessions, session_id)
            if not session:
                return None
            session.setdefault("messages", []).append(message)
            session["updated_at"] = _now_iso()
            data["sessions"] = _sort_sessions(sessions)
            self._save_data(data)
        return deepcopy(message)

    def ensure_default_title(self, session_id: str, prompt: str) -> dict | None:
        with self._data_lock:
            data = self._load_data()
            sessions = data.get("sessions", [])
            session = _find_session(sessions, session_id)
            if not session:
                return None
            title = str(session.get("title") or "").strip()
            if title and title != "New session":
                return deepcopy(session)
            if _has_user_message(session):
                return deepcopy(session)
            session["title"] = generate_session_title(prompt)
            session["updated_at"] = _now_iso()
            data["sessions"] = _sort_sessions(sessions)
            self._save_data(data)
            return deepcopy(session)

    def rename_session(self, session_id: str, title: str) -> dict | None:
        normalized = str(title or "").strip()
        if not normalized:
            return None
        with self._data_lock:
            data = self._load_data()
            sessions = data.get("sessions", [])
            session = _find_session(sessions, session_id)
            if not session:
                return None
            session["title"] = normalized
            session["updated_at"] = _now_iso()
            data["sessions"] = _sort_sessions(sessions)
            self._save_data(data)
        return deepcopy(session)

    def delete_session(self, session_id: str) -> bool:
        with self._data_lock:
            data = self._load_data()
            sessions = data.get("sessions", [])
            remaining = [session for session in sessions if session.get("id") != session_id]
            if len(remaining) == len(sessions):
                return False
            data["sessions"] = _sort_sessions(remaining)
            self._save_data(data)
        return True

    def get_settings(self) -> dict:
        with self._settings_lock:
            settings = self._read_settings()
            if not self.settings_path.exists():
                self._write_settings(settings)
            return settings

    def _resolve_settings_values(self, current: dict, provider: str | None = None, model: str | None = None) -> dict:
        current_provider = normalize_provider_name(current.get("provider"))
        current_model = normalize_model_name(current_provider, current.get("model"))

        next_provider = current_provider
        provider_changed = False
        if provider is not None:
            next_provider = normalize_provider_name(provider)
            provider_changed = next_provider != current_provider

        if model is None:
            if provider_changed:
                next_model = default_model_for_provider(next_provider)
            else:
                next_model = current_model
        else:
            next_model = normalize_model_name(next_provider, model)

        return {
            "provider": next_provider,
            "model": next_model,
        }

    def resolve_settings_preview(self, provider: str | None = None, model: str | None = None) -> dict:
        with self._settings_lock:
            current = self._read_settings()
            return self._resolve_settings_values(current, provider=provider, model=model)

    def update_settings(self, provider: str | None = None, model: str | None = None) -> dict:
        with self._settings_lock:
            current = self._read_settings()
            payload = self._resolve_settings_values(current, provider=provider, model=model)
            self._write_settings(payload)
            return payload
