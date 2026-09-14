import json

import pytest

from codex_agent.services.quick_tunnel_discovery import (
    QuickTunnelDiscoveryError,
    QuickTunnelDiscoveryService,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def encoded(status, **payload):
    return status, json.dumps(payload).encode('utf-8')


def test_online_result_is_cached_until_expiry():
    clock = Clock()
    calls = []

    def fetcher(url, _credential, _timeout):
        calls.append(url)
        return encoded(
            200,
            version=1,
            available=True,
            status='online',
            url='https://one-two-three.trycloudflare.com',
            updated_ts=1,
        )

    service = QuickTunnelDiscoveryService(
        base_url='https://dinya.wind-mintaka.ts.net',
        token='t',
        cache_ttl_seconds=45,
        fetcher=fetcher,
        clock=clock,
    )
    assert service.discover().url == 'https://one-two-three.trycloudflare.com'
    clock.now += 44
    assert service.discover().url == 'https://one-two-three.trycloudflare.com'
    assert len(calls) == 1
    clock.now += 2
    assert service.discover().url == 'https://one-two-three.trycloudflare.com'
    assert len(calls) == 2


def test_offline_result_has_no_url_and_drops_cached_value():
    replies = [
        encoded(200, available=True, status='online', url='https://old-host.trycloudflare.com', updated_ts=1),
        encoded(200, available=False, status='offline', url='https://old-host.trycloudflare.com', updated_ts=2),
    ]
    service = QuickTunnelDiscoveryService(
        base_url='https://dinya.wind-mintaka.ts.net',
        token='t',
        fetcher=lambda *_args: replies.pop(0),
    )
    assert service.discover().available is True
    offline = service.discover(force_refresh=True)
    assert offline.available is False
    assert offline.url is None


def test_unauthorized_upstream_is_non_retryable_configuration_error():
    service = QuickTunnelDiscoveryService(
        base_url='https://dinya.wind-mintaka.ts.net',
        token='t',
        fetcher=lambda *_args: encoded(401, error='unauthorized'),
    )
    with pytest.raises(QuickTunnelDiscoveryError) as captured:
        service.discover()
    assert captured.value.error_code == 'quick_tunnel_secret_misconfigured'
    assert captured.value.retryable is False


def test_service_unavailable_is_reported_as_503():
    service = QuickTunnelDiscoveryService(
        base_url='https://dinya.wind-mintaka.ts.net',
        token='t',
        fetcher=lambda *_args: encoded(503, error='unavailable'),
    )
    with pytest.raises(QuickTunnelDiscoveryError) as captured:
        service.discover()
    assert captured.value.error_code == 'quick_tunnel_discovery_unavailable'
    assert captured.value.http_status == 503


def test_refresh_after_target_failure_bypasses_cached_url():
    replies = [
        encoded(200, available=True, status='online', url='https://old-host.trycloudflare.com', updated_ts=1),
        encoded(200, available=True, status='online', url='https://new-host.trycloudflare.com', updated_ts=2),
    ]
    service = QuickTunnelDiscoveryService(
        base_url='https://dinya.wind-mintaka.ts.net',
        token='t',
        fetcher=lambda *_args: replies.pop(0),
    )
    assert service.discover().url == 'https://old-host.trycloudflare.com'
    assert service.refresh_after_target_failure().url == 'https://new-host.trycloudflare.com'
