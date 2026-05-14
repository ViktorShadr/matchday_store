from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from support.forms import SupportRequestForm
from support.models import SupportRequest
from support.tasks import send_support_request_notification
from users.models import User


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

    @patch("support.views.send_support_request_notification.delay")
    def test_valid_post_creates_support_request(self, mock_notification_delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data=self.valid_data)

        self.assertRedirects(response, reverse("support:success"))
        support_request = SupportRequest.objects.get()
        self.assertEqual(support_request.email, "ivan@example.com")
        self.assertEqual(support_request.status, SupportRequest.Status.NEW)
        mock_notification_delay.assert_called_once_with(support_request.pk)

    @patch("support.views.send_support_request_notification.delay")
    def test_honeypot_blocks_support_request_creation(self, mock_notification_delay):
        data = {**self.valid_data, "website": "https://spam.example"}

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SupportRequest.objects.exists())
        mock_notification_delay.assert_not_called()

    @patch("support.views.send_support_request_notification.delay")
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
    @patch("support.views.send_support_request_notification.delay")
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


class SupportRequestNotificationTaskTest(TestCase):
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
    @patch("support.tasks.send_mail", side_effect=RuntimeError("SMTP unavailable"))
    def test_notification_task_saves_email_error_on_failure(self, mock_send_mail):
        support_request = SupportRequest.objects.create(
            name="Иван Иванов",
            email="ivan@example.com",
            phone="",
            subject="Вопрос по заказу",
            message="Подскажите статус заказа.",
        )

        result = send_support_request_notification(support_request.pk)

        self.assertFalse(result)
        support_request.refresh_from_db()
        self.assertFalse(support_request.email_sent)
        self.assertIn("SMTP unavailable", support_request.email_error)
        mock_send_mail.assert_called_once()
