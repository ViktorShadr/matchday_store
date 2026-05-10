from contextlib import contextmanager
from contextvars import ContextVar

_payment_signal_sync_suppressed = ContextVar("payment_signal_sync_suppressed", default=False)


def is_payment_signal_sync_suppressed() -> bool:
    return _payment_signal_sync_suppressed.get()


@contextmanager
def suppress_payment_signal_sync():
    token = _payment_signal_sync_suppressed.set(True)
    try:
        yield
    finally:
        _payment_signal_sync_suppressed.reset(token)
