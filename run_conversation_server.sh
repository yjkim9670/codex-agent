#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
export CHAT_DATA_DIR="${CHAT_DATA_DIR:-$PWD/.agent_state/conversation}"
chat_python="${CHAT_PYTHON_BIN:-}"
if [[ -z "$chat_python" ]]; then
  for candidate in /opt/homebrew/bin/python3.14 /usr/local/bin/python3.14; do
    if [[ -x "$candidate" ]]; then chat_python="$candidate"; break; fi
  done
fi
if [[ -z "$chat_python" ]]; then chat_python="$(command -v python3)"; fi
# Proc Manager uses its works directory as HOME. Resolve Python's user packages
# from the OS login home, while preserving an explicitly configured user base.
if [[ -z "${PYTHONUSERBASE:-}" ]]; then
  PYTHONUSERBASE="$("$chat_python" -S -c 'import os, pwd, sys; from pathlib import Path; home = Path(pwd.getpwuid(os.getuid()).pw_dir); print(home / "Library" / "Python" / f"{sys.version_info.major}.{sys.version_info.minor}" if sys.platform == "darwin" and sys._framework else home / ".local")')"
  export PYTHONUSERBASE
fi
"$chat_python" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"; import flask'
exec "$chat_python" run_conversation_server.py "$@"
