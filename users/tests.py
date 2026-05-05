from datetime import timedelta
from unittest.mock import ANY, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, OrderItem
from store.models import Cart, CartItem, Category, Product, ProductImage, ProductVariant
from users.application import EmailConfirmationService
from users.forms import AVATAR_MAX_SIZE_BYTES, ProfileDeleteConfirmForm, UserProfileForm, UserRegistrationForm

User = get_user_model()


class UserModelTest(TestCase):
    """Тесты для UserModelTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.user_data = {
            "email": "test@example.com",
            "password": "testpass123",
            "first_name": "Test",
            "last_name": "User",
        }

    def test_create_user_with_email(self):
        """Проверяет сценарий 'create user with email'."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "Test")
        self.assertEqual(user.last_name, "User")
        self.assertTrue(user.check_password("testpass123"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_without_email_fails(self):
        """Проверяет сценарий 'create user without email fails'."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email=None, password="testpass123")

    def test_create_superuser(self):
        """Проверяет сценарий 'create superuser'."""
        admin_user = User.objects.create_superuser(email="admin@example.com", password="adminpass123")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertEqual(admin_user.email, "admin@example.com")

    def test_user_str_method(self):
        """Проверяет сценарий 'user str method'."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(str(user), "test@example.com")

    def test_generate_email_token_sets_created_at(self):
        user = User.objects.create_user(**self.user_data)

        token = user.generate_email_token()
        user.refresh_from_db()

        self.assertEqual(user.email_token, token)
        self.assertIsNotNone(user.email_token_created_at)

    def test_missing_token_timestamp_is_not_expired_during_rollout(self):
        user = User.objects.create_user(**self.user_data)
        user.email_token = "legacy-token"
        user.email_token_created_at = None
        user.save(update_fields=["email_token", "email_token_created_at"])

        self.assertFalse(EmailConfirmationService.is_token_expired(user))

    def test_email_normalization(self):
        """Проверяет сценарий 'email normalization'."""
        user = User.objects.create_user(email="Test@EXAMPLE.COM", password="testpass123")
        self.assertEqual(user.email, "Test@example.com")


class UserRegistrationFormTest(TestCase):
    """Тесты для UserRegistrationFormTest."""

    def test_valid_registration_form(self):
        """Проверяет сценарий 'valid registration form'."""
        form_data = {"email": "newuser@example.com", "password1": "complexpass123", "password2": "complexpass123"}
        form = UserRegistrationForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_duplicate_email_validation(self):
        """Проверяет сценарий 'duplicate email validation'."""
        User.objects.create_user(email="existing@example.com", password="pass123")
        form_data = {"email": "existing@example.com", "password1": "complexpass123", "password2": "complexpass123"}
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        self.assertIn("Пользователь с таким email уже зарегистрирован", form.errors["email"])

    def test_password_mismatch(self):
        """Проверяет сценарий 'password mismatch'."""
        form_data = {"email": "test@example.com", "password1": "pass123", "password2": "different123"}
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())


class UserProfileFormTest(TestCase):
    """Тесты для UserProfileFormTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.user = User.objects.create_user(email="test@example.com", password="testpass123")

    def test_valid_profile_form(self):
        """Проверяет сценарий 'valid profile form'."""
        form_data = {"first_name": "John", "last_name": "Doe", "city": "New York", "phone": "+79109716684"}
        form = UserProfileForm(data=form_data, instance=self.user)
        self.assertTrue(form.is_valid())

    def test_profile_form_normalizes_russian_phone(self):
        form_data = {"first_name": "John", "last_name": "Doe", "city": "New York", "phone": "8 (910) 971-66-84"}
        form = UserProfileForm(data=form_data, instance=self.user)

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["phone"], "+79109716684")

    def test_profile_form_rejects_non_russian_phone(self):
        form_data = {"first_name": "John", "last_name": "Doe", "city": "New York", "phone": "+1234567890"}
        form = UserProfileForm(data=form_data, instance=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_profile_form_rejects_oversized_avatar(self):
        upload = SimpleUploadedFile(
            "avatar.jpg",
            b"x" * (AVATAR_MAX_SIZE_BYTES + 1),
            content_type="image/jpeg",
        )
        form = UserProfileForm(data={}, files={"avatar": upload}, instance=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("avatar", form.errors)
        self.assertIn("Размер аватара не должен превышать 2 МБ", form.errors["avatar"][0])

    def test_profile_form_rejects_archive_avatar(self):
        upload = SimpleUploadedFile("avatar.zip", b"PK\x03\x04archive", content_type="application/zip")
        form = UserProfileForm(data={}, files={"avatar": upload}, instance=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("avatar", form.errors)
        self.assertIn("JPG, PNG или WebP", form.errors["avatar"][0])

    def test_form_save(self):
        """Проверяет сценарий 'form save'."""
        form_data = {"first_name": "Jane", "last_name": "Smith"}
        form = UserProfileForm(data=form_data, instance=self.user)
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Smith")


class ProfileDeleteConfirmFormTest(TestCase):
    """Тесты для ProfileDeleteConfirmFormTest."""

    def test_empty_password(self):
        """Проверяет сценарий 'empty password'."""
        form = ProfileDeleteConfirmForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_valid_password(self):
        """Проверяет сценарий 'valid password'."""
        form = ProfileDeleteConfirmForm(data={"password": "somepassword"})
        self.assertTrue(form.is_valid())


class UserViewsTest(TestCase):
    """Тесты для UserViewsTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.client = Client()
        self.user = User.objects.create_user(email="user@example.com", password="userpass123", is_active=True)
        self.staff_user = User.objects.create_user(
            email="staff@example.com",
            password="staffpass123",
            is_staff=True,
            is_active=True,
        )
        self.superuser = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123",
        )
        self.category = Category.objects.create(name="Атрибутика")
        self.product = Product.objects.create(name="Шарф", category=self.category)
        self.image = ProductImage.objects.create(product=self.product, image="product_images/test.jpg")
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size="One Size",
            color="Синий",
            price="1500.00",
            quantity=10,
            image=self.image,
        )

    @patch("users.views.send_welcome_email")
    @patch("users.views.send_confirmation_email")
    def test_registration_view_success(self, mock_confirmation_email, mock_welcome_email):
        """Проверяет сценарий 'registration view success'."""
        form_data = {"email": "newuser@example.com", "password1": "complexpass123", "password2": "complexpass123"}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("users:registration"), data=form_data)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("users:login"))

        new_user = User.objects.get(email="newuser@example.com")
        self.assertTrue(new_user.is_active)
        self.assertIsNotNone(new_user.email_token)
        self.assertIsNotNone(new_user.email_token_created_at)
        mock_confirmation_email.delay.assert_called_once_with("newuser@example.com", ANY)
        mock_welcome_email.delay.assert_not_called()

    def test_registration_view_uses_sync_fallback_when_celery_unavailable(self):
        form_data = {"email": "fallback@example.com", "password1": "complexpass123", "password2": "complexpass123"}

        with patch("users.views.send_confirmation_email") as mock_confirmation_email:
            with patch("users.views.send_confirmation_email_sync", return_value=True) as mock_confirmation_email_sync:
                mock_confirmation_email.delay.side_effect = RuntimeError("broker down")
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(reverse("users:registration"), data=form_data)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("users:login"))
        new_user = User.objects.get(email="fallback@example.com")
        self.assertTrue(new_user.is_active)
        self.assertIsNotNone(new_user.email_token)
        self.assertIsNotNone(new_user.email_token_created_at)
        self.assertIsNotNone(new_user.confirmation_email_last_sent_at)
        mock_confirmation_email.delay.assert_called_once_with("fallback@example.com", ANY)
        mock_confirmation_email_sync.assert_called_once_with("fallback@example.com", ANY)

    @patch("users.views.send_confirmation_email")
    def test_resend_confirmation_email_success_from_profile(self, mock_confirmation_email):
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.post(reverse("users:resend_confirmation"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("users:profile_detail", kwargs={"pk": self.user.pk}))
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.confirmation_email_last_sent_at)
        self.assertIsNotNone(self.user.email_token)
        self.assertIsNotNone(self.user.email_token_created_at)
        mock_confirmation_email.delay.assert_called_once_with("user@example.com", ANY)

    @patch("users.views.send_confirmation_email")
    def test_resend_confirmation_email_throttled_from_profile(self, mock_confirmation_email):
        self.user.confirmation_email_last_sent_at = timezone.now()
        self.user.save(update_fields=["confirmation_email_last_sent_at"])
        self.client.login(email="user@example.com", password="userpass123")

        response = self.client.post(reverse("users:resend_confirmation"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Повторная отправка будет доступна")
        mock_confirmation_email.delay.assert_not_called()

    @patch("users.views.send_confirmation_email")
    def test_resend_confirmation_email_not_sent_for_confirmed_user(self, mock_confirmation_email):
        self.user.is_email_confirmed = True
        self.user.save(update_fields=["is_email_confirmed"])
        self.client.login(email="user@example.com", password="userpass123")

        response = self.client.post(reverse("users:resend_confirmation"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email уже подтвержден")
        mock_confirmation_email.delay.assert_not_called()

    def test_resend_confirmation_email_failure_keeps_existing_token(self):
        old_token = self.user.generate_email_token()
        self.client.login(email="user@example.com", password="userpass123")

        with patch("users.views.send_confirmation_email") as mock_confirmation_email:
            with patch("users.views.send_confirmation_email_sync", return_value=False) as mock_confirmation_email_sync:
                mock_confirmation_email.delay.side_effect = RuntimeError("broker down")
                response = self.client.post(reverse("users:resend_confirmation"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Не удалось отправить письмо подтверждения. Попробуйте позже.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email_token, old_token)
        self.assertIsNotNone(self.user.email_token_created_at)
        self.assertIsNone(self.user.confirmation_email_last_sent_at)
        mock_confirmation_email.delay.assert_called_once()
        mock_confirmation_email_sync.assert_called_once()

    def test_registration_view_failure(self):
        """Проверяет сценарий 'registration view failure'."""
        form_data = {"email": "user@example.com", "password1": "pass123", "password2": "different"}  # Already exists
        response = self.client.post(reverse("users:registration"), data=form_data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="user@example.com").count() > 1)

    def test_login_view_success(self):
        """Проверяет сценарий 'login view success'."""
        response = self.client.post(
            reverse("users:login"), {"username": "user@example.com", "password": "userpass123"}
        )
        self.assertEqual(response.status_code, 302)

    def test_login_view_failure(self):
        """Проверяет сценарий 'login view failure'."""
        response = self.client.post(
            reverse("users:login"), {"username": "user@example.com", "password": "wrongpassword"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    @override_settings(
        RATELIMIT_LOGIN_IP_RATE="1/m",
        RATELIMIT_LOGIN_CREDENTIAL_RATE="1/m",
    )
    def test_login_view_rate_limited(self):
        cache.clear()
        login_url = reverse("users:login")
        payload = {"username": "user@example.com", "password": "wrongpassword"}

        first_response = self.client.post(login_url, payload)
        second_response = self.client.post(login_url, payload)

        self.assertEqual(first_response.status_code, 200)
        self.assertContains(
            second_response,
            "Слишком много попыток входа. Подождите и попробуйте снова.",
            status_code=429,
        )

    def test_login_view_hides_resend_confirmation_link_by_default(self):
        response = self.client.get(reverse("users:login"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("users:resend_confirmation"))

    def test_healthz_endpoint(self):
        response = self.client.get("/healthz/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

    @override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["testserver"],
        SECURE_SSL_REDIRECT=True,
    )
    def test_healthz_endpoint_is_not_redirected_when_ssl_redirect_enabled(self):
        response = self.client.get("/healthz/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

    @patch("users.views.send_welcome_email")
    def test_confirm_email_logs_user_in_and_redirects_to_profile(self, mock_welcome_email):
        confirm_user = User.objects.create_user(
            email="confirm-flow@example.com",
            password="confirmpass123",
            is_active=True,
            is_email_confirmed=False,
        )
        token = confirm_user.generate_email_token()

        response = self.client.get(reverse("users:confirm_email", kwargs={"token": token}))

        confirm_user.refresh_from_db()
        self.assertRedirects(response, reverse("users:profile_detail", kwargs={"pk": confirm_user.pk}))
        self.assertTrue(confirm_user.is_email_confirmed)
        self.assertTrue(confirm_user.is_active)
        self.assertIsNone(confirm_user.email_token_created_at)
        self.assertEqual(int(self.client.session["_auth_user_id"]), confirm_user.pk)
        mock_welcome_email.delay.assert_called_once_with("confirm-flow@example.com")

    @patch("users.views.send_welcome_email")
    def test_confirm_email_with_legacy_token_without_timestamp_succeeds(self, mock_welcome_email):
        confirm_user = User.objects.create_user(
            email="legacy-token@example.com",
            password="confirmpass123",
            is_active=True,
            is_email_confirmed=False,
        )
        token = confirm_user.generate_email_token()
        confirm_user.email_token_created_at = None
        confirm_user.save(update_fields=["email_token_created_at"])

        response = self.client.get(reverse("users:confirm_email", kwargs={"token": token}))

        confirm_user.refresh_from_db()
        self.assertRedirects(response, reverse("users:profile_detail", kwargs={"pk": confirm_user.pk}))
        self.assertTrue(confirm_user.is_email_confirmed)
        self.assertTrue(confirm_user.is_active)
        self.assertIsNone(confirm_user.email_token)
        self.assertIsNone(confirm_user.email_token_created_at)
        mock_welcome_email.delay.assert_called_once_with("legacy-token@example.com")

    @override_settings(
        RATELIMIT_REGISTRATION_IP_RATE="1/m",
        RATELIMIT_REGISTRATION_EMAIL_RATE="1/m",
    )
    @patch("users.views.send_confirmation_email")
    def test_registration_view_rate_limited(self, mock_confirmation_email):
        cache.clear()
        form_data = {
            "email": "new-rate-limit@example.com",
            "password1": "complexpass123",
            "password2": "complexpass123",
        }

        with self.captureOnCommitCallbacks(execute=True):
            first_response = self.client.post(reverse("users:registration"), data=form_data)
        second_response = self.client.post(reverse("users:registration"), data=form_data)

        self.assertEqual(first_response.status_code, 302)
        self.assertContains(
            second_response,
            "Слишком много попыток регистрации. Попробуйте позже.",
            status_code=429,
        )
        mock_confirmation_email.delay.assert_called_once()

    @override_settings(
        RATELIMIT_CONFIRM_RESEND_IP_RATE="1/m",
        RATELIMIT_CONFIRM_RESEND_USER_RATE="1/m",
    )
    @patch("users.views.send_confirmation_email")
    def test_resend_confirmation_email_rate_limited(self, mock_confirmation_email):
        cache.clear()
        self.client.login(email="user@example.com", password="userpass123")

        first_response = self.client.post(reverse("users:resend_confirmation"))
        second_response = self.client.post(reverse("users:resend_confirmation"), follow=True)

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "Слишком много запросов на повторную отправку. Попробуйте позже.")

    @override_settings(EMAIL_CONFIRMATION_TOKEN_TTL_HOURS=1)
    @patch("users.views.send_welcome_email")
    def test_confirm_email_with_expired_token_fails(self, mock_welcome_email):
        confirm_user = User.objects.create_user(
            email="expired-token@example.com",
            password="confirmpass123",
            is_active=True,
            is_email_confirmed=False,
        )
        token = confirm_user.generate_email_token()
        confirm_user.email_token_created_at = timezone.now() - timedelta(hours=2)
        confirm_user.save(update_fields=["email_token_created_at"])

        response = self.client.get(reverse("users:confirm_email", kwargs={"token": token}))

        confirm_user.refresh_from_db()
        self.assertRedirects(response, reverse("users:login"))
        self.assertFalse(confirm_user.is_email_confirmed)
        self.assertIsNone(confirm_user.email_token)
        self.assertIsNone(confirm_user.email_token_created_at)
        mock_welcome_email.delay.assert_not_called()

    def test_logout_view(self):
        """Проверяет сценарий 'logout view'."""
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.post(reverse("users:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("store:base"))

    def test_profile_detail_view_own_profile(self):
        """Проверяет сценарий 'profile detail view own profile'."""
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": self.user.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "user@example.com")

    def test_profile_detail_view_uses_actual_cart_counter(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product_variant=self.variant, quantity=3)

        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": self.user.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertIn("cart_count", response.context)
        self.assertEqual(response.context["cart_count"], 3)

    def test_profile_detail_shows_email_confirmation_prompt_for_unconfirmed_user(self):
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": self.user.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Подтвердите email для оформления заказов")
        self.assertContains(response, reverse("users:resend_confirmation"))

    def test_profile_detail_hides_email_confirmation_prompt_for_confirmed_user(self):
        self.user.is_email_confirmed = True
        self.user.save(update_fields=["is_email_confirmed"])
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": self.user.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Подтвердите email для оформления заказов")

    def test_profile_detail_view_other_profile_denied(self):
        """Проверяет сценарий 'profile detail view other profile denied'."""
        other_user = User.objects.create_user(email="other@example.com", password="otherpass123")
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": other_user.pk}))

        self.assertEqual(response.status_code, 403)

    def test_profile_detail_view_staff_cannot_see_other_profile(self):
        """Обычный staff не должен видеть чужой профиль."""
        other_user = User.objects.create_user(email="other@example.com", password="otherpass123")
        self.client.login(email="staff@example.com", password="staffpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": other_user.pk}))

        self.assertEqual(response.status_code, 403)

    def test_profile_detail_view_superuser_can_see_other_profile(self):
        """Суперпользователь может просматривать чужие профили."""
        other_user = User.objects.create_user(email="other2@example.com", password="otherpass123")
        self.client.login(email="admin@example.com", password="adminpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": other_user.pk}))

        self.assertEqual(response.status_code, 200)

    def test_profile_detail_view_not_authenticated(self):
        """Проверяет сценарий 'profile detail view not authenticated'."""
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": self.user.pk}))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_update_view(self):
        """Проверяет сценарий 'profile update view'."""
        self.client.login(email="user@example.com", password="userpass123")
        form_data = {"first_name": "Updated", "last_name": "Name", "city": "New City", "phone": "8 (910) 971-66-84"}
        response = self.client.post(reverse("users:profile_edit"), data=form_data)

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Name")
        self.assertEqual(self.user.phone, "+79109716684")

    def test_profile_update_view_rejects_archive_avatar(self):
        self.client.login(email="user@example.com", password="userpass123")
        upload = SimpleUploadedFile("avatar.zip", b"PK\x03\x04archive", content_type="application/zip")
        response = self.client.post(
            reverse("users:profile_edit"),
            data={"first_name": "Updated", "avatar": upload},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "JPG, PNG или WebP")
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_profile_update_view_not_authenticated(self):
        """Проверяет сценарий 'profile update view not authenticated'."""
        response = self.client.get(reverse("users:profile_edit"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_delete_view_success(self):
        """Проверяет сценарий 'profile delete view success'."""
        self.client.login(email="user@example.com", password="userpass123")
        form_data = {"password": "userpass123"}
        response = self.client.post(reverse("users:profile_delete"), data=form_data)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("store:base"))
        self.assertFalse(User.objects.filter(email="user@example.com").exists())

    def test_profile_delete_view_blocks_user_with_orders(self):
        """Профиль с оформленными заказами удалять нельзя."""
        Order.objects.create(
            number="ORD-DELETE-BLOCK",
            user=self.user,
            recipient_name="Покупатель",
            email=self.user.email,
            phone="+79990001122",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            total_amount="1000.00",
        )
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.post(reverse("users:profile_delete"), data={"password": "userpass123"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email="user@example.com").exists())
        self.assertContains(response, "Нельзя удалить профиль")

    def test_user_delete_is_protected_when_orders_exist(self):
        """На уровне БД удаление пользователя с заказами должно быть запрещено."""
        Order.objects.create(
            number="ORD-PROTECT-1",
            user=self.user,
            recipient_name="Покупатель",
            email=self.user.email,
            phone="+79990001122",
            status=Order.Status.PLACED,
            delivery_method=Order.DeliveryMethod.PICKUP,
            total_amount="1000.00",
        )

        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_profile_delete_view_wrong_password(self):
        """Проверяет сценарий 'profile delete view wrong password'."""
        self.client.login(email="user@example.com", password="userpass123")
        form_data = {"password": "wrongpassword"}
        response = self.client.post(reverse("users:profile_delete"), data=form_data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email="user@example.com").exists())
        self.assertContains(response, "Неверный пароль")

    def test_profile_delete_view_not_authenticated(self):
        """Проверяет сценарий 'profile delete view not authenticated'."""
        response = self.client.get(reverse("users:profile_delete"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_user_order_list_requires_authentication(self):
        """Список заказов должен требовать авторизацию."""
        response = self.client.get(reverse("users:order_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("users:login"), response.url)

    def test_user_order_list_shows_current_user_orders(self):
        """Список заказов должен показывать данные только текущего пользователя."""
        other_user = User.objects.create_user(email="other@example.com", password="otherpass123")
        order = Order.objects.create(
            number="ORD-USER-1",
            user=self.user,
            recipient_name="Покупатель",
            email=self.user.email,
            phone="+79990000000",
            status=Order.Status.PLACED,
            total_amount="3000.00",
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot="Шарф",
            unit_price="1500.00",
            quantity=2,
            line_total="3000.00",
        )
        Order.objects.create(
            number="ORD-OTHER-1",
            user=other_user,
            recipient_name="Другой покупатель",
            email=other_user.email,
            phone="+79991111111",
            status=Order.Status.CANCELLED,
            total_amount="1000.00",
        )

        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:order_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ORD-USER-1")
        self.assertContains(response, "2")
        self.assertContains(response, "3000,00")
        self.assertContains(response, "Новый")
        self.assertContains(response, "Отменить заказ")
        self.assertNotContains(response, "ORD-OTHER-1")

    def test_user_order_list_reflects_current_workflow_status(self):
        """Список заказов должен показывать статус исполнения, а не только общий status."""
        Order.objects.create(
            number="ORD-READY-1",
            user=self.user,
            recipient_name="Покупатель",
            email=self.user.email,
            phone="+79990000000",
            status=Order.Status.PROCESSING,
            fulfillment_status=Order.FulfillmentStatus.RESERVED,
            total_amount="1500.00",
        )

        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:order_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Готов к выдаче")
        self.assertNotContains(response, "В обработке")

    def test_user_order_detail_shows_pickup_payment_and_cancel_action(self):
        order = Order.objects.create(
            number="ORD-DETAIL-1",
            user=self.user,
            recipient_name="Покупатель",
            email=self.user.email,
            phone="+79990000000",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            total_amount="1500.00",
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot="Шарф",
            unit_price="1500.00",
            quantity=1,
            line_total="1500.00",
        )

        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:order_detail", kwargs={"pk": order.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Самовывоз")
        self.assertContains(response, "Ожидает оплаты")
        self.assertContains(response, "Отменить заказ")
        self.assertContains(response, "Шарф")

    def test_user_order_detail_reflects_current_workflow_status(self):
        order = Order.objects.create(
            number="ORD-DETAIL-READY-1",
            user=self.user,
            recipient_name="Покупатель",
            email=self.user.email,
            phone="+79990000000",
            status=Order.Status.PROCESSING,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.RESERVED,
            delivery_method=Order.DeliveryMethod.PICKUP,
            pickup_point_code="main-store",
            total_amount="1500.00",
        )

        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:order_detail", kwargs={"pk": order.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Готов к выдаче")
        self.assertNotContains(response, "В обработке")

    def test_user_can_cancel_own_order_from_orders_page(self):
        """Отмена из UI должна проходить через доменный сервис и снимать резерв."""
        self.variant.reserved_quantity = 2
        self.variant.save(update_fields=["reserved_quantity", "updated_at"])
        order = Order.objects.create(
            number="ORD-CANCEL-UI-1",
            user=self.user,
            recipient_name="Покупатель",
            email=self.user.email,
            phone="+79990000000",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            total_amount="3000.00",
        )
        OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot="Шарф",
            unit_price="1500.00",
            quantity=2,
            line_total="3000.00",
        )

        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.post(reverse("users:order_cancel", kwargs={"pk": order.pk}), follow=True)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.CANCELLED)
        self.assertEqual(self.variant.quantity, 10)
        self.assertEqual(self.variant.reserved_quantity, 0)
        self.assertContains(response, "Заказ успешно отменен")

    def test_user_cannot_cancel_another_users_order(self):
        """Пользователь не может отменить чужой заказ."""
        other_user = User.objects.create_user(
            email="other-cancel@example.com", password="otherpass123", is_active=True
        )
        order = Order.objects.create(
            number="ORD-CANCEL-UI-2",
            user=other_user,
            recipient_name="Другой",
            email=other_user.email,
            phone="+79991111111",
            status=Order.Status.PLACED,
            payment_status=Order.PaymentStatus.PENDING,
            fulfillment_status=Order.FulfillmentStatus.NEW,
            delivery_method=Order.DeliveryMethod.PICKUP,
            total_amount="1500.00",
        )

        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.post(reverse("users:order_cancel", kwargs={"pk": order.pk}), follow=True)

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, Order.Status.PLACED)
        self.assertContains(response, "Недостаточно прав")

    def test_profile_list_view_staff_denied(self):
        """Обычному staff список профилей недоступен."""
        self.client.login(email="staff@example.com", password="staffpass123")
        response = self.client.get(reverse("users:profile_list"))

        self.assertEqual(response.status_code, 403)

    def test_profile_list_view_superuser(self):
        """Суперпользователь может видеть список профилей."""
        self.client.login(email="admin@example.com", password="adminpass123")
        response = self.client.get(reverse("users:profile_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "user@example.com")
        self.assertContains(response, "staff@example.com")

    def test_profile_list_view_regular_user_denied(self):
        """Проверяет сценарий 'profile list view regular user denied'."""
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_list"))

        self.assertEqual(response.status_code, 403)

    def test_profile_list_view_not_authenticated(self):
        """Проверяет сценарий 'profile list view not authenticated'."""
        response = self.client.get(reverse("users:profile_list"))
        self.assertEqual(response.status_code, 403)  # Permission denied due to raise_exception=True


class UserIntegrationTest(TestCase):
    """Тесты для UserIntegrationTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        self.client = Client()

    @patch("users.views.send_welcome_email")
    @patch("users.views.send_confirmation_email")
    def test_full_user_flow(self, mock_confirmation_email, mock_welcome_email):
        # 1. Register new user
        """Проверяет сценарий 'full user flow'."""
        form_data = {"email": "flowtest@example.com", "password1": "complexpass123", "password2": "complexpass123"}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("users:registration"), data=form_data)
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(email="flowtest@example.com")
        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.email_token)
        mock_confirmation_email.delay.assert_called_once_with("flowtest@example.com", ANY)
        mock_welcome_email.delay.assert_not_called()

        # 2. Confirm email
        response = self.client.get(reverse("users:confirm_email", kwargs={"token": user.email_token}))
        self.assertRedirects(response, reverse("users:profile_detail", kwargs={"pk": user.pk}))
        mock_welcome_email.delay.assert_called_once_with("flowtest@example.com")

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_confirmed)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

        # 3. View profile
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": user.pk}))
        self.assertEqual(response.status_code, 200)

        # 4. Update profile
        form_data = {"first_name": "Flow", "last_name": "Test"}
        response = self.client.post(reverse("users:profile_edit"), data=form_data)
        self.assertEqual(response.status_code, 302)

        user.refresh_from_db()
        self.assertEqual(user.first_name, "Flow")
        self.assertEqual(user.last_name, "Test")

        # 5. Logout
        response = self.client.post(reverse("users:logout"))
        self.assertEqual(response.status_code, 302)


class UserFormTest(TestCase):
    """Тесты для UserFormTest."""

    def setUp(self):
        """Подготавливает тестовые данные перед выполнением тестов."""
        from users.forms import ProfileDeleteConfirmForm, UserLoginForm, UserProfileForm, UserRegistrationForm

        self.UserRegistrationForm = UserRegistrationForm
        self.UserLoginForm = UserLoginForm
        self.UserProfileForm = UserProfileForm
        self.ProfileDeleteConfirmForm = ProfileDeleteConfirmForm

    def test_user_login_form_fields(self):
        """Проверяет сценарий 'user login form fields'."""
        form = self.UserLoginForm()
        self.assertIn("username", form.fields)
        self.assertIn("password", form.fields)
        self.assertEqual(form.fields["username"].label, "Email")
        self.assertEqual(form.fields["password"].label, "Пароль")
