from __future__ import annotations

from django.conf import settings


def setting_rate(setting_name: str):
    """Возвращает callable-rate для django-ratelimit из Django settings."""

    def _rate(group, request):
        if not getattr(settings, "RATELIMIT_ENABLE", True):
            return None
        return getattr(settings, setting_name, None)

    return _rate
