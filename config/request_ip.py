from __future__ import annotations

from ipaddress import ip_address

from django.conf import settings


def get_safe_request_ip(request) -> str | None:
    """
    Return the client IP from a trusted request meta key.

    Reverse proxy headers are used only when RATELIMIT_IP_META_KEY is configured;
    otherwise REMOTE_ADDR is the safe default.
    """
    meta_key = getattr(settings, "RATELIMIT_IP_META_KEY", None) or "REMOTE_ADDR"
    raw_value = (request.META.get(meta_key) or "").split(",", 1)[0].strip()
    if not raw_value:
        return None

    try:
        return str(ip_address(raw_value))
    except ValueError:
        return None
