"""Server-side Cloudflare Quick Tunnel discovery for trusted clients.

The Proc Manager discovery bearer token is read only in this server process.
It must never be returned to browsers, Android clients, logs, or error payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import threading
import time
from typing import Callable, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit


DISCOVERY_PATH = "/__funnel_auth/api/quick-tunnel"
DEFAULT_CACHE_TTL_SECONDS = 45.0
DEFAULT_TIMEOUT_SECONDS = 7.0
_TRYCLOUDFLARE_HOST_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+trycloudflare\.com$"
)


@dataclass(frozen=True)
class QuickTunnelDiscoveryState:
    available: bool
    status: str
    url: Optional[str]
    updated_ts: int


class QuickTunnelDiscoveryError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        http_status: int = 502,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.http_status = int(http_status)
        self.retryable = bool(retryable)


FetchResult = Tuple[int, bytes]
Fetcher = Callable[[str, str, float], FetchResult]
Clock = Callable[[], float]


def normalize_quick_tunnel_url(raw_url: object) -> Optional[str]:
    value = str(raw_url or "").strip()
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    if port is not None or parsed.query or parsed.fragment:
        return None
    if parsed.path not in {"", "/"}:
        return None
    host = (parsed.hostname or "").lower()
    if not _TRYCLOUDFLARE_HOST_RE.fullmatch(host):
        return None
    return f"https://{host}"


def _default_fetcher(url: str, token: str, timeout_seconds: float) -> FetchResult:
    request = urllib_request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "CodexWorkbenchQuickTunnelDiscovery/1",
        },
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            return int(response.status), response.read(128 * 1024)
    except urllib_error.HTTPError as exc:
        return int(exc.code), exc.read(128 * 1024)
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        raise QuickTunnelDiscoveryError(
            "quick_tunnel_discovery_unavailable",
            "Quick Tunnel discovery 서비스에 연결할 수 없습니다.",
            http_status=503,
            retryable=True,
        ) from exc


class QuickTunnelDiscoveryService:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        fetcher: Optional[Fetcher] = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._timeout_seconds = max(0.1, float(timeout_seconds))
        self._fetcher = fetcher or _default_fetcher
        self._clock = clock
        self._lock = threading.RLock()
        self._cached_state: Optional[QuickTunnelDiscoveryState] = None
        self._cache_expires_at = 0.0

    def invalidate(self) -> None:
        with self._lock:
            self._cached_state = None
            self._cache_expires_at = 0.0

    def discover(self, *, force_refresh: bool = False) -> QuickTunnelDiscoveryState:
        now = self._clock()
        with self._lock:
            if force_refresh:
                self._cached_state = None
                self._cache_expires_at = 0.0
            elif self._cached_state is not None and now < self._cache_expires_at:
                return self._cached_state

        base_url = str(
            self._base_url
            if self._base_url is not None
            else os.environ.get("PROC_MANAGER_DISCOVERY_BASE_URL", "")
        ).strip().rstrip("/")
        token = str(
            self._token
            if self._token is not None
            else os.environ.get("PROC_MANAGER_QUICK_TUNNEL_API_TOKEN", "")
        ).strip()
        if not base_url or not token:
            raise QuickTunnelDiscoveryError(
                "quick_tunnel_discovery_not_configured",
                "Quick Tunnel discovery 서버 설정이 준비되지 않았습니다.",
                http_status=503,
                retryable=False,
            )
        if not base_url.lower().startswith("https://"):
            raise QuickTunnelDiscoveryError(
                "quick_tunnel_discovery_not_configured",
                "Quick Tunnel discovery base URL 설정이 올바르지 않습니다.",
                http_status=503,
                retryable=False,
            )

        status_code, raw_body = self._fetcher(
            f"{base_url}{DISCOVERY_PATH}",
            token,
            self._timeout_seconds,
        )
        if status_code == 401:
            self.invalidate()
            raise QuickTunnelDiscoveryError(
                "quick_tunnel_secret_misconfigured",
                "Quick Tunnel discovery Secret 설정을 확인해야 합니다.",
                http_status=500,
                retryable=False,
            )
        if status_code == 503:
            self.invalidate()
            raise QuickTunnelDiscoveryError(
                "quick_tunnel_discovery_unavailable",
                "Quick Tunnel discovery 서비스가 현재 준비되지 않았습니다.",
                http_status=503,
                retryable=False,
            )
        if status_code != 200:
            self.invalidate()
            raise QuickTunnelDiscoveryError(
                "quick_tunnel_discovery_failed",
                f"Quick Tunnel discovery 요청이 실패했습니다. (HTTP {status_code})",
                http_status=502,
                retryable=False,
            )

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.invalidate()
            raise QuickTunnelDiscoveryError(
                "quick_tunnel_discovery_invalid_response",
                "Quick Tunnel discovery 응답 형식이 올바르지 않습니다.",
                http_status=502,
                retryable=False,
            ) from exc
        if not isinstance(payload, dict):
            self.invalidate()
            raise QuickTunnelDiscoveryError(
                "quick_tunnel_discovery_invalid_response",
                "Quick Tunnel discovery 응답 형식이 올바르지 않습니다.",
                http_status=502,
                retryable=False,
            )

        available = payload.get("available") is True
        status = str(payload.get("status") or "").strip()
        try:
            updated_ts = int(payload.get("updated_ts") or 0)
        except (TypeError, ValueError):
            updated_ts = 0

        if not available or status != "online":
            self.invalidate()
            return QuickTunnelDiscoveryState(
                available=False,
                status=status or "offline",
                url=None,
                updated_ts=updated_ts,
            )

        normalized_url = normalize_quick_tunnel_url(payload.get("url"))
        if normalized_url is None:
            self.invalidate()
            raise QuickTunnelDiscoveryError(
                "quick_tunnel_discovery_invalid_response",
                "Quick Tunnel discovery 응답 URL이 허용된 trycloudflare.com 형식이 아닙니다.",
                http_status=502,
                retryable=False,
            )

        state = QuickTunnelDiscoveryState(
            available=True,
            status="online",
            url=normalized_url,
            updated_ts=updated_ts,
        )
        with self._lock:
            self._cached_state = state
            self._cache_expires_at = self._clock() + self._cache_ttl_seconds
        return state

    def refresh_after_target_failure(self) -> QuickTunnelDiscoveryState:
        self.invalidate()
        return self.discover(force_refresh=True)


_service_lock = threading.Lock()
_service: Optional[QuickTunnelDiscoveryService] = None


def get_quick_tunnel_discovery_service() -> QuickTunnelDiscoveryService:
    global _service
    with _service_lock:
        if _service is None:
            _service = QuickTunnelDiscoveryService()
        return _service


def discover_quick_tunnel_for_client(force_refresh: bool = False) -> Tuple[dict, int]:
    """Return a sanitized response tuple for the Android BFF route."""
    try:
        state = get_quick_tunnel_discovery_service().discover(force_refresh=force_refresh)
    except QuickTunnelDiscoveryError as error:
        return ({
            "version": 1,
            "available": False,
            "status": "error",
            "url": None,
            "updated_ts": 0,
            "error_code": error.error_code,
            "message": str(error),
            "retryable": error.retryable,
        }, error.http_status)

    if not state.available or state.status != "online" or not state.url:
        return ({
            "version": 1,
            "available": False,
            "status": state.status or "offline",
            "url": None,
            "updated_ts": state.updated_ts,
            "message": "Quick Tunnel이 현재 준비되지 않았습니다",
            "retryable": False,
        }, 200)

    return ({
        "version": 1,
        "available": True,
        "status": "online",
        "url": state.url,
        "updated_ts": state.updated_ts,
    }, 200)
