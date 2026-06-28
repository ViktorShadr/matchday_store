import io
import json
import logging
from smtplib import SMTPDataError, SMTPRecipientsRefused
from types import SimpleNamespace

from django.test import SimpleTestCase

from config.celery import (
    REQUEST_ID_HEADER,
    clear_request_id_after_task,
    inject_request_id_before_publish,
    set_request_id_for_task,
)
from config.email_delivery import is_permanent_email_delivery_error
from config.logging_context import get_request_id, reset_request_id, set_request_id
from config.logging_utils import JsonFormatter, RequestIdFilter, SensitiveDataFilter


class EmailDeliveryErrorClassificationTest(SimpleTestCase):
    def test_recipient_4xx_is_retryable(self):
        recipient = "buyer@example.com"
        exc = SMTPRecipientsRefused({recipient: (450, b"4.2.0 Greylisted")})

        self.assertFalse(is_permanent_email_delivery_error(exc))

    def test_recipient_5xx_is_permanent(self):
        recipient = "buyer@example.com"
        response = b"5.1.1 Mailbox unavailable"
        exc = SMTPRecipientsRefused({recipient: (550, response)})

        self.assertTrue(is_permanent_email_delivery_error(exc))

    def test_mixed_recipient_codes_are_retryable(self):
        exc = SMTPRecipientsRefused(
            {
                "buyer@example.com": (451, b"4.7.1 Try again later"),
                "bad@example.com": (550, b"5.1.1 Mailbox unavailable"),
            }
        )

        self.assertFalse(is_permanent_email_delivery_error(exc))

    def test_smtp_response_5xx_is_permanent(self):
        exc = SMTPDataError(553, b"5.1.10 No valid recipients")

        self.assertTrue(is_permanent_email_delivery_error(exc))

    def test_smtp_response_4xx_is_retryable(self):
        exc = SMTPDataError(451, b"4.7.1 Try again later")

        self.assertFalse(is_permanent_email_delivery_error(exc))


class LoggingPipelineTest(SimpleTestCase):
    @staticmethod
    def _build_json_logger(name: str) -> tuple[logging.Logger, io.StringIO]:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(RequestIdFilter())
        handler.addFilter(SensitiveDataFilter())
        handler.setFormatter(JsonFormatter())

        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        return logger, stream

    def test_json_log_contains_request_id_and_extra(self):
        token = set_request_id("req-123")
        self.addCleanup(reset_request_id, token)
        logger, stream = self._build_json_logger("config.tests.request_id")

        logger.info("order.created", extra={"event": "order.created", "order_id": 42, "user_id": 7})
        payload = json.loads(stream.getvalue().strip())

        self.assertEqual(payload["message"], "order.created")
        self.assertEqual(payload["request_id"], "req-123")
        self.assertEqual(payload["event"], "order.created")
        self.assertEqual(payload["order_id"], 42)
        self.assertEqual(payload["user_id"], 7)

    def test_json_log_uses_request_id_fallback(self):
        token = set_request_id(None)
        self.addCleanup(reset_request_id, token)
        logger, stream = self._build_json_logger("config.tests.request_id_fallback")

        logger.info("healthz.ping")
        payload = json.loads(stream.getvalue().strip())

        self.assertEqual(payload["request_id"], "-")

    def test_sensitive_data_is_masked_in_message_and_extra(self):
        token = set_request_id("req-mask")
        self.addCleanup(reset_request_id, token)
        logger, stream = self._build_json_logger("config.tests.sensitive_data")

        logger.error(
            "auth.failed password=secret token=abc Authorization=Bearer token123 "
            "cookie=sessionid123 email=buyer@example.com phone=+79990001122",
            extra={
                "event": "auth.failed",
                "password": "secret",
                "token": "abc",
                "authorization": "Bearer token123",
                "cookie": "sessionid123",
                "email": "buyer@example.com",
                "phone": "+79990001122",
            },
        )
        payload = json.loads(stream.getvalue().strip())
        message = payload["message"]

        self.assertNotIn("secret", message)
        self.assertNotIn("token123", message)
        self.assertNotIn("buyer@example.com", message)
        self.assertNotIn("+79990001122", message)
        self.assertEqual(payload["password"], "***")
        self.assertEqual(payload["token"], "***")
        self.assertEqual(payload["authorization"], "***")
        self.assertEqual(payload["cookie"], "***")
        self.assertEqual(payload["email"], "***")
        self.assertEqual(payload["phone"], "***")

    def test_email_delivery_metadata_keys_are_not_masked(self):
        token = set_request_id("req-email-metadata")
        self.addCleanup(reset_request_id, token)
        logger, stream = self._build_json_logger("config.tests.email_metadata")

        logger.info(
            "email.delivery",
            extra={
                "event": "email.delivery",
                "email_type": "confirmation",
                "email_timeout": 30,
            },
        )
        payload = json.loads(stream.getvalue().strip())

        self.assertEqual(payload["email_type"], "confirmation")
        self.assertEqual(payload["email_timeout"], 30)

    def test_contact_keys_with_suffix_stay_masked(self):
        token = set_request_id("req-contact-key")
        self.addCleanup(reset_request_id, token)
        logger, stream = self._build_json_logger("config.tests.contact_key")

        logger.info(
            "profile.updated",
            extra={
                "event": "profile.updated",
                "user_email": "buyer@example.com",
                "customer_phone": "+79990001122",
            },
        )
        payload = json.loads(stream.getvalue().strip())

        self.assertEqual(payload["user_email"], "***")
        self.assertEqual(payload["customer_phone"], "***")

    def test_json_log_contains_exception_trace(self):
        token = set_request_id("req-exception")
        self.addCleanup(reset_request_id, token)
        logger, stream = self._build_json_logger("config.tests.exception_json")

        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("checkout.failed", extra={"event": "checkout.failed"})

        payload = json.loads(stream.getvalue().strip())
        self.assertIn("exception", payload)
        self.assertIn("RuntimeError: boom", payload["exception"])

    def test_ipv4_address_is_not_masked(self):
        token = set_request_id("req-ip")
        self.addCleanup(reset_request_id, token)
        logger, stream = self._build_json_logger("config.tests.ip_not_masked")

        logger.info("http.request", extra={"event": "http.request", "ip": "192.168.1.100"})
        payload = json.loads(stream.getvalue().strip())

        self.assertEqual(payload["extra"]["ip"], "192.168.1.100")


class CeleryRequestIdPropagationTest(SimpleTestCase):
    def test_publish_signal_injects_request_id_into_headers(self):
        token = set_request_id("req-celery-publish")
        self.addCleanup(reset_request_id, token)
        headers: dict[str, str] = {}

        inject_request_id_before_publish(headers=headers)

        self.assertEqual(headers.get(REQUEST_ID_HEADER), "req-celery-publish")

    def test_task_prerun_and_postrun_propagate_and_clear_request_id(self):
        baseline_token = set_request_id(None)
        self.addCleanup(reset_request_id, baseline_token)
        task = SimpleNamespace(request=SimpleNamespace(headers={REQUEST_ID_HEADER: "req-celery-task"}))

        set_request_id_for_task(task=task)
        self.assertEqual(get_request_id(), "req-celery-task")

        clear_request_id_after_task(task=task)
        self.assertEqual(get_request_id(), "-")

    def test_publish_signal_does_not_inject_fallback_request_id(self):
        token = set_request_id(None)
        self.addCleanup(reset_request_id, token)
        headers: dict[str, str] = {}

        inject_request_id_before_publish(headers=headers)

        self.assertNotIn(REQUEST_ID_HEADER, headers)
