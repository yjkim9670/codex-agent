"""Session-bound browser transport. TLS authenticates delivery of the client code."""
import base64
from dataclasses import dataclass, field
import io
import json
import secrets
import threading
import time
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import Response, jsonify, request, session

KEY_INFO = b'workbench-conversation-transport-v1'
TTL = 900
MAX_REQUESTS = 8192


class TransportError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def encode(value):
    return base64.b64encode(value).decode('ascii')


def decode(value):
    try:
        return base64.b64decode(value, validate=True)
    except (TypeError, ValueError):
        raise TransportError('invalid_crypto_payload') from None


@dataclass
class Channel:
    id: str
    owner: str
    expires: float
    inbound: AESGCM
    outbound: AESGCM
    seen: set = field(default_factory=set)

    def encrypt(self, payload, request_iv, seq=0):
        iv = secrets.token_bytes(12)
        aad = f'{self.id}:response:{request_iv}:{seq}'.encode()
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
        return dict(encrypted=True, crypto_session_id=self.id, iv=encode(iv), seq=seq,
                    ciphertext=encode(self.outbound.encrypt(iv, raw, aad)))


class Channels:
    def __init__(self):
        self.entries, self.lock = {}, threading.Lock()

    def create(self, public_key, owner):
        try:
            public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decode(public_key))
        except ValueError:
            raise TransportError('invalid_crypto_key') from None
        private = ec.generate_private_key(ec.SECP256R1())
        salt = secrets.token_bytes(32)
        material = HKDF(algorithm=hashes.SHA256(), length=64, salt=salt, info=KEY_INFO).derive(
            private.exchange(ec.ECDH(), public))
        channel = Channel(secrets.token_urlsafe(24), owner, time.time() + TTL,
                          AESGCM(material[:32]), AESGCM(material[32:]))
        with self.lock:
            self.entries = {k: v for k, v in self.entries.items() if v.expires > time.time()}
            if len(self.entries) >= 256 or sum(c.owner == owner for c in self.entries.values()) >= 16:
                raise TransportError('crypto_capacity', 429)
            self.entries[channel.id] = channel
        return dict(crypto_session_id=channel.id, expires_at=int(channel.expires), salt=encode(salt),
                    server_public_key=encode(private.public_key().public_bytes(
                        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
                    algorithm='ECDH-P256-HKDF-SHA256-AES-256-GCM')

    def decrypt(self, envelope, owner):
        if not isinstance(envelope, dict) or envelope.get('encrypted') is not True:
            raise TransportError('encrypted_transport_required', 428)
        with self.lock:
            channel = self.entries.get(str(envelope.get('crypto_session_id', '')))
            if not channel or channel.expires <= time.time():
                if channel:
                    self.entries.pop(channel.id, None)
                raise TransportError('crypto_session_expired', 401)
            if not owner or not secrets.compare_digest(channel.owner, owner):
                raise TransportError('crypto_session_owner_mismatch', 403)
            iv = decode(envelope.get('iv'))
            if len(iv) != 12:
                raise TransportError('invalid_crypto_payload')
            if iv in channel.seen:
                raise TransportError('crypto_replay_rejected', 409)
            if len(channel.seen) >= MAX_REQUESTS:
                raise TransportError('crypto_session_expired', 401)
            try:
                raw = channel.inbound.decrypt(iv, decode(envelope.get('ciphertext')),
                                              f'{channel.id}:request'.encode())
            except InvalidTag:
                raise TransportError('crypto_auth_failed') from None
            channel.seen.add(iv)
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise TransportError('invalid_crypto_payload') from None
        if not isinstance(payload, dict):
            raise TransportError('invalid_crypto_payload')
        return channel, encode(iv), payload


def install_transport(app):
    channels = Channels()
    app.extensions['chat_channels'] = channels

    @app.errorhandler(TransportError)
    def crypto_error(exc):
        return jsonify(error='암호화 연결을 확인해 주세요. 필요하면 페이지를 새로고침하세요.',
                       code=exc.code), exc.status

    @app.before_request
    def require_encryption():
        if (request.path.startswith('/api/') and request.path not in ('/api/crypto-session', '/api/secure')
                and not request.environ.get('chat.encrypted_dispatch')):
            raise TransportError('encrypted_transport_required', 428)

    @app.post('/api/crypto-session')
    def handshake():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise TransportError('invalid_crypto_payload')
        return jsonify(channels.create(value.get('client_public_key'), session['csrf']))

    @app.post('/api/secure')
    def secure():
        channel, iv, payload = channels.decrypt(request.get_json(silent=True), session.get('csrf', ''))
        path, method = payload.get('path'), payload.get('method', 'GET')
        if not isinstance(path, str) or not isinstance(method, str):
            raise TransportError('invalid_crypto_route')
        parsed = urlsplit(path)
        if (len(path) > 4096 or parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith('/api/')
                or parsed.path in ('/api/crypto-session', '/api/secure')
                or method not in ('GET', 'POST', 'PATCH', 'DELETE')):
            raise TransportError('invalid_crypto_route')
        if not isinstance(payload.get('body', {}), dict):
            raise TransportError('invalid_crypto_payload')
        # A server-owned WSGI flag permits only this authenticated dispatch.
        # Neither a client header nor a forwarded header can set it.
        raw = json.dumps(payload.get('body', {})).encode()
        environ = dict(request.environ, PATH_INFO=parsed.path, QUERY_STRING=parsed.query,
                       REQUEST_METHOD=method, CONTENT_TYPE='application/json', CONTENT_LENGTH=str(len(raw)))
        environ.update({'wsgi.input': io.BytesIO(raw), 'chat.encrypted_dispatch': True})
        with app.request_context(environ):
            response = app.full_dispatch_request()
        if response.mimetype == 'text/event-stream':
            def stream():
                try:
                    for seq, chunk in enumerate(response.response):
                        if time.time() >= channel.expires:
                            break  # Client reconnects with its cursor and a fresh channel.
                        if isinstance(chunk, bytes):
                            chunk = chunk.decode('utf-8')
                        yield 'data: ' + json.dumps(channel.encrypt({'chunk': chunk}, iv, seq)) + '\n\n'
                finally:
                    response.close()
            return Response(stream(), mimetype='text/event-stream', headers={'X-Accel-Buffering': 'no'})
        try:
            body = response.get_json()
            if body is None:
                body = {'error': 'API 응답 형식이 올바르지 않습니다.'}
            return jsonify(channel.encrypt({'status': response.status_code, 'body': body}, iv))
        finally:
            response.close()
