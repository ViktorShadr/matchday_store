from __future__ import annotations

import logging
from uuid import uuid4

from config.logging_context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)
activity_logger = logging.getLogger("activity")


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
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)

        response[self.response_header_name] = request_id
        return response


class UserActivityMiddleware:
    """Логирует каждый пользовательский HTTP-запрос с user_id и реальным IP."""

    _SKIP_PREFIXES = ("/healthz/", "/metrics", "/static/", "/media/", "/favicon.ico")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if any(request.path.startswith(p) for p in self._SKIP_PREFIXES):
            return response

        user = getattr(request, "user", None)
        user_id = user.id if user and user.is_authenticated else None

        ip = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "")

        activity_logger.info(
            "http.request",
            extra={
                "event": "http.request",
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "user_id": user_id,
                "ip": ip,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:200],
            },
        )

        return response
