"""Loopback Workbench with isolated chat state and real local voice tools."""
import os
from pathlib import Path
import runpy
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


if __name__ == '__main__':
    (ROOT / '.local').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='voice-browser-', dir=ROOT / '.local') as data:
        os.environ.update({
            'CODEX_WORKSPACE_DIR': data,
            'CODEX_HOME': str(Path(data) / 'codex-home'),
            'CODEX_WORKBENCH_SHARED_ACCOUNT_STATE_DIR': str(Path(data) / 'accounts'),
            'CODEX_ENABLE_LEGACY_STATE_IMPORT': 'false',
            'CODEX_DEPLOYMENT_MODE': 'standalone',
            'CODEX_AGENT_BACKEND': 'codex',
            'CODEX_DTGPT_HEALTH_URL': '',
            'CODEX_COMPANY_MODE': 'false',
            'CODEX_CHAT_RELOAD': 'false',
            'CODEX_CHAT_DEBUG': 'false',
        })
        from codex_agent.codex_app import create_codex_app

        def create_fixture_app():
            app = create_codex_app()
            if os.environ.get('CODEX_VERIFY_VOICE_PROXY') == '1':
                inner = app.wsgi_app

                def proxy_host(environ, start_response):
                    # Model a proxy that replaces the public Host before Flask
                    # receives a voice request, retaining the browser's Origin.
                    if environ.get('PATH_INFO', '').startswith('/api/codex/voice'):
                        environ['HTTP_HOST'] = 'internal-workbench:3004'
                    return inner(environ, start_response)

                app.wsgi_app = proxy_host
            return app

        # Keep unrelated account collectors/queue recovery off in this fixture.
        with patch('codex_agent.codex_app.create_codex_app', create_fixture_app), \
             patch('codex_agent.codex_app.ensure_pending_queue_background_worker'), \
             patch('codex_agent.codex_app.ensure_usage_snapshot_background_worker'), \
             patch('codex_agent.services.usage_dashboard.ensure_collection_worker'):
            runpy.run_path(str(ROOT / 'run_codex_chat_server.py'), run_name='__main__')
