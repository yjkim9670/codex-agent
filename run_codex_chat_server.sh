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
    exec python "${SCRIPT_DIR}/run_codex_chat_server.py" "${original_args[@]}"
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

exec python "${SCRIPT_DIR}/run_codex_chat_server.py" "${passthrough_args[@]}" --port "${final_port}"
