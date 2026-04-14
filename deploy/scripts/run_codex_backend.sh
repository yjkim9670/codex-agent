#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE_DEFAULT="${REPO_ROOT}/deploy/codex-backend.env"
ENV_FILE="${CODEX_BACKEND_ENV_FILE:-${ENV_FILE_DEFAULT}}"

if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${ENV_FILE}"
    set +a
else
    echo "[WARN] Environment file not found: ${ENV_FILE}" >&2
fi

HOST="${CODEX_BACKEND_HOST:-127.0.0.1}"
PORT="${CODEX_BACKEND_PORT:-6000}"

cd "${REPO_ROOT}"
exec "${REPO_ROOT}/run_codex_chat_server.sh" --host "${HOST}" --port "${PORT}" "$@"
