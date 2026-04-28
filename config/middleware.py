from __future__ import annotations

from uuid import uuid4

from config.logging_context import reset_request_id, set_request_id


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

