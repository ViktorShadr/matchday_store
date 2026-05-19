import logging

from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def healthz_view(request):
    """Readiness endpoint для compose/k8s healthchecks."""
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except OperationalError as exc:
        logger.warning(
            "healthz.db_unavailable",
            extra={
                "event": "healthz.db_unavailable",
                "error_type": exc.__class__.__name__,
            },
        )
        return JsonResponse({"status": "error", "db": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
