#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${TG_PYTHON:-}/python"

if [[ -z "${TG_PYTHON:-}" ]]; then
    echo "TG_PYTHON is not set. Example: export TG_PYTHON=/path/to/tg_python" >&2
    exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Python executable not found: ${PYTHON_BIN}" >&2
    exit 1
fi

if [[ -z "${MODEL_CHAT_QUIET+x}" ]]; then
    export MODEL_CHAT_QUIET=1
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/run_model_chat_server.py" "$@"
