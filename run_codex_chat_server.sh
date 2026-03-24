#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

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
        echo "Python executable not found on PATH." >&2
        return 1
    }

    if [[ ! -x "${venv_dir}/bin/python" ]]; then
        echo "[INFO] Venv python missing at ${venv_dir}/bin/python. Recreating..." >echo "[INFO] Venv python missing at /bin/python. Recreating..." >&22
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

    if "${venv_python}" -c "import flask" >/dev/null 2>&1; then
        return 0
    fi

    echo "[INFO] Installing Python dependencies from ${requirements_path}..."
    "${venv_python}" -m pip install --upgrade pip
    "${venv_python}" -m pip install -r "${requirements_path}"
}

PYTHON_BIN="$(ensure_venv_python "${VENV_DIR}")"
ensure_requirements "${PYTHON_BIN}" "${SCRIPT_DIR}/requirements.txt"

PARENT_DIR="$(dirname "${SCRIPT_DIR}")"
cd "${PARENT_DIR}"

original_args=("$@")
requested_port=3000
show_help=0
declare -a passthrough_args=()

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

    if command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | awk -v p=":${port}" 'NR > 2 && $4 ~ (p "$") { found = 1 } END { exit(found ? 0 : 1) }'
        return $?
    fi

    return 1
}

final_port="${requested_port}"
while port_in_use "${final_port}"; do
    next_port=$((final_port + 1))
    if ((next_port > 65535)); then
        echo "No available port found between ${requested_port} and 65535" >&2
        exit 1
    fi
    echo "[INFO] Port ${final_port} is unavailable. Trying ${next_port}..."
    final_port="${next_port}"
done

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/run_codex_chat_server.py" "${passthrough_args[@]}" --port "${final_port}"
