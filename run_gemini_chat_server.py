#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point for the Gemini Chat server."""

import argparse
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
    if os.environ.get('GEMINI_WORKSPACE_DIR'):
        os.environ['GEMINI_PARENT_ACCESS_DECISION'] = 'preset'
        return
    parent_dir = script_path.parent
    os.environ['GEMINI_WORKSPACE_DIR'] = str(parent_dir)
    os.environ['GEMINI_PARENT_ACCESS_DECISION'] = 'auto'
    print(f"[INFO] Parent workspace enabled by default: {parent_dir}")

if original_cwd != script_dir:
    print(f"[INFO] Changing working directory from {original_cwd} to: {script_dir}")
    os.chdir(script_dir)

if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

def parse_args():
    parser = argparse.ArgumentParser(description='Run Gemini Chat server.')
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=3100,
        help='Port to bind the server (default: 3100)',
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host interface to bind (default: 0.0.0.0)',
    )
    args = parser.parse_args()
    if args.port < 1 or args.port > 65535:
        parser.error('--port must be between 1 and 65535')
    return args

if __name__ == '__main__':
    ensure_parent_workspace(script_dir)
    args = parse_args()
    try:
        from gemini_agent.gemini_app import create_gemini_app
    except ImportError as exc:
        print(f"[ERROR] Failed to import Gemini chat modules: {exc}")
        print(f"[ERROR] Current directory: {os.getcwd()}")
        print(f"[ERROR] Script directory: {script_dir}")
        print(f"[ERROR] Python path: {sys.path[:3]}")
        sys.exit(1)

    app = create_gemini_app()
    use_reloader = True
    print("[INFO] Starting Gemini Chat Server...")
    print(f"[INFO] Access the Gemini chat API at: http://localhost:{args.port}")
    app.run(
        debug=True,
        host=args.host,
        port=args.port,
        use_reloader=use_reloader,
        threaded=True,
    )
