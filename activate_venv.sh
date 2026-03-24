#!/usr/bin/env bash
set -euo pipefail

# This script must be sourced to keep the venv active in the current shell.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Please run: source ./activate_venv.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
VENV_PYTHON=""

resolve_host_python() {
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return 0
    fi
    if command -v python >/dev/null 2>&1; then
        echo "python"
        return 0
    fi
    return 1
}

ensure_venv_python() {
    local venv_dir="$1"
    local host_python
    host_python="$(resolve_host_python)" || {
        echo "Python executable not found on PATH."
        return 1
    }

    if [[ ! -x "${venv_dir}/bin/python" ]]; then
        echo "Venv python missing at ${venv_dir}/bin/python. Recreating..."
        rm -rf "${venv_dir}"
        "${host_python}" -m venv "${venv_dir}"
    fi

    if [[ ! -x "${venv_dir}/bin/python" ]]; then
        echo "Failed to create a usable venv at ${venv_dir}"
        return 1
    fi

    printf '%s\n' "${venv_dir}/bin/python"
}

VENV_PYTHON="$(ensure_venv_python "${VENV_DIR}")"

# Activate environment without relying on potentially stale activate scripts.
export VIRTUAL_ENV="${VENV_DIR}"
case ":${PATH}:" in
    *":${VENV_DIR}/bin:"*) ;;
    *) export PATH="${VENV_DIR}/bin:${PATH}" ;;
esac
unset PYTHONHOME
hash -r 2>/dev/null || true

echo "Activated venv: ${VENV_DIR}"

LOCAL_ENV_SCRIPT="${SCRIPT_DIR}/model_agent_env.local.sh"
if [[ -f "${LOCAL_ENV_SCRIPT}" ]]; then
    # shellcheck disable=SC1091
    source "${LOCAL_ENV_SCRIPT}"
    echo "Loaded local model env: ${LOCAL_ENV_SCRIPT}"
fi

if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
    "${VENV_PYTHON}" -m pip install --upgrade pip
    "${VENV_PYTHON}" -m pip install -r "${SCRIPT_DIR}/requirements.txt"
fi
