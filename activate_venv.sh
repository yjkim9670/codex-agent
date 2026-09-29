#!/usr/bin/env bash
set -euo pipefail

# This script must be sourced so the global Python settings stay in the shell.
if [[ -n "${BASH_SOURCE:-}" && "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Please run: source ./activate_venv.sh"
    exit 1
fi

GLOBAL_PYTHON_BIN="${CODEX_PYTHON_BIN:-${PYTHON_BIN:-/opt/homebrew/opt/python@3.14/bin/python3.14}}"
GLOBAL_PYTHON_USER_BIN="/Users/dinya/Library/Python/3.14/bin"
GLOBAL_PYTHON_USER_SITE="/Users/dinya/Library/Python/3.14/lib/python/site-packages"

if [[ ! -x "${GLOBAL_PYTHON_BIN}" ]]; then
    if command -v python3.14 >/dev/null 2>&1; then
        GLOBAL_PYTHON_BIN="$(command -v python3.14)"
    else
        echo "Python 3.14 executable not found. Install python@3.14 or set CODEX_PYTHON_BIN to Python 3.14.x." >&2
        return 1
    fi
fi

if ! "${GLOBAL_PYTHON_BIN}" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)' >/dev/null 2>&1; then
    echo "CODEX_PYTHON_BIN must point to Python 3.14.x: ${GLOBAL_PYTHON_BIN}" >&2
    return 1
fi

GLOBAL_PYTHON_BIN_DIR="$(cd "$(dirname "${GLOBAL_PYTHON_BIN}")" && pwd)"

export CODEX_USE_GLOBAL_PYTHON=1
export CODEX_PYTHON_BIN="${GLOBAL_PYTHON_BIN}"
export PYTHON_BIN="${GLOBAL_PYTHON_BIN}"
export PYTHON="${GLOBAL_PYTHON_BIN}"
case ":${PATH}:" in
    *":${GLOBAL_PYTHON_USER_BIN}:"*) ;;
    *) export PATH="${GLOBAL_PYTHON_USER_BIN}:${PATH}" ;;
esac
export PATH="${GLOBAL_PYTHON_BIN_DIR}:${PATH}"
case ":${PYTHONPATH:-}:" in
    *":${GLOBAL_PYTHON_USER_SITE}:"*) ;;
    *) export PYTHONPATH="${GLOBAL_PYTHON_USER_SITE}${PYTHONPATH:+:${PYTHONPATH}}" ;;
esac
unset VIRTUAL_ENV
unset PYTHONHOME
hash -r 2>/dev/null || true

echo "Using global Python: ${GLOBAL_PYTHON_BIN}"
