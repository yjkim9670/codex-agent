#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
APP_DIR="${REPO_ROOT}/apps/codex-agent-web"
ENV_FILE="${1:-${SCRIPT_DIR}/codex-agent-web.vercel.env}"

if ! command -v vercel >/dev/null 2>&1; then
    echo "[ERROR] vercel CLI not found on PATH." >&2
    exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[ERROR] env file not found: ${ENV_FILE}" >&2
    echo "        copy deploy/vercel/codex-agent-web.vercel.env.example first." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

: "${VERCEL_PROJECT_NAME:?VERCEL_PROJECT_NAME is required}"
: "${VITE_CODEX_API_BASE_URL:?VITE_CODEX_API_BASE_URL is required}"
VITE_APP_ENV_NAME="${VITE_APP_ENV_NAME:-private-tailnet}"

SCOPE_ARGS=()
if [[ -n "${VERCEL_SCOPE:-}" ]]; then
    SCOPE_ARGS=(--scope "${VERCEL_SCOPE}")
fi

if [[ ! -d "${APP_DIR}" ]]; then
    echo "[ERROR] app directory not found: ${APP_DIR}" >&2
    exit 1
fi

echo "[INFO] Ensuring Vercel project exists: ${VERCEL_PROJECT_NAME}"
if ! vercel project inspect "${VERCEL_PROJECT_NAME}" "${SCOPE_ARGS[@]}" >/dev/null 2>&1; then
    vercel project add "${VERCEL_PROJECT_NAME}" "${SCOPE_ARGS[@]}"
fi

echo "[INFO] Linking app to Vercel project"
vercel link --cwd "${APP_DIR}" --yes --project "${VERCEL_PROJECT_NAME}" "${SCOPE_ARGS[@]}"

set_env() {
    local name="$1"
    local value="$2"
    local target="$3"

    vercel env add "${name}" "${target}" \
        --cwd "${APP_DIR}" \
        --value "${value}" \
        --force --yes \
        "${SCOPE_ARGS[@]}" >/dev/null
}

set_preview_env() {
    local name="$1"
    local value="$2"

    if vercel env add "${name}" preview \
        --cwd "${APP_DIR}" \
        --value "${value}" \
        --force --yes \
        "${SCOPE_ARGS[@]}" >/dev/null 2>&1; then
        return 0
    fi

    echo "[WARN] Could not update preview env ${name} non-interactively; preview deploys still use --build-env."
}

echo "[INFO] Updating Vercel env vars (development/production)"
for target in development production; do
    set_env "VITE_CODEX_API_BASE_URL" "${VITE_CODEX_API_BASE_URL}" "${target}"
    set_env "VITE_APP_ENV_NAME" "${VITE_APP_ENV_NAME}" "${target}"
done

echo "[INFO] Attempting to sync preview env vars"
set_preview_env "VITE_CODEX_API_BASE_URL" "${VITE_CODEX_API_BASE_URL}"
set_preview_env "VITE_APP_ENV_NAME" "${VITE_APP_ENV_NAME}"
echo "[INFO] Current variables"
vercel env ls --cwd "${APP_DIR}" "${SCOPE_ARGS[@]}" | rg 'VITE_CODEX_API_BASE_URL|VITE_APP_ENV_NAME' || true

echo "[INFO] Step 6 setup finished"
