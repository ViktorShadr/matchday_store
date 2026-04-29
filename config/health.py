from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse


def healthz_view(request):
    """Readiness endpoint для compose/k8s healthchecks."""
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except OperationalError:
        return JsonResponse({"status": "error", "db": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
