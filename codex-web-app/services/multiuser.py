"""Request-scoped isolation for the optional internal multi-user mode.

This module intentionally has no Flask dependency.  The application resolves a
trusted client identity at the HTTP boundary and activates it here; existing
services can keep using pathlib-like configuration values without sharing a
user's files or ledgers with another user.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import json
import os
import re


_USER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_active_user: ContextVar["InternalUser | None"] = ContextVar("codex_internal_user", default=None)


@dataclass(frozen=True)
class InternalUser:
    username: str
    role: str
    client_ip: str


def normalize_username(value: object) -> str:
    username = str(value or "").strip().lower()
    if not _USER_ID_RE.fullmatch(username):
        raise ValueError("username must contain 1-64 lowercase letters, digits, '.', '_' or '-'")
    return username


def activate_user(user: InternalUser):
    return _active_user.set(user)


def deactivate_user(token) -> None:
    _active_user.reset(token)


def get_active_user() -> InternalUser | None:
    return _active_user.get()


def load_ip_user_map(path: Path) -> dict[str, dict[str, str]]:
    """Load the deliberately small, auditable IP-to-user map.

    Accepted forms are ``{"users": [{"ip": "...", "username": "..."}]}``
    and a list of those entries.  Invalid entries are ignored so a malformed
    single line cannot accidentally grant access.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}
    entries = raw.get('users', []) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return {}
    result = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ip = str(entry.get('ip') or '').strip()
        try:
            username = normalize_username(entry.get('username'))
        except ValueError:
            continue
        role = str(entry.get('role') or 'member').strip().lower()
        if role not in {'admin', 'maintainer', 'member'}:
            continue
        if ip:
            result[ip] = {'username': username, 'role': role}
    return result


def save_ip_user_map(path: Path, entries: object) -> list[dict[str, str]]:
    if not isinstance(entries, list):
        raise ValueError('users must be an array')
    clean = []
    seen_ips = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('each user entry must be an object')
        ip = str(entry.get('ip') or '').strip()
        username = normalize_username(entry.get('username'))
        role = str(entry.get('role') or 'member').strip().lower()
        if not ip or ip in seen_ips or role not in {'admin', 'maintainer', 'member'}:
            raise ValueError('each entry needs a unique IP and a valid role')
        clean.append({'ip': ip, 'username': username, 'role': role})
        seen_ips.add(ip)
    if not any(entry['role'] == 'admin' for entry in clean):
        raise ValueError('at least one admin is required')
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(json.dumps({'version': 1, 'users': clean}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, target)
    return clean


class ScopedPath:
    """A pathlib-compatible value resolved from the current request scope."""

    def __init__(self, standalone_path: Path, internal_resolver):
        self._standalone_path = Path(standalone_path)
        self._internal_resolver = internal_resolver

    def _path(self) -> Path:
        user = get_active_user()
        if user is None:
            return self._standalone_path
        return Path(self._internal_resolver(user))

    def __fspath__(self):
        return str(self._path())

    def __str__(self):
        return str(self._path())

    def __repr__(self):
        return f"ScopedPath({self._path()!s})"

    def __truediv__(self, other):
        return self._path() / other

    def __rtruediv__(self, other):
        return other / self._path()

    def __getattr__(self, name):
        return getattr(self._path(), name)

    def __eq__(self, other):
        try:
            return self._path() == Path(other)
        except TypeError:
            return False

    def __hash__(self):
        return hash(("ScopedPath", str(self._standalone_path)))
