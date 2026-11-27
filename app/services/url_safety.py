"""SSRF protection for user-supplied outbound URLs (webhooks)."""

import ipaddress
import socket

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UnsafeURLError(ValueError):
    """The URL is not allowed as an outbound destination. str(exc) is user-safe."""


def resolve_host(host: str, port: int) -> list[str]:
    """Resolve host to IP strings (deduplicated, getaddrinfo order). Patched in tests.
    Raises UnsafeURLError if the name cannot be resolved."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise UnsafeURLError(f"Host {host!r} could not be resolved") from None
    seen: dict[str, None] = {}
    for *_, sockaddr in infos:
        seen.setdefault(str(sockaddr[0]).split("%", 1)[0], None)
    return list(seen)


def is_public_ip(ip: IPAddress) -> bool:
    """True only for globally routable unicast addresses. IPv4-mapped / 6to4 / Teredo
    IPv6 addresses are judged by their embedded IPv4 address."""
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is not None:
            return is_public_ip(embedded)
    return ip.is_global and not ip.is_multicast


def _normalize_host(host: str) -> str:
    return host.lower().rstrip(".")


def _parse_ip(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        return None


def _require_all_public(host: str, port: int) -> list[str]:
    """Resolve host and require every address to be public; return the addresses."""
    ips = resolve_host(host, port)
    if not ips:
        raise UnsafeURLError(f"Host {host!r} could not be resolved")
    for raw in ips:
        parsed = _parse_ip(raw)
        if parsed is None or not is_public_ip(parsed):
            raise UnsafeURLError("Webhook URL must not point to a private or internal address")
    return ips


def check_outbound_url(url: str) -> str:
    """Validate a user-supplied outbound URL; return it (stripped) if allowed.
    Raises UnsafeURLError with a short user-facing message otherwise."""
    from urllib.parse import urlsplit

    from app.config import get_settings

    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        raise UnsafeURLError("Webhook URL must be an absolute http(s) URL") from None
    scheme = parts.scheme.lower()
    try:
        hostname = parts.hostname
    except ValueError:
        raise UnsafeURLError("Webhook URL must be an absolute http(s) URL") from None
    if scheme not in ("http", "https") or not hostname:
        raise UnsafeURLError("Webhook URL must be an absolute http(s) URL")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURLError("Webhook URL must not contain credentials")
    try:
        port = parts.port
    except ValueError:
        raise UnsafeURLError("Webhook URL has an invalid port") from None
    host = _normalize_host(hostname)
    if host in get_settings().webhook_allowed_hosts:
        return url
    literal = _parse_ip(host)
    if literal is not None:
        if not is_public_ip(literal):
            raise UnsafeURLError("Webhook URL must not point to a private or internal address")
        return url
    _require_all_public(host, port or (443 if scheme == "https" else 80))
    return url


def pick_connect_ip(host: str, port: int) -> str | None:
    """Connection-time check for the pinned transport. Returns the IP to connect to, or
    None if host is allow-listed (connect by name). Raises UnsafeURLError when blocked."""
    from app.config import get_settings

    host = _normalize_host(host)
    if host in get_settings().webhook_allowed_hosts:
        return None
    literal = _parse_ip(host)
    if literal is not None:
        if not is_public_ip(literal):
            raise UnsafeURLError("Webhook URL must not point to a private or internal address")
        return str(literal)
    return _require_all_public(host, port)[0]
