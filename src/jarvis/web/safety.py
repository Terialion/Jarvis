from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


INTERNAL_HOSTS = {"localhost", "metadata.google.internal", "host.docker.internal"}


def block_reason_for_url(url: str) -> str | None:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return "invalid_url"
    if parsed.scheme.lower() not in {"http", "https"}:
        return "unsupported_scheme"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "missing_host"
    if host in INTERNAL_HOSTS or host.endswith(".internal"):
        return "internal_hostname_blocked"
    if host in {"0.0.0.0", "::1"}:
        return "loopback_blocked"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host == "localhost":
            return "loopback_blocked"
        return None
    if str(ip) == "169.254.169.254":
        return "metadata_service_blocked"
    if ip.is_loopback:
        return "loopback_blocked"
    if ip.is_private:
        return "private_ip_blocked"
    if ip.is_link_local:
        return "link_local_blocked"
    return None


def assert_safe_url(url: str) -> None:
    reason = block_reason_for_url(url)
    if reason is not None:
        raise ValueError(reason)
