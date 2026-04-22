#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CODEX_MODEL_OPTIONS="${CODEX_MODEL_OPTIONS:-GLM4.7,Gemma-4-31B-IT,OpenAI-GPT-OSS-120B,Qwen3.5-397B-A17B-FP8,NVIDIA-Nemotron-3-Super-120B-A12B-BF16}"
export CODEX_REASONING_OPTIONS="${CODEX_REASONING_OPTIONS:-low,medium,high,xhigh}"
export CODEX_STORAGE_SUBDIR="${CODEX_STORAGE_SUBDIR:-.agent_state_company}"

exec "${SCRIPT_DIR}/run_codex_chat_server.sh" --host 0.0.0.0 --port 3000 "$@"
