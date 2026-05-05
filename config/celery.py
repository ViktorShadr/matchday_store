import os

from celery import Celery, signals

from config.logging_context import get_request_id, reset_request_id, set_request_id

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

REQUEST_ID_HEADER = "x-request-id"
REQUEST_ID_TOKEN_ATTR = "_request_id_log_token"


@signals.before_task_publish.connect
def inject_request_id_before_publish(headers=None, **kwargs):
    if not isinstance(headers, dict):
        return
    if headers.get(REQUEST_ID_HEADER):
        return

    request_id = get_request_id()
    if request_id and request_id != "-":
        headers[REQUEST_ID_HEADER] = request_id


@signals.task_prerun.connect
def set_request_id_for_task(task=None, **kwargs):
    if task is None:
        return

    headers = getattr(task.request, "headers", None) or {}
    request_id = headers.get(REQUEST_ID_HEADER)
    if not request_id:
        return

    token = set_request_id(request_id)
    setattr(task.request, REQUEST_ID_TOKEN_ATTR, token)


@signals.task_postrun.connect
def clear_request_id_after_task(task=None, **kwargs):
    if task is None:
        return

    token = getattr(task.request, REQUEST_ID_TOKEN_ATTR, None)
    if token is None:
        return

    reset_request_id(token)
    setattr(task.request, REQUEST_ID_TOKEN_ATTR, None)
