#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN=""

if [[ -n "${TG_PYTHON:-}" ]]; then
    PYTHON_BIN="${TG_PYTHON}/python"
    if [[ ! -x "${PYTHON_BIN}" ]]; then
        echo "Python executable not found: ${PYTHON_BIN}" >&2
        exit 1
    fi
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo "Python executable not found. Set TG_PYTHON or install python3." >&2
    exit 1
fi

cd "${REPO_ROOT}"

# Default behavior suppresses noisy GUI environment logs (Gtk/Gdk/Qt/Xlib/etc.).
# Set DTGPT_AGENT_SHOW_GUI_NOISE=1 to print all stderr lines unchanged.
if [[ "${DTGPT_AGENT_SHOW_GUI_NOISE:-0}" == "1" ]]; then
    exec "${PYTHON_BIN}" -m dtgpt_agent "$@"
fi

exec "${PYTHON_BIN}" -m dtgpt_agent "$@" \
    2> >(
        awk 'BEGIN { IGNORECASE=1 }
             !($0 ~ /^(gtk|gdk|qt|qxcbconnection|libgl|xlib|dbus|objc\[)/) {
                 print > "/dev/stderr"
                 fflush("/dev/stderr")
             }'
    )
