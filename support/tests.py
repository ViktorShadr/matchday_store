from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.email_delivery import (
    EMAIL_TASK_MAX_RETRIES,
    EMAIL_TASK_RETRY_BACKOFF_MAX_SECONDS,
    NotificationDeliveryError,
)
from support.forms import SupportRequestForm
from support.models import SupportRequest
from support.tasks import send_support_request_notification
from users.models import User

SUPPORT_NOTIFICATION_DELAY_PATH = (
    "support.application.support_notification_service." "send_support_request_notification.delay"
)
SUPPORT_NOTIFICATION_TASK_PATH = (
    "support.application.support_notification_service." "send_support_request_notification"
)


class SupportRequestFormTest(TestCase):
    def test_form_requires_personal_data_consent(self):
        form = SupportRequestForm(
            data={
                "name": "Иван Иванов",
                "email": "ivan@example.com",
                "phone": "",
                "subject": "Вопрос по заказу",
                "message": "Подскажите статус заказа.",
                "personal_data_consent": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("personal_data_consent", form.errors)


class SupportRequestViewTest(TestCase):
    def setUp(self):
        self.url = reverse("support:request")
        self.valid_data = {
            "name": "Иван Иванов",
            "email": "ivan@example.com",
            "phone": "+79990001122",
            "subject": "Вопрос по заказу",
            "message": "Подскажите статус заказа SH-100.",
            "personal_data_consent": "on",
            "website": "",
        }

    def test_get_support_form_returns_200(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Обращение в поддержку")

    @patch(SUPPORT_NOTIFICATION_DELAY_PATH)
    def test_valid_post_creates_support_request(self, mock_notification_delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data=self.valid_data)

        self.assertRedirects(response, reverse("support:success"))
        support_request = SupportRequest.objects.get()
        self.assertEqual(support_request.email, "ivan@example.com")
        self.assertEqual(support_request.status, SupportRequest.Status.NEW)
        mock_notification_delay.assert_called_once_with(support_request.pk)

    @patch(SUPPORT_NOTIFICATION_DELAY_PATH)
    def test_honeypot_blocks_support_request_creation(self, mock_notification_delay):
        data = {**self.valid_data, "website": "https://spam.example"}

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SupportRequest.objects.exists())
        mock_notification_delay.assert_not_called()

    @patch(SUPPORT_NOTIFICATION_DELAY_PATH)
    def test_authenticated_user_is_attached_to_support_request(self, mock_notification_delay):
        user = User.objects.create_user(
            email="user-support@example.com",
            password="userpass123",
            is_active=True,
            is_email_confirmed=True,
        )
        self.client.login(email="user-support@example.com", password="userpass123")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data=self.valid_data)

        self.assertRedirects(response, reverse("support:success"))
        support_request = SupportRequest.objects.get()
        self.assertEqual(support_request.user, user)
        mock_notification_delay.assert_called_once_with(support_request.pk)

    def test_missing_personal_data_consent_does_not_create_support_request(self):
        data = {**self.valid_data}
        data.pop("personal_data_consent")

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SupportRequest.objects.exists())
        self.assertContains(response, "Подтвердите согласие на обработку персональных данных.")

    @override_settings(RATELIMIT_SUPPORT_POST_RATE="1/m")
    @patch(SUPPORT_NOTIFICATION_DELAY_PATH)
    def test_support_form_rate_limited(self, mock_notification_delay):
        cache.clear()

        with self.captureOnCommitCallbacks(execute=True):
            first_response = self.client.post(self.url, data=self.valid_data)
        second_response = self.client.post(self.url, data={**self.valid_data, "email": "second@example.com"})

        self.assertEqual(first_response.status_code, 302)
        self.assertContains(
            second_response,
            "Слишком много обращений. Попробуйте отправить форму позже.",
            status_code=429,
        )
        self.assertEqual(SupportRequest.objects.count(), 1)
        mock_notification_delay.assert_called_once()

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        SUPPORT_NOTIFICATION_EMAILS=["staff@matchday-store.com"],
        SITE_URL="https://shop.example.com",
    )
    @patch("support.tasks.send_mail")
    @patch(
        SUPPORT_NOTIFICATION_DELAY_PATH,
        side_effect=RuntimeError("broker down"),
    )
    def test_notification_dispatch_failure_does_not_send_sync(self, mock_notification_delay, mock_send_mail):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data=self.valid_data)

        self.assertRedirects(response, reverse("support:success"))
        support_request = SupportRequest.objects.get()
        mock_notification_delay.assert_called_once_with(support_request.pk)
        mock_send_mail.assert_not_called()
        support_request.refresh_from_db()
        self.assertFalse(support_request.email_sent)
        self.assertIn("email-задачу", support_request.email_error)


