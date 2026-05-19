"""Application-level encryption helpers for sensitive browser payloads."""

from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_SESSION_TTL_SECONDS = 15 * 60
_SESSION_PRUNE_INTERVAL_SECONDS = 60
_ECDH_CURVE = ec.SECP256R1()
_FILE_KEY_INFO = b'codex-workbench-file-browser-v1'
_CHAT_KEY_INFO = b'codex-workbench-chat-prompt-v1'
_KEY_MATERIAL_BYTES = 64
_AES_GCM_KEY_BYTES = 32
_AES_GCM_IV_BYTES = 12
_MAX_ENCRYPTED_PAYLOAD_BYTES = 1024 * 1024
_PURPOSE_FILE = 'file'
_PURPOSE_CHAT = 'chat'


class FileCryptoError(RuntimeError):
    """Controlled error for encrypted file API payloads."""

    def __init__(self, message, *, error_code='file_crypto_error', status_code=400):
        super().__init__(str(message))
        self.error_code = str(error_code or 'file_crypto_error')
        self.status_code = int(status_code)


@dataclass
class _FileCryptoSession:
    session_id: str
    purpose: str
    request_key: bytes
    response_key: bytes
    expires_at: float
    used_request_ivs: set[bytes] = field(default_factory=set)


_sessions: dict[str, _FileCryptoSession] = {}
_sessions_lock = threading.Lock()
_last_prune_at = 0.0


def _now():
    return time.time()


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def _b64decode(value, field_name: str) -> bytes:
    try:
        return base64.b64decode(str(value or ''), validate=True)
    except (TypeError, ValueError) as exc:
        raise FileCryptoError(
            f'{field_name} 값이 올바른 base64 형식이 아닙니다.',
            error_code='invalid_crypto_payload',
            status_code=400,
        ) from exc


def _json_dumps_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _json_loads_bytes(raw: bytes):
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FileCryptoError(
            '복호화된 요청 JSON이 올바르지 않습니다.',
            error_code='invalid_crypto_payload',
            status_code=400,
        ) from exc
    if not isinstance(payload, dict):
        raise FileCryptoError(
            '복호화된 요청 본문이 올바르지 않습니다.',
            error_code='invalid_crypto_payload',
            status_code=400,
        )
    return payload


def _prune_expired_sessions(now=None):
    global _last_prune_at
    timestamp = _now() if now is None else float(now)
    with _sessions_lock:
        if timestamp - _last_prune_at < _SESSION_PRUNE_INTERVAL_SECONDS:
            return
        expired_ids = [
            session_id
            for session_id, session in _sessions.items()
            if session.expires_at <= timestamp
        ]
        for session_id in expired_ids:
            _sessions.pop(session_id, None)
        _last_prune_at = timestamp


def _session_retry_hint(purpose: str) -> str:
    if purpose == _PURPOSE_FILE:
        return '파일을 다시 열어주세요.'
    if purpose == _PURPOSE_CHAT:
        return '요청을 다시 보내주세요.'
    return '다시 시도해주세요.'


def _get_session(session_id: str, *, purpose: str = '') -> _FileCryptoSession:
    normalized_session_id = str(session_id or '').strip()
    normalized_purpose = str(purpose or '').strip()
    if not normalized_session_id:
        raise FileCryptoError(
            '암호화 세션이 없습니다.',
            error_code='crypto_session_required',
            status_code=400,
        )
    timestamp = _now()
    _prune_expired_sessions(timestamp)
    with _sessions_lock:
        session = _sessions.get(normalized_session_id)
        if session is None:
            raise FileCryptoError(
                f'암호화 세션을 찾을 수 없습니다. {_session_retry_hint(normalized_purpose)}',
                error_code='crypto_session_not_found',
                status_code=401,
            )
        if session.expires_at <= timestamp:
            _sessions.pop(normalized_session_id, None)
            raise FileCryptoError(
                f'암호화 세션이 만료되었습니다. {_session_retry_hint(normalized_purpose)}',
                error_code='crypto_session_expired',
                status_code=401,
            )
        if normalized_purpose and session.purpose != normalized_purpose:
            raise FileCryptoError(
                '암호화 세션의 사용 범위가 올바르지 않습니다.',
                error_code='crypto_session_scope_mismatch',
                status_code=401,
            )
        return session


