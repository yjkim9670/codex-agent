#!/usr/bin/env bash
set -euo pipefail

# This script must be sourced to keep the venv active in the current shell.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Please run: source ./activate_venv.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Venv not found at ${VENV_DIR}. Creating..."
    python -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
echo "Activated venv: ${VENV_DIR}"

if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
    python -m pip install --upgrade pip
    pip install -r "${SCRIPT_DIR}/requirements.txt"
fi