class SupportRequestNotificationTaskTest(TestCase):
    def test_support_notification_task_has_retry_backoff(self):
        self.assertEqual(send_support_request_notification.autoretry_for, (NotificationDeliveryError,))
        self.assertTrue(send_support_request_notification.retry_backoff)
        self.assertEqual(send_support_request_notification.retry_backoff_max, EMAIL_TASK_RETRY_BACKOFF_MAX_SECONDS)
        self.assertTrue(send_support_request_notification.retry_jitter)
        self.assertEqual(
            send_support_request_notification.retry_kwargs.get("max_retries"),
            EMAIL_TASK_MAX_RETRIES,
        )

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        SUPPORT_NOTIFICATION_EMAILS=["staff@matchday-store.com"],
        SITE_URL="https://shop.example.com",
    )
    @patch("support.tasks.send_mail")
    def test_notification_task_marks_email_sent_on_success(self, mock_send_mail):
        support_request = SupportRequest.objects.create(
            name="Иван Иванов",
            email="ivan@example.com",
            phone="",
            subject="Вопрос по заказу",
            message="Подскажите статус заказа.",
        )

        result = send_support_request_notification(support_request.pk)

        self.assertTrue(result)
        support_request.refresh_from_db()
        self.assertTrue(support_request.email_sent)
        self.assertIsNone(support_request.email_error)
        mock_send_mail.assert_called_once()

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        SUPPORT_NOTIFICATION_EMAILS=["staff@matchday-store.com"],
        SITE_URL="https://shop.example.com",
    )
    @patch("support.tasks._get_current_retry_count", side_effect=[0, 1])
    @patch("support.tasks.send_mail", side_effect=[RuntimeError("SMTP unavailable"), 1])
    def test_notification_task_marks_sent_when_retry_attempt_succeeds(self, mock_send_mail, mock_retry_count):
        support_request = SupportRequest.objects.create(
            name="Иван Иванов",
            email="ivan@example.com",
            phone="",
            subject="Вопрос по заказу",
            message="Подскажите статус заказа.",
        )

        with self.assertRaises(NotificationDeliveryError):
            send_support_request_notification.run(support_request.pk)

        support_request.refresh_from_db()
        self.assertFalse(support_request.email_sent)
        self.assertIsNone(support_request.email_error)

        result = send_support_request_notification.run(support_request.pk)

        self.assertTrue(result)
        support_request.refresh_from_db()
        self.assertTrue(support_request.email_sent)
        self.assertIsNone(support_request.email_error)
        self.assertEqual(mock_send_mail.call_count, 2)
        self.assertEqual(mock_retry_count.call_count, 2)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        SUPPORT_NOTIFICATION_EMAILS=["staff@matchday-store.com"],
        SITE_URL="https://shop.example.com",
    )
    @patch("support.tasks._get_current_retry_count", return_value=0)
    @patch("support.tasks.send_mail", side_effect=RuntimeError("SMTP unavailable"))
    def test_notification_task_retries_without_persisting_error_on_intermediate_failure(
        self,
        mock_send_mail,
        mock_retry_count,
    ):
        support_request = SupportRequest.objects.create(
            name="Иван Иванов",
            email="ivan@example.com",
            phone="",
            subject="Вопрос по заказу",
            message="Подскажите статус заказа.",
        )

        with self.assertRaises(NotificationDeliveryError):
            send_support_request_notification.run(support_request.pk)

        support_request.refresh_from_db()
        self.assertFalse(support_request.email_sent)
        self.assertIsNone(support_request.email_error)
        mock_send_mail.assert_called_once()
        mock_retry_count.assert_called_once()

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@matchday-store.com",
        SUPPORT_NOTIFICATION_EMAILS=["staff@matchday-store.com"],
        SITE_URL="https://shop.example.com",
    )
    @patch("support.tasks._get_current_retry_count", return_value=EMAIL_TASK_MAX_RETRIES)
    @patch("support.tasks.send_mail", side_effect=RuntimeError("SMTP unavailable"))
    def test_notification_task_saves_email_error_after_final_failure(self, mock_send_mail, mock_retry_count):
        support_request = SupportRequest.objects.create(
            name="Иван Иванов",
            email="ivan@example.com",
            phone="",
            subject="Вопрос по заказу",
            message="Подскажите статус заказа.",
        )

        result = send_support_request_notification.run(support_request.pk)

        self.assertFalse(result)
        support_request.refresh_from_db()
        self.assertFalse(support_request.email_sent)
        self.assertIn("SMTP unavailable", support_request.email_error)
        mock_send_mail.assert_called_once()
        mock_retry_count.assert_called_once()


class SupportNotificationServiceQueueDispatchTest(TestCase):
    @patch(SUPPORT_NOTIFICATION_TASK_PATH)
    def test_enqueue_returns_false_when_celery_dispatch_fails(
        self,
        mock_async_task,
    ):
        from support.application import SupportNotificationService

        support_request = SupportRequest.objects.create(
            name="Иван Иванов",
            email="ivan@example.com",
            phone="",
            subject="Вопрос по заказу",
            message="Подскажите статус заказа.",
        )
        mock_async_task.delay.side_effect = RuntimeError("broker down")

        result = SupportNotificationService.enqueue(support_request_id=support_request.pk)

        self.assertFalse(result)
        mock_async_task.delay.assert_called_once_with(support_request.pk)
        support_request.refresh_from_db()
        self.assertFalse(support_request.email_sent)
        self.assertIn("email-задачу", support_request.email_error)
