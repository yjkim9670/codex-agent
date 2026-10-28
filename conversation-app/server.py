"""Standalone loopback-only personal conversation service."""
import atexit
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit

from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory, session, stream_with_context
from shared.chat_accounts import accounts, get_account
from services.conversations import Store, TERMINAL
from services.codex_provider import Provider

ROOT = Path(__file__).resolve().parents[1]


def create_app(data_dir=None, provider=None):
    app = Flask(__name__, root_path=str(Path(__file__).resolve().parent))
    root = Path(data_dir or os.environ.get('CHAT_DATA_DIR') or ROOT / '.agent_state/conversation').resolve()
    store = Store(root)
    secret_file = root / 'session.key'
    if not secret_file.exists():
        try:
            with secret_file.open('x') as target:
                target.write(secrets.token_hex(32))
            secret_file.chmod(0o600)
        except FileExistsError:
            pass
    app.config.update(SECRET_KEY=secret_file.read_text(), SESSION_COOKIE_NAME='workbench_chat_session',
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict', MAX_CONTENT_LENGTH=1024 * 1024)
    engine = provider or Provider(root)
    jobs, lock = {}, threading.Lock()
    slots = threading.BoundedSemaphore(2)
    app.extensions.update(chat_store=store, chat_provider=engine)

    @app.before_request
    def protect():
        # Loopback plus strict Host guards against DNS rebinding and LAN access.
        if request.remote_addr not in ('127.0.0.1', '::1') or request.host.split(':')[0] not in ('localhost', '127.0.0.1'):
            abort(403)
        if request.method in ('POST', 'PATCH', 'DELETE'):
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                abort(403)
            if not secrets.compare_digest(request.headers.get('X-Chat-CSRF', ''), session.get('csrf') or secrets.token_hex(32)):
                abort(403)

    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(ValueError)
    def invalid(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(KeyError)
    def missing(exc):
        return jsonify(error='대상을 찾을 수 없습니다.'), 404

    @app.get('/')
    def index():
        session.setdefault('csrf', secrets.token_hex(32))
        return render_template('index.html', csrf=session['csrf'])

    @app.get('/health')
    def health():
        with store.db() as db:
            db.execute('SELECT 1')
        return jsonify(status='ok', application='workbench-chat')

    @app.get('/static/fonts/<path:name>')
    def fonts(name):
        return send_from_directory(ROOT / 'codex-web-app/static/fonts', name)

    @app.get('/static/vendor/<name>')
    def vendor(name):
        if name not in ('marked-18.0.6.umd.js', 'dompurify-3.4.12.min.js'):
            abort(404)
        return send_from_directory(ROOT / 'codex-web-app/static/vendor', name)

    @app.get('/api/accounts')
    def list_accounts():
        return jsonify(accounts=[{k: a[k] for k in ('id', 'label', 'authenticated')} for a in accounts()])

    @app.get('/api/models')
    def models():
        account = get_account(request.args.get('account_id'))
        return jsonify(models=engine.models(account, force=request.args.get('refresh') == '1'))

    @app.route('/api/settings', methods=['GET', 'PATCH'])
    def settings():
        if request.method == 'PATCH':
            value = request.get_json()
            if not isinstance(value, dict):
                raise ValueError('설정 형식이 올바르지 않습니다.')
            store.settings({k: str(value.get(k, ''))[:160] for k in ('account_id', 'model', 'effort', 'search', 'preset')})
        return jsonify(store.settings())

    @app.route('/api/conversations', methods=['GET', 'POST'])
    def conversations():
        return jsonify(store.create() if request.method == 'POST' else store.conversations(request.args.get('q', '')[:160]))

    @app.route('/api/conversations/<cid>', methods=['PATCH', 'DELETE'])
    def change(cid):
        title = str((request.get_json(silent=True) or {}).get('title', '')).strip()
        if request.method == 'PATCH' and not title:
            raise ValueError('제목을 입력해 주세요.')
        store.change(cid, title, request.method == 'DELETE')
        return jsonify(ok=True, note='화면 이력 삭제 후에도 사용량 회계 및 Codex rollout은 보존됩니다.')

    @app.route('/api/conversations/<cid>/messages', methods=['GET', 'POST'])
    def messages(cid):
        if request.method == 'GET':
            return jsonify(messages=store.messages(cid))
        value = request.get_json()
        content = str(value.get('content', '')).strip()
        retry = value.get('retry_attempt_id')
        if (not content and not retry) or len(content) > 60000:
            raise ValueError('메시지는 1~60,000자로 입력해 주세요.')
        rid = str(value.get('request_id', ''))
        if not 8 <= len(rid) <= 100:
            raise ValueError('request_id가 필요합니다.')
        opts = value.get('settings') or store.settings()
        account = get_account(opts.get('account_id'))
        opts = {k: str(opts.get(k) or '') for k in ('account_id', 'model', 'effort', 'search', 'preset')}
        if opts['search'] not in ('auto', 'on', 'off'):
            raise ValueError('검색 설정이 올바르지 않습니다.')
        opts['provider_account_id'] = account['provider_account_id']
        attempt, created = store.enqueue(cid, content, rid, opts, retry)
        if created:
            cancel = threading.Event()
            with lock:
                jobs[attempt['id']] = cancel
            def work():
                acquired = False
                try:
                    while not cancel.is_set():
                        acquired = slots.acquire(timeout=0.2)
                        if acquired:
                            break
                    if cancel.is_set():
                        store.emit(attempt['id'], 'done', {'status': 'cancelled'})
                        return
                    engine.run(account, opts, store.history(attempt['id']),
                               lambda kind, data: store.emit(attempt['id'], kind, data), cancel)
                except Exception as exc:
                    error = str(exc) if isinstance(exc, ValueError) else '요청 처리 중 오류가 발생했습니다. 다시 시도해 주세요.'
                    store.emit(attempt['id'], 'done', {'status': 'failed', 'error': error})
                finally:
                    if acquired:
                        slots.release()
                    with lock:
                        jobs.pop(attempt['id'], None)
            threading.Thread(target=work, daemon=True).start()
        return jsonify(attempt=attempt), 202 if created else 200

    @app.get('/api/attempts/<aid>/events')
    def events(aid):
        store.attempt(aid)
        try:
            after = max(0, int(request.headers.get('Last-Event-ID') or request.args.get('after', '0')))
        except ValueError:
            raise ValueError('이벤트 위치가 올바르지 않습니다.') from None
        @stream_with_context
        def stream():
            cursor = after
            while True:
                rows = store.events(aid, cursor)
                for row in rows:
                    cursor = row['id']
                    yield f"id: {cursor}\nevent: {row['type']}\ndata: {row['data']}\n\n"
                if store.attempt(aid)['status'] in TERMINAL:
                    # Drain events committed between the query and terminal read.
                    for row in store.events(aid, cursor):
                        yield f"id: {row['id']}\nevent: {row['type']}\ndata: {row['data']}\n\n"
                    return
                yield ': keepalive\n\n'
                with store.wake:
                    store.wake.wait(timeout=10)
        return Response(stream(), mimetype='text/event-stream', headers={'X-Accel-Buffering': 'no'})

    @app.post('/api/attempts/<aid>/cancel')
    def cancel(aid):
        store.attempt(aid)
        with lock:
            event = jobs.get(aid)
            if event:
                event.set()
        return jsonify(ok=True)

    @app.get('/api/usage/summary')
    def usage():
        return jsonify(store.usage())

    def shutdown():
        with lock:
            for event in jobs.values():
                event.set()
    atexit.register(shutdown)
    return app
