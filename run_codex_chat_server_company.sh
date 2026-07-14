#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CODEX_MODEL_OPTIONS="${CODEX_MODEL_OPTIONS:-DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT}"
export CODEX_DTGPT_HEALTH_URL="${CODEX_DTGPT_HEALTH_URL:-http://dtgpt.samsungds.net/llm/health}"
export CODEX_REASONING_OPTIONS="${CODEX_REASONING_OPTIONS:-low,medium,high,xhigh}"
export CODEX_CLI_MODEL_PROVIDER="${CODEX_CLI_MODEL_PROVIDER:-dtgpt_linux}"
export CODEX_STORAGE_SUBDIR="${CODEX_STORAGE_SUBDIR:-.agent_state_company}"
export CODEX_USE_GLOBAL_PYTHON=1
# DTGPT company providers do not use OpenAI account authentication.
export CODEX_REQUIRE_ACCOUNT_LOGIN=0
# Company/offline Workbench must not inherit the legacy global exec lock. The
# older variable is set to 0 as well so older bundled server code stays lock-free.
export CODEX_CLI_EXEC_LOCK=0
export CODEX_CLI_SERIALIZE_EXEC=0

is_codex_app_bundle_cli() {
    local candidate="${1:-}"
    [[ "${candidate}" == *"/Codex.app/Contents/Resources/codex" ]]
}

if [[ -x "${SCRIPT_DIR}/.local/bin/codex" ]]; then
    export CODEX_CLI_BIN="${SCRIPT_DIR}/.local/bin/codex"
fi
if [[ "${CODEX_CLI_BIN:-}" == "${SCRIPT_DIR}/.local/"* ]]; then
    export NPM_CONFIG_PREFIX="${SCRIPT_DIR}/.local"
    export npm_config_prefix="${SCRIPT_DIR}/.local"
fi
if [[ -z "${CODEX_CLI_BIN:-}" ]]; then
    for candidate in \
        "$(dirname "${SCRIPT_DIR}")/.local/bin/codex" \
        "$(dirname "${SCRIPT_DIR}")/../.local/bin/codex" \
        "${HOME:-}/.local/bin/codex"; do
        if [[ -x "${candidate}" ]]; then
            export CODEX_CLI_BIN="${candidate}"
            break
        fi
    done
fi
if [[ -z "${CODEX_CLI_BIN:-}" ]] && command -v codex >/dev/null 2>&1; then
    codex_path="$(command -v codex)"
    if ! is_codex_app_bundle_cli "${codex_path}"; then
        export CODEX_CLI_BIN="${codex_path}"
    fi
fi
if [[ -z "${CODEX_CLI_BIN:-}" ]]; then
    for prefix in "${NPM_PREFIX:-}" "${npm_config_prefix:-}" "${NPM_CONFIG_PREFIX:-}"; do
        [[ -n "${prefix}" ]] || continue
        if [[ -x "${prefix}/bin/codex" ]]; then
            export CODEX_CLI_BIN="${prefix}/bin/codex"
            break
        elif [[ -x "${prefix}/codex" ]]; then
            export CODEX_CLI_BIN="${prefix}/codex"
            break
        fi
    done
fi
if [[ -z "${CODEX_CLI_BIN:-}" ]]; then
    for candidate in \
        "/Applications/Codex.app/Contents/Resources/codex" \
        "${HOME:-}/Applications/Codex.app/Contents/Resources/codex"; do
        if [[ -x "${candidate}" ]]; then
            export CODEX_CLI_BIN="${candidate}"
            break
        fi
    done
fi

exec "${SCRIPT_DIR}/run_codex_chat_server.sh" --host 0.0.0.0 --port 3000 "$@"
