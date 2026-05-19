from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from config.logging_context import get_request_id

STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}

SENSITIVE_KEY_RE = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie)",
    re.IGNORECASE,
)
SENSITIVE_CONTACT_KEY_RE = re.compile(
    r"(?:^|[_-])(email|phone)(?:$|[_-](address|number))",
    re.IGNORECASE,
)
SENSITIVE_PAIR_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|cookie|email|phone)\b(\s*[:=]\s*)([^\s,;]+)"
)
BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{7,}\d)(?!\w)")


def _mask_email_local_part(match: re.Match) -> str:
    first = match.group(1)
    domain = match.group(3)
    return f"{first}***@{domain}"


def _mask_phone_number(match: re.Match) -> str:
    value = match.group(1)
    digits = [ch for ch in value if ch.isdigit()]
    if len(digits) < 8:
        return value
    visible_tail = "".join(digits[-4:])
    return f"***{visible_tail}"


def _sanitize_string(value: str) -> str:
    sanitized = BEARER_TOKEN_RE.sub("Bearer ***", value)
    sanitized = SENSITIVE_PAIR_RE.sub(r"\1\2***", sanitized)
    sanitized = EMAIL_RE.sub(_mask_email_local_part, sanitized)
    sanitized = PHONE_RE.sub(_mask_phone_number, sanitized)
    return sanitized


def _sanitize_value(value: Any, key: str | None = None) -> Any:
    if key and (SENSITIVE_KEY_RE.search(key) or SENSITIVE_CONTACT_KEY_RE.search(key)):
        return "***"

    if isinstance(value, dict):
        return {k: _sanitize_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item, key=key) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item, key=key) for item in value)
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


class RequestIdFilter(logging.Filter):
    """Добавляет request_id в каждую запись лога."""

    def filter(self, record: logging.LogRecord) -> bool:
        request = getattr(record, "request", None)
        request_id = getattr(request, "request_id", None)
        normalized_request_id = (str(request_id).strip() if request_id is not None else "") or get_request_id()
        record.request_id = normalized_request_id or "-"
        return True


class SensitiveDataFilter(logging.Filter):
    """Редактирует потенциально чувствительные данные в сообщении и extra-полях."""

    def filter(self, record: logging.LogRecord) -> bool:
        sanitized_message = _sanitize_string(record.getMessage())
        record.msg = sanitized_message
        record.args = ()

        for key, value in list(record.__dict__.items()):
            if key in STANDARD_RECORD_FIELDS:
                continue
            if key == "request_id":
                continue
            record.__dict__[key] = _sanitize_value(value, key=key)
        return True


class JsonFormatter(logging.Formatter):
    """JSON formatter для production-логов."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = str(getattr(record, "request_id", "")).strip() or get_request_id() or "-"
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id,
            "module": record.module,
            "func_name": record.funcName,
            "line_no": record.lineno,
            "process": record.processName,
        }

        extra = {}
        for key, value in record.__dict__.items():
            if key in STANDARD_RECORD_FIELDS or key in payload:
                continue
            extra[key] = value

        if extra:
            payload["extra"] = extra

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def build_logging_config(*, debug: bool, log_level: str, json_logs: bool) -> dict[str, Any]:
    formatter_name = "json" if json_logs else "human"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": "config.logging_utils.RequestIdFilter"},
            "sanitize": {"()": "config.logging_utils.SensitiveDataFilter"},
        },
        "formatters": {
            "human": {
                "format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": "config.logging_utils.JsonFormatter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "filters": ["request_id", "sanitize"],
                "formatter": formatter_name,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": "INFO" if debug else log_level,
                "propagate": False,
            },
            "django.server": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "celery": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "audit": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
