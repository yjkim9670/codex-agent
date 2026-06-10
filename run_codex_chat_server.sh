#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"
DEFAULT_VENV_DIR="${PARENT_DIR}/.venv"
VENV_DIR="${CODEX_COMMON_VENV_DIR:-${COMMON_PYTHON_VENV:-${VIRTUAL_ENV:-${DEFAULT_VENV_DIR}}}}"
CODEX_APP_RESOURCES_DIR="${CODEX_APP_RESOURCES_DIR:-/Applications/Codex.app/Contents/Resources}"

if [[ -x "${CODEX_APP_RESOURCES_DIR}/codex" ]]; then
    case ":${PATH}:" in
        *":${CODEX_APP_RESOURCES_DIR}:"*) ;;
        *) export PATH="${CODEX_APP_RESOURCES_DIR}:${PATH}" ;;
    esac
fi

resolve_host_python() {
    local candidate
    for candidate in "${CODEX_PYTHON_BIN:-}" "${PYTHON_BIN:-}" "${PYTHON:-}"; do
        [[ -n "${candidate}" ]] || continue
        if [[ "${candidate}" == */* ]]; then
            if [[ -x "${candidate}" ]]; then
                echo "${candidate}"
                return 0
            fi
        elif command -v "${candidate}" >/dev/null 2>&1; then
            command -v "${candidate}"
            return 0
        fi
        echo "Configured Python executable not found or not executable: ${candidate}" >&2
        return 1
    done

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

python_ready_for_workbench() {
    local python_bin="$1"
    "${python_bin}" -c "import sys; sys.exit(1) if sys.version_info < (3, 10) else None; import flask, cryptography" >/dev/null 2>&1
}

resolve_global_python() {
    local candidate
    for candidate in "${CODEX_PYTHON_BIN:-}" "${PYTHON_BIN:-}" "${PYTHON:-}"; do
        if [[ -n "${candidate}" ]]; then
            resolve_host_python
            return $?
        fi
    done

    local fallback=""
    local resolved=""
    for candidate in /opt/homebrew/opt/python@3.12/bin/python3.12 python3.12 python3 python; do
        if command -v "${candidate}" >/dev/null 2>&1; then
            resolved="$(command -v "${candidate}")"
            [[ -n "${fallback}" ]] || fallback="${resolved}"
            if python_ready_for_workbench "${resolved}"; then
                echo "${resolved}"
                return 0
            fi
        fi
    done

    if [[ -n "${fallback}" ]]; then
        echo "${fallback}"
        return 0
    fi

    return 1
}

use_global_python() {
    case "${CODEX_USE_GLOBAL_PYTHON:-${CODEX_SKIP_VENV:-1}}" in
        1|true|TRUE|yes|YES|on|ON)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

ensure_venv_python() {
    local venv_dir="$1"
    local host_python
    host_python="$(resolve_host_python)" || {
        echo "Python executable not found on PATH." >&2
        return 1
    }

    if [[ ! -x "${venv_dir}/bin/python" ]]; then
        echo "[INFO] Venv python missing at ${venv_dir}/bin/python. Recreating..." >&2
        rm -rf "${venv_dir}"
        "${host_python}" -m venv "${venv_dir}"
    fi

    if [[ ! -x "${venv_dir}/bin/python" ]]; then
        echo "Failed to create a usable venv at ${venv_dir}" >&2
        return 1
    fi

    printf '%s\n' "${venv_dir}/bin/python"
}

ensure_requirements() {
    local venv_python="$1"
    local requirements_path="$2"

    if [[ ! -f "${requirements_path}" ]]; then
        return 0
    fi

    if "${venv_python}" -c "import flask, cryptography" >/dev/null 2>&1; then
        return 0
    fi

    echo "[INFO] Installing Python dependencies from ${requirements_path}..."
    local wheelhouse_path
    wheelhouse_path="$(dirname "${requirements_path}")/wheelhouse"
    if [[ -d "${wheelhouse_path}" ]]; then
        "${venv_python}" -m pip install --no-index --find-links "${wheelhouse_path}" -r "${requirements_path}"
    else
        "${venv_python}" -m pip install --upgrade pip
        "${venv_python}" -m pip install -r "${requirements_path}"
    fi
}

check_global_requirements() {
    local python_bin="$1"
    local requirements_path="$2"

    if [[ ! -f "${requirements_path}" ]]; then
        return 0
    fi

    if ! "${python_bin}" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
        echo "Python 3.10+ is required for Workbench. Configured global Python is: ${python_bin}" >&2
        return 1
    fi

    if "${python_bin}" -c "import flask, cryptography" >/dev/null 2>&1; then
        return 0
    fi

    echo "Required Python packages are missing from the configured global Python: ${python_bin}" >&2
    echo "Install them before launching Workbench." >&2
    local wheelhouse_path
    wheelhouse_path="$(dirname "${requirements_path}")/wheelhouse"
    if [[ -d "${wheelhouse_path}" ]]; then
        echo "Suggested command: ${python_bin} -m pip install --no-index --find-links ${wheelhouse_path} -r ${requirements_path}" >&2
    else
        echo "Suggested command: ${python_bin} -m pip install -r ${requirements_path}" >&2
    fi
    return 1
}

if use_global_python; then
    PYTHON_BIN="$(resolve_global_python)" || {
        echo "Python executable not found on PATH." >&2
        exit 1
    }
    check_global_requirements "${PYTHON_BIN}" "${SCRIPT_DIR}/requirements.txt"
else
    PYTHON_BIN="$(ensure_venv_python "${VENV_DIR}")"
    ensure_requirements "${PYTHON_BIN}" "${SCRIPT_DIR}/requirements.txt"
fi

cd "${PARENT_DIR}"

original_args=("$@")
requested_port=3000
show_help=0
declare -a passthrough_args=()
reserved_ports_raw="${CODEX_RESERVED_PORTS:-8080}"

while (($#)); do
    case "$1" in
        -h|--help)
            show_help=1
            passthrough_args+=("$1")
            shift
            ;;
        -p|--port)
            if (($# < 2)); then
                echo "Missing value for $1" >&2
                exit 1
            fi
            requested_port="$2"
            shift 2
            ;;
        --port=*)
            requested_port="${1#*=}"
            shift
            ;;
        --host)
            if (($# < 2)); then
                echo "Missing value for $1" >&2
                exit 1
            fi
            passthrough_args+=("$1" "$2")
            shift 2
            ;;
        --host=*)
            passthrough_args+=("$1")
            shift
            ;;
        --)
            passthrough_args+=("$@")
            break
            ;;
        *)
            passthrough_args+=("$1")
            shift
            ;;
    esac
done

if ((show_help == 1)); then
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/run_codex_chat_server.py" "${original_args[@]}"
fi

if [[ ! "${requested_port}" =~ ^[0-9]+$ ]]; then
    echo "Invalid --port value: ${requested_port}" >&2
    exit 1
fi

if ((requested_port < 1 || requested_port > 65535)); then
    echo "--port must be between 1 and 65535" >&2
    exit 1
fi

port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | awk -v p=":${port}" 'NR > 1 && $4 ~ (p "$") { found = 1 } END { exit(found ? 0 : 1) }'
        return $?
    fi

    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1
        return $?
    fi

    if command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | awk -v p=":${port}" 'NR > 2 && $4 ~ (p "$") { found = 1 } END { exit(found ? 0 : 1) }'
        return $?
    fi

    return 1
}

port_reserved() {
    local port="$1"
    local reserved_list="$2"
    local token
    local -a reserved_tokens=()

    IFS=',' read -r -a reserved_tokens <<< "${reserved_list}"
    for token in "${reserved_tokens[@]}"; do
        token="${token//[[:space:]]/}"
        [[ -z "${token}" ]] && continue
        if [[ "${token}" =~ ^[0-9]+$ ]] && (( port == token )); then
            return 0
        fi
    done

    return 1
}

if port_reserved "${requested_port}" "${reserved_ports_raw}"; then
    echo "Port ${requested_port} is reserved via CODEX_RESERVED_PORTS=${reserved_ports_raw}. Keep 8080 for code-server." >&2
    exit 1
fi

final_port="${requested_port}"
while true; do
    if port_reserved "${final_port}" "${reserved_ports_raw}"; then
        next_port=$((final_port + 1))
        if ((next_port > 65535)); then
            echo "No available port found between ${requested_port} and 65535" >&2
            exit 1
        fi
        echo "[INFO] Port ${final_port} is reserved. Trying ${next_port}..."
        final_port="${next_port}"
        continue
    fi

    if ! port_in_use "${final_port}"; then
        break
    fi

    next_port=$((final_port + 1))
    if ((next_port > 65535)); then
        echo "No available port found between ${requested_port} and 65535" >&2
        exit 1
    fi
    echo "[INFO] Port ${final_port} is unavailable. Trying ${next_port}..."
    final_port="${next_port}"
done

if ((${#passthrough_args[@]})); then
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/run_codex_chat_server.py" "${passthrough_args[@]}" --port "${final_port}"
else
    exec "${PYTHON_BIN}" "${SCRIPT_DIR}/run_codex_chat_server.py" --port "${final_port}"
fi
