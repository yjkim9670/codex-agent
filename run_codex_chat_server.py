#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point for the Codex Chat server."""

import sys
import os
from pathlib import Path

if sys.platform == 'win32':
    os.environ['PYTHONUTF8'] = '1'
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

script_dir = Path(__file__).resolve().parent
repo_root = script_dir
original_cwd = Path.cwd()

def ensure_parent_workspace(script_path):
    if os.environ.get('CODEX_WORKSPACE_DIR'):
        os.environ['CODEX_PARENT_ACCESS_DECISION'] = 'preset'
        return
    parent_dir = script_path.parent
    os.environ['CODEX_WORKSPACE_DIR'] = str(parent_dir)
    os.environ['CODEX_PARENT_ACCESS_DECISION'] = 'auto'
    print(f"[INFO] Parent workspace enabled by default: {parent_dir}")

if original_cwd != script_dir:
    print(f"[INFO] Changing working directory from {original_cwd} to: {script_dir}")
    os.chdir(script_dir)
    os.environ['WERKZEUG_RUN_MAIN'] = 'true'

if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

if __name__ == '__main__':
    ensure_parent_workspace(script_dir)
    try:
        from codex_agent.codex_app import create_codex_app
    except ImportError as exc:
        print(f"[ERROR] Failed to import Codex chat modules: {exc}")
        print(f"[ERROR] Current directory: {os.getcwd()}")
        print(f"[ERROR] Script directory: {script_dir}")
        print(f"[ERROR] Python path: {sys.path[:3]}")
        sys.exit(1)

    app = create_codex_app()
    use_reloader = (original_cwd == script_dir)
    print("[INFO] Starting Codex Chat Server...")
    print("[INFO] Access the Codex chat API at: http://localhost:3000")
    app.run(debug=True, host='0.0.0.0', port=3000, use_reloader=use_reloader, threaded=True)
