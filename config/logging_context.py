from __future__ import annotations

from contextvars import ContextVar, Token

REQUEST_ID_FALLBACK = "-"
_request_id: ContextVar[str] = ContextVar("request_id", default=REQUEST_ID_FALLBACK)


def get_request_id() -> str:
    value = _request_id.get()
    if value:
        return value
    return REQUEST_ID_FALLBACK


def set_request_id(value: str | None) -> Token:
    normalized = (value or REQUEST_ID_FALLBACK).strip() or REQUEST_ID_FALLBACK
    return _request_id.set(normalized)


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)

