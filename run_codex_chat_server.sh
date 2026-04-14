#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"
VENV_DIR="${PARENT_DIR}/.venv"

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

    if "${venv_python}" -c "import flask" >/dev/null 2>&1; then
        return 0
    fi

    echo "[INFO] Installing Python dependencies from ${requirements_path}..."
    "${venv_python}" -m pip install --upgrade pip
    "${venv_python}" -m pip install -r "${requirements_path}"
}

PYTHON_BIN="$(ensure_venv_python "${VENV_DIR}")"
ensure_requirements "${PYTHON_BIN}" "${SCRIPT_DIR}/requirements.txt"

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

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/run_codex_chat_server.py" "${passthrough_args[@]}" --port "${final_port}"
