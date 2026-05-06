"""SMTP mail helpers for file-panel archive delivery."""

from __future__ import annotations

import smtplib
import ssl
from email.header import Header
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, parseaddr

from ..config import (
    CODEX_MAIL_FROM,
    CODEX_MAIL_FROM_NAME,
    CODEX_MAIL_PASSWORD,
    CODEX_MAIL_SMTP_HOST,
    CODEX_MAIL_SMTP_PORT,
    CODEX_MAIL_SMTP_SSL,
    CODEX_MAIL_SMTP_STARTTLS,
    CODEX_MAIL_SMTP_TIMEOUT_SECONDS,
    CODEX_MAIL_USERNAME,
)


class MailSendError(RuntimeError):
    """Controlled error for mail sending API responses."""

    def __init__(self, message, *, error_code='mail_send_error', status_code=400):
        super().__init__(str(message))
        self.error_code = str(error_code or 'mail_send_error')
        self.status_code = int(status_code)


def _coerce_address_header_values(value):
    if value in (None, ''):
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = [str(item or '') for item in value]
    else:
        raise MailSendError(
            '메일 주소 형식이 올바르지 않습니다.',
            error_code='invalid_recipient',
            status_code=400,
        )
    return [item.replace(';', ',').replace('\n', ',') for item in values if str(item or '').strip()]


def _normalize_email_addresses(value, *, field_name='recipient', required=False):
    raw_values = _coerce_address_header_values(value)
    parsed = getaddresses(raw_values)
    addresses = []
    seen = set()
    for display_name, address in parsed:
        normalized_name, normalized_address = parseaddr(formataddr((display_name, address)))
        normalized_address = str(normalized_address or '').strip()
        if not normalized_address:
            continue
        if '@' not in normalized_address or any(char.isspace() for char in normalized_address):
            raise MailSendError(
                f'{field_name} 주소가 올바르지 않습니다: {normalized_address}',
                error_code='invalid_recipient',
                status_code=400,
            )
        key = normalized_address.lower()
        if key in seen:
            continue
        seen.add(key)
        addresses.append(formataddr((normalized_name, normalized_address)) if normalized_name else normalized_address)

    if required and not addresses:
        raise MailSendError(
            '받는 사람을 입력해주세요.',
            error_code='missing_recipient',
            status_code=400,
        )
    return addresses


def _normalize_single_delivery_address(value, *, field_name='address'):
    addresses = _normalize_email_addresses(value, field_name=field_name, required=True)
    if len(addresses) != 1:
        raise MailSendError(
            f'{field_name} 주소는 하나만 설정해주세요.',
            error_code='invalid_address',
            status_code=400,
        )
    address = parseaddr(addresses[0])[1].strip()
    if not address:
        raise MailSendError(
            f'{field_name} 주소가 올바르지 않습니다.',
            error_code='invalid_address',
            status_code=400,
        )
    return address


def _extract_delivery_addresses(addresses):
    return [parseaddr(address)[1] for address in addresses if parseaddr(address)[1]]


def _normalize_subject(value):
    subject = str(value or '').strip()
    if not subject:
        raise MailSendError(
            '메일 제목을 입력해주세요.',
            error_code='missing_subject',
            status_code=400,
        )
    if len(subject) > 200:
        raise MailSendError(
            '메일 제목은 200자 이내로 입력해주세요.',
            error_code='subject_too_long',
            status_code=400,
        )
    return subject


def _normalize_body(value):
    body = str(value or '')
    if len(body) > 20000:
        raise MailSendError(
            '메일 본문은 20000자 이내로 입력해주세요.',
            error_code='body_too_long',
            status_code=400,
        )
    return body


