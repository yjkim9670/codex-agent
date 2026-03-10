#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
    echo "Windows environment detected. Run PowerShell script: run_window.ps1" >&2
    exit 1
fi

exec "${SCRIPT_DIR}/run_linux.sh" "$@"
