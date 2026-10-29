"""Independent protocol client used by integration tests (no server crypto helpers)."""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import Response
from flask.testing import FlaskClient


class EncryptedClient(FlaskClient):
    def raw_open(self, *args, **kwargs):
        return super().open(*args, **kwargs)

    def handshake(self, headers, options):
        private = ec.generate_private_key(ec.SECP256R1())
        public = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        result = self.raw_open('/api/crypto-session', method='POST', headers=headers,
                               json={'client_public_key': base64.b64encode(public).decode()}, **options)
        if result.status_code != 200:
            return result, None
        data = result.json
        remote = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), base64.b64decode(data['server_public_key']))
        material = HKDF(algorithm=hashes.SHA256(), length=64, salt=base64.b64decode(data['salt']),
                        info=b'workbench-conversation-transport-v1').derive(private.exchange(ec.ECDH(), remote))
        return result, dict(id=data['crypto_session_id'], request=AESGCM(material[:32]), response=AESGCM(material[32:]))

    def seal(self, channel, payload):
        iv = os.urandom(12)
        return dict(encrypted=True, crypto_session_id=channel['id'], iv=base64.b64encode(iv).decode(),
                    ciphertext=base64.b64encode(channel['request'].encrypt(iv, json.dumps(payload).encode(),
                                                                          (channel['id'] + ':request').encode())).decode())

    def unseal(self, channel, iv, payload, seq=0):
        assert payload['encrypted'] is True and payload['crypto_session_id'] == channel['id']
        assert payload['seq'] == seq
        return json.loads(channel['response'].decrypt(base64.b64decode(payload['iv']),
                          base64.b64decode(payload['ciphertext']), f"{channel['id']}:response:{iv}:{seq}".encode()))

    def open(self, path, *args, **kwargs):
        if not isinstance(path, str) or not path.startswith('/api/') or path in ('/api/crypto-session', '/api/secure'):
            return super().open(path, *args, **kwargs)
        headers = dict(kwargs.get('headers') or {})
        method = kwargs.pop('method', 'GET')
        options = {k: kwargs[k] for k in ('base_url', 'environ_overrides') if k in kwargs}
        if method == 'GET' and 'X-Chat-CSRF' not in headers:
            with self.session_transaction(**options) as session:
                headers['X-Chat-CSRF'] = session.get('csrf', '')
        response, channel = self.handshake(headers, options)
        if channel is None:
            return response
        # Old tests may reconnect with the standard SSE cursor header.
        envelope = self.seal(channel, dict(path=path, method=method, body=kwargs.get('json', {})))
        response = self.raw_open('/api/secure', method='POST', json=envelope, headers=headers, **options)
        if response.status_code != 200:
            return response
        if response.mimetype == 'text/event-stream':
            chunks = [self.unseal(channel, envelope['iv'], json.loads(frame[6:]), seq)['chunk']
                      for seq, frame in enumerate(response.get_data(as_text=True).strip().split('\n\n')) if frame]
            return Response(''.join(chunks), mimetype='text/event-stream')
        result = self.unseal(channel, envelope['iv'], response.json)
        return Response(json.dumps(result['body']), status=result['status'], mimetype='application/json')
