#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CODEX_MODEL_OPTIONS="${CODEX_MODEL_OPTIONS:-DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT}"
export CODEX_REASONING_OPTIONS="${CODEX_REASONING_OPTIONS:-low,medium,high,xhigh}"
export CODEX_CLI_MODEL_PROVIDER="${CODEX_CLI_MODEL_PROVIDER:-dtgpt_linux}"
export CODEX_STORAGE_SUBDIR="${CODEX_STORAGE_SUBDIR:-.agent_state_company}"

exec "${SCRIPT_DIR}/run_codex_chat_server.sh" --host 0.0.0.0 --port 3000 "$@"
