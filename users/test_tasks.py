from smtplib import SMTPException
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from config.email_delivery import (
    EMAIL_TASK_MAX_RETRIES,
    EMAIL_TASK_RETRY_BACKOFF_MAX_SECONDS,
    NotificationDeliveryError,
)
from users.application import EmailConfirmationService
from users.tasks import (
    send_confirmation_email,
    send_confirmation_email_sync,
    send_welcome_email,
    send_welcome_email_sync,
)


class UserEmailTaskRetryConfigurationTest(SimpleTestCase):
    def _assert_retry_settings(self, task):
        self.assertEqual(task.autoretry_for, (NotificationDeliveryError,))
        self.assertTrue(task.retry_backoff)
        self.assertEqual(task.retry_backoff_max, EMAIL_TASK_RETRY_BACKOFF_MAX_SECONDS)
        self.assertTrue(task.retry_jitter)
        self.assertEqual(task.retry_kwargs, {"max_retries": EMAIL_TASK_MAX_RETRIES})

    def test_send_confirmation_email_has_retry_backoff(self):
        self._assert_retry_settings(send_confirmation_email)

    def test_send_welcome_email_has_retry_backoff(self):
        self._assert_retry_settings(send_welcome_email)


class UserEmailDeliveryFailureTest(SimpleTestCase):
    @override_settings(DEFAULT_FROM_EMAIL="noreply@matchday-store.com", SITE_URL="https://shop.example.com")
    @patch("users.tasks.send_mail", side_effect=SMTPException("smtp temp failure"))
    def test_confirmation_sync_raises_domain_error_on_smtp_failure(self, mock_send_mail):
        with self.assertRaises(NotificationDeliveryError):
            send_confirmation_email_sync(
                "buyer@example.com",
                "token-123",
                raise_on_error=True,
            )
        mock_send_mail.assert_called_once()

    @override_settings(DEFAULT_FROM_EMAIL="noreply@matchday-store.com")
    @patch("users.tasks.send_mail", side_effect=SMTPException("smtp temp failure"))
    def test_welcome_sync_raises_domain_error_on_smtp_failure(self, mock_send_mail):
        with self.assertRaises(NotificationDeliveryError):
            send_welcome_email_sync("buyer@example.com", raise_on_error=True)
        mock_send_mail.assert_called_once()

    @override_settings(DEFAULT_FROM_EMAIL="noreply@matchday-store.com", SITE_URL="https://shop.example.com")
    @patch("users.tasks.send_mail", side_effect=SMTPException("smtp temp failure"))
    def test_confirmation_task_surface_domain_error_for_celery_autoretry(self, mock_send_mail):
        with self.assertRaises(NotificationDeliveryError):
            send_confirmation_email.run("buyer@example.com", "token-123")
        mock_send_mail.assert_called_once()


class EmailConfirmationFallbackTest(SimpleTestCase):
    @patch("users.application.email_confirmation_service.send_confirmation_email_sync", return_value=True)
    @patch("users.application.email_confirmation_service.send_confirmation_email")
    def test_dispatch_fallback_uses_sync_sender_when_queue_is_unavailable(
        self,
        mock_async_sender,
        mock_sync_sender,
    ):
        mock_async_sender.delay.side_effect = RuntimeError("broker down")

        result = EmailConfirmationService.send_confirmation_email_with_fallback(
            user_email="buyer@example.com",
            confirmation_token="token-123",
        )

        self.assertTrue(result)
        mock_async_sender.delay.assert_called_once_with("buyer@example.com", "token-123")
        mock_sync_sender.assert_called_once_with("buyer@example.com", "token-123")
