#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-preview}"
ENV_FILE="${2:-}"

if [[ "${TARGET}" != "preview" && "${TARGET}" != "production" ]]; then
    echo "Usage: $0 [preview|production] [env-file]" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
APP_DIR="${REPO_ROOT}/apps/codex-agent-web"
if [[ -z "${ENV_FILE}" ]]; then
    ENV_FILE="${SCRIPT_DIR}/codex-agent-web.vercel.env"
fi

if ! command -v vercel >/dev/null 2>&1; then
    echo "[ERROR] vercel CLI not found on PATH." >&2
    exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[ERROR] env file not found: ${ENV_FILE}" >&2
    echo "        run setup first after copying the example env file." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

: "${VITE_CODEX_API_BASE_URL:?VITE_CODEX_API_BASE_URL is required}"
VITE_APP_ENV_NAME="${VITE_APP_ENV_NAME:-private-tailnet}"

SCOPE_ARGS=()
if [[ -n "${VERCEL_SCOPE:-}" ]]; then
    SCOPE_ARGS=(--scope "${VERCEL_SCOPE}")
fi

echo "[INFO] Building frontend locally"
npm --prefix "${APP_DIR}" ci
npm --prefix "${APP_DIR}" run build

DEPLOY_ARGS=(
    deploy
    --cwd "${APP_DIR}"
    --yes
    --build-env "VITE_CODEX_API_BASE_URL=${VITE_CODEX_API_BASE_URL}"
    --build-env "VITE_APP_ENV_NAME=${VITE_APP_ENV_NAME}"
)

if [[ "${TARGET}" == "production" ]]; then
    DEPLOY_ARGS+=(--prod)
fi

if [[ ${#SCOPE_ARGS[@]} -gt 0 ]]; then
    DEPLOY_ARGS+=("${SCOPE_ARGS[@]}")
fi

echo "[INFO] Deploying (${TARGET})"
DEPLOY_OUTPUT="$(vercel "${DEPLOY_ARGS[@]}")"
DEPLOY_URL="$(
    printf '%s\n' "${DEPLOY_OUTPUT}" \
        | rg -o 'https://[^ ]+\.vercel\.app' \
        | tail -n 1
)"
DEPLOY_URL="${DEPLOY_URL%/}"

echo "[INFO] Deployed URL: ${DEPLOY_URL}"
if [[ -n "${DEPLOY_URL}" ]]; then
    curl --silent --show-error --location --max-time 20 "${DEPLOY_URL}" >/dev/null
    echo "[INFO] Deploy URL check passed"
fi