def _create_crypto_session(client_public_key, *, key_info: bytes, purpose: str):
    """Create an ECDH session and return the public parameters for the browser."""

    client_public_key_bytes = _b64decode(client_public_key, 'client_public_key')
    try:
        client_public = ec.EllipticCurvePublicKey.from_encoded_point(
            _ECDH_CURVE,
            client_public_key_bytes,
        )
    except ValueError as exc:
        raise FileCryptoError(
            '클라이언트 공개키가 올바르지 않습니다.',
            error_code='invalid_crypto_key',
            status_code=400,
        ) from exc

    server_private = ec.generate_private_key(_ECDH_CURVE)
    shared_secret = server_private.exchange(ec.ECDH(), client_public)
    salt = os.urandom(16)
    key_material = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_MATERIAL_BYTES,
        salt=salt,
        info=key_info,
    ).derive(shared_secret)
    request_key = key_material[:_AES_GCM_KEY_BYTES]
    response_key = key_material[_AES_GCM_KEY_BYTES:]
    session_id = secrets.token_urlsafe(24)
    expires_at = _now() + _SESSION_TTL_SECONDS
    server_public_key = server_private.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    with _sessions_lock:
        _sessions[session_id] = _FileCryptoSession(
            session_id=session_id,
            purpose=str(purpose or '').strip(),
            request_key=request_key,
            response_key=response_key,
            expires_at=expires_at,
        )

    return {
        'crypto_session_id': session_id,
        'server_public_key': _b64encode(server_public_key),
        'salt': _b64encode(salt),
        'expires_at': int(expires_at),
        'algorithm': 'ECDH-P256-HKDF-SHA256-AES-256-GCM',
    }


def create_file_crypto_session(client_public_key):
    """Create an ECDH session for file browser payloads."""

    return _create_crypto_session(
        client_public_key,
        key_info=_FILE_KEY_INFO,
        purpose=_PURPOSE_FILE,
    )


def create_chat_crypto_session(client_public_key):
    """Create an ECDH session for chat prompt payloads."""

    return _create_crypto_session(
        client_public_key,
        key_info=_CHAT_KEY_INFO,
        purpose=_PURPOSE_CHAT,
    )


def is_encrypted_file_payload(payload) -> bool:
    return isinstance(payload, dict) and payload.get('encrypted') is True


def is_encrypted_chat_payload(payload) -> bool:
    return isinstance(payload, dict) and payload.get('encrypted') is True


def _decrypt_payload(envelope, *, purpose: str):
    """Decrypt an encrypted API request and return ``(payload, session_id)``."""

    if not isinstance(envelope, dict):
        raise FileCryptoError(
            '암호화 요청 본문이 올바르지 않습니다.',
            error_code='invalid_crypto_payload',
            status_code=400,
        )
    session_id = str(envelope.get('crypto_session_id') or '').strip()
    session = _get_session(session_id, purpose=purpose)
    iv = _b64decode(envelope.get('iv'), 'iv')
    ciphertext = _b64decode(envelope.get('ciphertext'), 'ciphertext')
    if len(iv) != _AES_GCM_IV_BYTES:
        raise FileCryptoError(
            '암호화 요청 IV 길이가 올바르지 않습니다.',
            error_code='invalid_crypto_payload',
            status_code=400,
        )
    if len(ciphertext) > _MAX_ENCRYPTED_PAYLOAD_BYTES:
        raise FileCryptoError(
            '암호화 요청 크기 제한을 초과했습니다.',
            error_code='crypto_payload_too_large',
            status_code=413,
        )

    with _sessions_lock:
        if iv in session.used_request_ivs:
            raise FileCryptoError(
                '이미 사용된 암호화 요청 IV입니다.',
                error_code='crypto_replay_rejected',
                status_code=409,
            )
        session.used_request_ivs.add(iv)

    try:
        raw = AESGCM(session.request_key).decrypt(
            iv,
            ciphertext,
            session_id.encode('ascii'),
        )
    except InvalidTag as exc:
        raise FileCryptoError(
            '암호화 요청 인증에 실패했습니다.',
            error_code='crypto_auth_failed',
            status_code=400,
        ) from exc
    return _json_loads_bytes(raw), session_id


def decrypt_file_payload(envelope):
    """Decrypt an encrypted file API request and return ``(payload, session_id)``."""

    return _decrypt_payload(envelope, purpose=_PURPOSE_FILE)


def decrypt_chat_payload(envelope):
    """Decrypt an encrypted chat prompt request and return ``(payload, session_id)``."""

    return _decrypt_payload(envelope, purpose=_PURPOSE_CHAT)


def _encrypt_payload(session_id: str, payload, *, purpose: str):
    """Encrypt an API response for an existing session."""

    session = _get_session(session_id, purpose=purpose)
    iv = os.urandom(_AES_GCM_IV_BYTES)
    ciphertext = AESGCM(session.response_key).encrypt(
        iv,
        _json_dumps_bytes(payload),
        str(session_id).encode('ascii'),
    )
    return {
        'encrypted': True,
        'crypto_session_id': session_id,
        'iv': _b64encode(iv),
        'ciphertext': _b64encode(ciphertext),
    }


def encrypt_file_payload(session_id: str, payload):
    """Encrypt a file API response for an existing session."""

    return _encrypt_payload(session_id, payload, purpose=_PURPOSE_FILE)


def encrypt_chat_payload(session_id: str, payload):
    """Encrypt a chat prompt API response for an existing session."""

    return _encrypt_payload(session_id, payload, purpose=_PURPOSE_CHAT)
