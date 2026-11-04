"""Temporary loopback-only server with deterministic model events; no real accounts."""
import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
import threading

from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'conversation-app'))
spec = importlib.util.spec_from_file_location('conversation_fixture', ROOT / 'conversation-app/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

from services.codex_provider import Provider as ArtifactProvider
from services.artifacts import TOOL_NAME

PREVIEW_CONTENT = 'print("미리보기")\n' + 'x' * 70000 + '\n<script>window.fileXss=true</script>'

HTML_CONTENT = ('<!doctype html><html><head><meta charset="utf-8"><title>HTML fixture</title></head>'
                '<body><h1>렌더링 확인</h1><button id="counter">0</button><script>'
                'localStorage.setItem("fixture", "ready");'
                'document.querySelector("#counter").onclick=()=>{document.querySelector("#counter").textContent="1";};'
                'try { parent.document.body.dataset.escaped="yes"; } catch(e) {}'
                '</script><!--' + 'x' * (5 * 1024 * 1024) + '--></body></html>')

ANSWER = '''**Hello**

> 읽기 쉬운 인용문

```python
print("hello")
```

| 항목 | 값 |
| --- | --- |
| 사용 | 24 |

[Source](https://example.com)
<script>window.xss=true</script>
[Bad](javascript:alert(1))
'''


class Provider:
    fail_limits = False

    def read_artifact(self, cid, path):
        return self.artifacts.read_artifact(cid, path)

    def models(self, account, force=False):
        return [dict(model='test-model', displayName='Test Model', defaultReasoningEffort='low',
                     supportedReasoningEfforts=[dict(reasoningEffort='low'), dict(reasoningEffort='high')])]

    def limits(self, account, force=False):
        if self.fail_limits:
            raise ValueError('계정 한도 조회 실패')
        return dict(five_hour=dict(used_percent=24, remaining_percent=76, resets_at="2033-05-18T03:33:20+00:00"),
                    weekly=dict(used_percent=60, remaining_percent=40, resets_at=2000500000))

    def run(self, account, settings, history, emit, cancel):
        emit('limits', {'before': self.limits(account)})
        emit('provider', dict(model='test-model', reasoning_effort='low', thread_id='fixture', turn_id=str(time.time_ns())))
        if 'file preview fixture' in history[-1]['content']:
            artifacts = self.artifacts.open_artifacts('fixture', settings['artifact_scope'])
            try:
                artifacts.call({'tool': TOOL_NAME, 'arguments': {'operation': 'write', 'path': 'sample.py', 'content': PREVIEW_CONTENT}})
                artifacts.call({'tool': TOOL_NAME, 'arguments': {'operation': 'write', 'path': 'sample.html', 'content': HTML_CONTENT}})
                emit('delta', dict(text=f'[sample.py]({artifacts.root}/sample.py) [sample.html]({artifacts.root}/sample.html)'))
                emit('done', dict(status='completed'))
            finally:
                artifacts.close()
            return
        emit('title', dict(title='영어 번역'))
        emit('delta', dict(text='**Hello**\n'))
        if 'cancel me' in history[-1]['content']:
            cancel.wait(10)
            emit('done', dict(status='cancelled'))
            return
        for start in range(len('**Hello**\n'), len(ANSWER), 3):
            if cancel.wait(.012):
                emit('done', dict(status='cancelled'))
                return
            emit('delta', dict(text=ANSWER[start:start+3]))
        emit('usage', dict(total=dict(inputTokens=100, outputTokens=23, totalTokens=123)))
        emit('done', dict(status='completed'))
        emit('limits', {'after': {**self.limits(account),
                                'five_hour': dict(used_percent=25, resets_at='2033-05-18T03:33:20+00:00')}})
        timer = threading.Timer(.2, lambda: emit('limits', {'delayed': {
            'five_hour': dict(used_percent=26, resets_at='2033-05-18T03:33:20+00:00'),
            'weekly': dict(used_percent=60.5, resets_at=2000500000)}}))
        timer.daemon = True
        timer.start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--https-proxy', action='store_true',
                        help='Temporary self-signed TLS with loopback gateway Host/header rewriting.')
    args = parser.parse_args()
    account = dict(id='personal', label='Personal Codex', authenticated=True, provider_account_id='fixture')
    server.accounts = lambda: [account]
    server.get_account = lambda _: account
    with tempfile.TemporaryDirectory(prefix='conversation-browser-') as data:
        provider = Provider()
        provider.artifacts = ArtifactProvider(data)
        app = server.create_app(data, provider)
        @app.post('/__fixture/limits/<mode>')
        def fixture_limits(mode):
            provider.fail_limits = mode == 'fail'
            return {'ok': True}
        application = DispatcherMiddleware(app, {'/chat': app, '/apps/workbench-chat': app})
        if args.https_proxy:
            dispatch = application
            def application(environ, start_response):
                # Model TLS termination before a Host-rewriting HTTP gateway.
                public_host = environ['HTTP_HOST']
                duplicate = environ['PATH_INFO'].startswith('/apps/')
                environ.update(HTTP_HOST='127.0.0.1:3101', SERVER_NAME='127.0.0.1',
                               SERVER_PORT='3101', **{'wsgi.url_scheme': 'http'})
                environ['HTTP_X_FORWARDED_HOST'] = ('localhost:19443, ' if duplicate else '') + public_host
                environ['HTTP_X_FORWARDED_PROTO'] = 'https, http' if duplicate else 'https'
                return dispatch(environ, start_response)
        http = make_server('127.0.0.1', args.port, application, threaded=True,
                           ssl_context='adhoc' if args.https_proxy else None)
        scheme = 'https' if args.https_proxy else 'http'
        print(f'{scheme}://127.0.0.1:{http.server_port}', flush=True)
        try:
            http.serve_forever()
        finally:
            http.server_close()


if __name__ == '__main__':
    main()
