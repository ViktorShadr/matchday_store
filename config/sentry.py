from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    value = (os.getenv(name) or "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning(
            "sentry.invalid_float_config",
            extra={
                "event": "sentry.invalid_float_config",
                "setting_name": name,
                "setting_value": value,
                "default_value": default,
            },
        )
        return default


def init_sentry(debug: bool) -> None:
    """Инициализирует Sentry SDK, если задан DSN."""
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
    except Exception:
        logger.exception(
            "sentry.integrations_import_failed",
            extra={
                "event": "sentry.integrations_import_failed",
            },
        )
        return

    environment = (os.getenv("SENTRY_ENVIRONMENT") or "").strip() or ("development" if debug else "production")
    release = (os.getenv("SENTRY_RELEASE") or "").strip() or None

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=_env_float("SENTRY_TRACES_SAMPLE_RATE", 0.0 if debug else 0.1),
        profiles_sample_rate=_env_float("SENTRY_PROFILES_SAMPLE_RATE", 0.0),
        send_default_pii=False,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
        ],
    )
