import socket

import pytest

from app.config import get_settings
from app.services import url_safety
from app.services.url_safety import UnsafeURLError, check_outbound_url, pick_connect_ip

REAL_RESOLVE = url_safety.resolve_host  # captured before the autouse fake_dns patch


@pytest.fixture
def allow_hosts(monkeypatch):
    def set_hosts(value: str):
        monkeypatch.setenv("WEBHOOK_ALLOWED_HOSTS", value)
        get_settings.cache_clear()

    yield set_hosts
    monkeypatch.delenv("WEBHOOK_ALLOWED_HOSTS", raising=False)
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "javascript:alert(1)",
        "http:///path",
        "example.com/hook",
        "",
        "http://user:pw@example.com/",
        "http://user@example.com/",
        "http://example.com:99999/",
        "http://example.com:abc/",
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://0.0.0.0/",
        "http://224.0.0.1/",
        "http://255.255.255.255/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:10.0.0.1]/",
        "http://[2002:7f00:1::]/",
        "http://localhost/",
        "http://localhost:8080/",
        "http://x.invalid/",
    ],
)
def test_rejects(url):
    with pytest.raises(UnsafeURLError):
        check_outbound_url(url)


def test_rejects_mixed_public_and_private(fake_dns):
    fake_dns["mixed.example"] = ["93.184.215.14", "10.0.0.5"]
    with pytest.raises(UnsafeURLError, match="private or internal"):
        check_outbound_url("http://mixed.example/")


def test_rejects_private_hostname(fake_dns):
    fake_dns["evil.example"] = ["192.168.0.9"]
    with pytest.raises(UnsafeURLError, match="private or internal"):
        check_outbound_url("https://evil.example/")


def test_unresolvable_message():
    with pytest.raises(UnsafeURLError, match="could not be resolved"):
        check_outbound_url("http://x.invalid/")


@pytest.mark.parametrize(
    "url",
    [
        "http://hook.example/in",
        "https://hook.example:8443/in?x=1",
        "http://93.184.215.14/",
        "http://[2606:4700::1111]/",
        "HTTPS://HOOK.EXAMPLE/Path",
        "https://hook.example./",
    ],
)
def test_accepts(url):
    assert check_outbound_url(url) == url


def test_accept_strips_whitespace():
    assert check_outbound_url("  http://hook.example/in \n") == "http://hook.example/in"


def test_allowlist_allows_private(fake_dns, allow_hosts):
    allow_hosts("host.docker.internal, Other.Example.")
    fake_dns["host.docker.internal"] = ["192.168.65.254"]
    url = "http://host.docker.internal:8765/h"
    assert check_outbound_url(url) == url
    assert pick_connect_ip("host.docker.internal", 8765) is None
    assert pick_connect_ip("OTHER.example", 80) is None
    # Not allow-listed hosts are still blocked.
    with pytest.raises(UnsafeURLError):
        check_outbound_url("http://127.0.0.1/")


def test_allowlist_empty_by_default(fake_dns):
    fake_dns["host.docker.internal"] = ["192.168.65.254"]
    with pytest.raises(UnsafeURLError):
        check_outbound_url("http://host.docker.internal:8765/h")


def test_pick_connect_ip_public(fake_dns):
    assert pick_connect_ip("hook.example", 80) == "93.184.215.14"
    assert pick_connect_ip("93.184.215.14", 80) == "93.184.215.14"
    assert pick_connect_ip("2606:4700::1111", 443) == "2606:4700::1111"
    assert pick_connect_ip("[2606:4700::1111]", 443) == "2606:4700::1111"


def test_pick_connect_ip_first_of_many(fake_dns):
    fake_dns["multi.example"] = ["93.184.215.14", "8.8.8.8"]
    assert pick_connect_ip("multi.example", 80) == "93.184.215.14"


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.1", "::1", "localhost"])
def test_pick_connect_ip_private_raises(host):
    with pytest.raises(UnsafeURLError):
        pick_connect_ip(host, 80)


def test_pick_connect_ip_mixed_raises(fake_dns):
    fake_dns["mixed.example"] = ["93.184.215.14", "127.0.0.1"]
    with pytest.raises(UnsafeURLError):
        pick_connect_ip("mixed.example", 80)


def test_pick_connect_ip_empty_resolution_raises(fake_dns):
    fake_dns["empty.example"] = []
    with pytest.raises(UnsafeURLError):
        pick_connect_ip("empty.example", 80)


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("8.8.8.8", True),
        ("2606:4700::1111", True),
        ("127.0.0.1", False),
        ("100.64.0.1", False),
        ("::ffff:8.8.8.8", True),
        ("::ffff:127.0.0.1", False),
        ("2002:7f00:1::", False),
    ],
)
def test_is_public_ip(ip, expected):
    import ipaddress

    assert url_safety.is_public_ip(ipaddress.ip_address(ip)) is expected


def test_real_resolve_host_dedupes_and_strips_scope(monkeypatch):
    def fake_getaddrinfo(host, port, type=0):
        assert (host, port, type) == ("multi.example", 80, socket.SOCK_STREAM)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 80)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1%eth0", 80, 0, 2)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 80, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert REAL_RESOLVE("multi.example", 80) == ["93.184.215.14", "fe80::1"]


@pytest.mark.parametrize("exc", [socket.gaierror(-2, "nope"), UnicodeError("bad label")])
def test_real_resolve_host_failure(monkeypatch, exc):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(UnsafeURLError, match="could not be resolved"):
        REAL_RESOLVE("nope.example", 80)


@pytest.mark.parametrize("url", ["http://[::1", "http://[not-an-ip]/x"])
def test_malformed_url_rejected(url):
    # Delivery calls check_outbound_url directly (no schema validation in front of it).
    with pytest.raises(UnsafeURLError, match="absolute http"):
        check_outbound_url(url)