def _require_mail_configuration():
    username = str(CODEX_MAIL_USERNAME or '').strip()
    password = str(CODEX_MAIL_PASSWORD or '')
    sender = str(CODEX_MAIL_FROM or username).strip()
    host = str(CODEX_MAIL_SMTP_HOST or '').strip()
    if not host:
        raise MailSendError(
            'SMTP 서버가 설정되지 않았습니다.',
            error_code='mail_not_configured',
            status_code=503,
        )
    if not username:
        raise MailSendError(
            'CODEX_MAIL_USERNAME 환경변수를 설정해주세요.',
            error_code='mail_not_configured',
            status_code=503,
        )
    if not password:
        raise MailSendError(
            'CODEX_MAIL_PASSWORD 환경변수를 설정해주세요.',
            error_code='mail_not_configured',
            status_code=503,
        )
    if not sender:
        raise MailSendError(
            'CODEX_MAIL_FROM 환경변수를 설정해주세요.',
            error_code='mail_not_configured',
            status_code=503,
        )
    normalized_sender = _normalize_single_delivery_address(sender, field_name='보낸 사람')
    return {
        'host': host,
        'port': int(CODEX_MAIL_SMTP_PORT),
        'username': username,
        'password': password,
        'sender': normalized_sender,
    }


def _format_sender(sender):
    from_name = str(CODEX_MAIL_FROM_NAME or '').strip()
    if not from_name:
        return sender
    return formataddr((str(Header(from_name, 'utf-8')), sender))


def build_mail_message(*, to, cc=None, bcc=None, subject='', body='', archive_payload=None):
    archive = archive_payload if isinstance(archive_payload, dict) else {}
    archive_content = archive.get('content') or b''
    archive_name = str(archive.get('download_name') or 'codex-mail.zip').strip() or 'codex-mail.zip'
    if not isinstance(archive_content, (bytes, bytearray)) or not archive_content:
        raise MailSendError(
            '첨부할 압축 파일을 만들지 못했습니다.',
            error_code='missing_archive',
            status_code=400,
        )

    config = _require_mail_configuration()
    to_addresses = _normalize_email_addresses(to, field_name='받는 사람', required=True)
    cc_addresses = _normalize_email_addresses(cc, field_name='참조')
    bcc_addresses = _normalize_email_addresses(bcc, field_name='숨은 참조')

    message = EmailMessage()
    message['From'] = _format_sender(config['sender'])
    message['To'] = ', '.join(to_addresses)
    if cc_addresses:
        message['Cc'] = ', '.join(cc_addresses)
    message['Subject'] = _normalize_subject(subject)
    message.set_content(_normalize_body(body) or '첨부 파일을 확인해주세요.')
    message.add_attachment(
        bytes(archive_content),
        maintype='application',
        subtype='zip',
        filename=archive_name,
    )
    return message, {
        **config,
        'to': to_addresses,
        'cc': cc_addresses,
        'bcc': bcc_addresses,
        'archive_name': archive_name,
        'archive_size': len(archive_content),
    }


def send_mail_with_archive(*, to, cc=None, bcc=None, subject='', body='', archive_payload=None):
    message, config = build_mail_message(
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        body=body,
        archive_payload=archive_payload,
    )
    recipients = _extract_delivery_addresses([*config['to'], *config['cc'], *config['bcc']])
    context = ssl.create_default_context()

    try:
        if CODEX_MAIL_SMTP_SSL:
            with smtplib.SMTP_SSL(
                config['host'],
                config['port'],
                timeout=int(CODEX_MAIL_SMTP_TIMEOUT_SECONDS),
                context=context,
            ) as server:
                server.login(config['username'], config['password'])
                server.send_message(message, to_addrs=recipients)
        else:
            with smtplib.SMTP(
                config['host'],
                config['port'],
                timeout=int(CODEX_MAIL_SMTP_TIMEOUT_SECONDS),
            ) as server:
                server.ehlo()
                if CODEX_MAIL_SMTP_STARTTLS:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(config['username'], config['password'])
                server.send_message(message, to_addrs=recipients)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailSendError(
            f'SMTP 메일 전송에 실패했습니다: {exc}',
            error_code='smtp_send_error',
            status_code=502,
        ) from exc

    return {
        'sent': True,
        'from': config['sender'],
        'to': config['to'],
        'cc': config['cc'],
        'bcc_count': len(config['bcc']),
        'archive_name': config['archive_name'],
        'archive_size': config['archive_size'],
    }
