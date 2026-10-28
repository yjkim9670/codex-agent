"""Standalone personal conversation service with explicit network access rules."""
import atexit
import json
import ipaddress
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit

from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory, session, stream_with_context
from werkzeug.exceptions import HTTPException
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
    allowed_hosts = {'localhost', '127.0.0.1', '::1'} | {
        host.strip().lower() for host in os.environ.get('CHAT_ALLOWED_HOSTS', '').split(',') if host.strip()}
    allowed_networks = [ipaddress.ip_network(cidr.strip()) for cidr in
                        ('127.0.0.0/8,::1/128,' + os.environ.get('CHAT_ALLOWED_NETWORKS', '')).split(',') if cidr.strip()]
    engine = provider or Provider(root)
    jobs, lock = {}, threading.Lock()
    slots = threading.BoundedSemaphore(2)
    app.extensions.update(chat_store=store, chat_provider=engine)

    @app.before_request
    def protect():
        # Check the socket peer and exact Host; forwarded headers grant no access.
        try:
            peer = ipaddress.ip_address(request.remote_addr)
            host = urlsplit(request.host_url).hostname.lower()
        except (ValueError, AttributeError):
            abort(403)
        host_allowed = host in allowed_hosts
        if not host_allowed:
            try:
                address = ipaddress.ip_address(host)
                host_allowed = any(address in network for network in allowed_networks)
            except ValueError:
                pass
        if not host_allowed:
            abort(403, description='host_not_allowed')
        if not any(peer in network for network in allowed_networks):
            abort(403, description='network_not_allowed')
        if request.method in ('POST', 'PATCH', 'DELETE'):
            origin = request.headers.get('Origin')
            valid_origins = {request.host_url.rstrip('/')}
            # The local gateway terminates TLS and rewrites Host to loopback.
            # Forwarding metadata only adjusts the Origin check, never access
            # control; remote peers cannot use it to impersonate the gateway.
            if peer.is_loopback:
                forwarded_host = request.headers.get('X-Forwarded-Host', '')
                forwarded_proto = request.headers.get('X-Forwarded-Proto', '')
                if forwarded_proto in ('http', 'https') and forwarded_host:
                    forwarded_origin = f'{forwarded_proto}://{forwarded_host}'
                    try:
                        parsed = urlsplit(forwarded_origin)
                        parsed.port
                        if (parsed.hostname and parsed.netloc == forwarded_host
                                and not parsed.username and not parsed.password
                                and not parsed.path and not parsed.query and not parsed.fragment
                                and not any(c.isspace() or c == ',' for c in forwarded_host)):
                            valid_origins.add(forwarded_origin)
                    except ValueError:
                        pass
                # A tunnel can replace Host without forwarding the public name.
                # Browser-generated Fetch Metadata confirms same-origin fetch;
                # the session-bound CSRF token below is still mandatory.
                if request.headers.get('Sec-Fetch-Site') == 'same-origin' and origin:
                    try:
                        parsed = urlsplit(origin)
                        if (parsed.scheme in ('http', 'https') and parsed.hostname
                                and not parsed.username and not parsed.password
                                and origin == f'{parsed.scheme}://{parsed.netloc}'):
                            valid_origins.add(origin)
                    except ValueError:
                        pass
            if origin and origin not in valid_origins:
                abort(403, description='origin_mismatch')
            if not secrets.compare_digest(request.headers.get('X-Chat-CSRF', ''), session.get('csrf') or secrets.token_hex(32)):
                abort(403, description='csrf_mismatch')

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

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith('/api/'):
            errors = {
                'host_not_allowed': '접속 호스트가 허용되지 않았습니다. 인증 게이트웨이의 Chat 링크를 사용하거나 서버의 --allowed-host 설정을 확인해 주세요.',
                'network_not_allowed': '접속 네트워크가 허용되지 않았습니다. 서버의 허용 네트워크 설정을 확인해 주세요.',
                'origin_mismatch': '외부 접속 주소(Origin)를 확인할 수 없습니다. 게이트웨이의 전달 헤더 설정을 확인해 주세요.',
                'csrf_mismatch': '전송 보안 토큰이 만료되었거나 세션 쿠키가 없습니다. 페이지를 새로고침한 뒤 다시 전송해 주세요.',
            }
            return jsonify(error=errors.get(exc.description, exc.description), code=exc.description if exc.description in errors else 'http_error'), exc.code
        return exc

    @app.errorhandler(500)
    def api_internal_error(exc):
        if request.path.startswith('/api/'):
            return jsonify(error='서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'), 500
        return exc

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
        opts['artifact_scope'] = cid  # Server-owned scope; never accept a client path.
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
