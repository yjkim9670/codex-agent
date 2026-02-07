#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Venv not found at ${VENV_DIR}. Create it with: python -m venv .venv"
    exit 1
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

PARENT_DIR="$(dirname "${SCRIPT_DIR}")"
cd "${PARENT_DIR}"

exec python "${SCRIPT_DIR}/run_codex_chat_server.py"
