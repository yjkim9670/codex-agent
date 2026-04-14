#!/usr/bin/env bash
set -euo pipefail

LOCAL_PORT="${1:-${CODE_SERVER_PORT:-8080}}"
HTTPS_PORT="${TAILSCALE_CODE_SERVER_HTTPS_PORT:-8080}"

if ! command -v tailscale >/dev/null 2>&1; then
    echo "[ERROR] tailscale command not found on PATH." >&2
    exit 1
fi

if ! tailscale status >/dev/null 2>&1; then
    echo "[ERROR] tailscale is not connected. Run 'tailscale up' first." >&2
    exit 1
fi

echo "[INFO] Exposing code-server http://127.0.0.1:${LOCAL_PORT} via tailscale serve (HTTPS ${HTTPS_PORT})"
SERVE_OUTPUT=''
if ! SERVE_OUTPUT="$(tailscale serve --bg --https="${HTTPS_PORT}" "http://127.0.0.1:${LOCAL_PORT}" 2>&1)"; then
    echo "${SERVE_OUTPUT}" >&2
    if echo "${SERVE_OUTPUT}" | grep -qiE 'serve config denied|access denied'; then
        echo "[ERROR] tailscale serve 권한이 없습니다." >&2
        echo "[ACTION] 로컬 PC에서 1회 실행: sudo tailscale set --operator=${USER}" >&2
        echo "[ACTION] 그다음 다시 실행: ./deploy/tailscale/expose_code_server.sh ${LOCAL_PORT}" >&2
    fi
    exit 1
fi

echo "[INFO] tailscale serve status"
tailscale serve status
echo "[INFO] code-server URL: https://<machine>.<tailnet>.ts.net:${HTTPS_PORT}"
