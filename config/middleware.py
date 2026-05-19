from __future__ import annotations

import logging
from uuid import uuid4

from config.logging_context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)

try:
    import sentry_sdk
except Exception:  # pragma: no cover - sentry optional at runtime
    logger.debug(
        "sentry.sdk_unavailable",
        extra={
            "event": "sentry.sdk_unavailable",
        },
    )
    sentry_sdk = None


class RequestIdMiddleware:
    """Прокидывает request id в контекст логирования и в response header."""

    request_header_name = "HTTP_X_REQUEST_ID"
    response_header_name = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = (request.META.get(self.request_header_name) or "").strip() or uuid4().hex
        request.request_id = request_id

        token = set_request_id(request_id)
        if sentry_sdk is not None:
            sentry_sdk.set_tag("request_id", request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)

        response[self.response_header_name] = request_id
        return response
