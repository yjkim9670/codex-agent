#!/usr/bin/env python3
"""Independent Chat entrypoint; does not load Workbench's server."""
import argparse
import fcntl
import importlib.util
import os
import signal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'conversation-app'))
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description='Workbench Chat (personal Codex, loopback only)')
    parser.add_argument('--host', choices=['127.0.0.1', 'localhost'], default='127.0.0.1')
    parser.add_argument('--port', type=int, default=3101)
    args = parser.parse_args()
    def terminate(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    root = Path(os.environ.get('CHAT_DATA_DIR', ROOT / '.agent_state/conversation')).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'server.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('이 Chat 데이터 경로를 사용하는 서버가 이미 실행 중입니다.')
        spec = importlib.util.spec_from_file_location('conversation_server', ROOT / 'conversation-app/server.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        app = module.create_app(root)
        app.run(host=args.host, port=args.port, threaded=True, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
