from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from users.forms import UserRegistrationForm, UserProfileForm, ProfileDeleteConfirmForm

User = get_user_model()


class UserModelTest(TestCase):
    def setUp(self):
        self.user_data = {
            "email": "test@example.com",
            "password": "testpass123",
            "first_name": "Test",
            "last_name": "User",
        }

    def test_create_user_with_email(self):
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "Test")
        self.assertEqual(user.last_name, "User")
        self.assertTrue(user.check_password("testpass123"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_without_email_fails(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email=None, password="testpass123")

    def test_create_superuser(self):
        admin_user = User.objects.create_superuser(email="admin@example.com", password="adminpass123")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertEqual(admin_user.email, "admin@example.com")

    def test_user_str_method(self):
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(str(user), "test@example.com")

    def test_email_normalization(self):
        user = User.objects.create_user(email="Test@EXAMPLE.COM", password="testpass123")
        self.assertEqual(user.email, "Test@example.com")


class UserRegistrationFormTest(TestCase):
    def test_valid_registration_form(self):
        form_data = {"email": "newuser@example.com", "password1": "complexpass123", "password2": "complexpass123"}
        form = UserRegistrationForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_duplicate_email_validation(self):
        User.objects.create_user(email="existing@example.com", password="pass123")
        form_data = {"email": "existing@example.com", "password1": "complexpass123", "password2": "complexpass123"}
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        self.assertIn("Пользователь с таким email уже зарегистрирован", form.errors["email"])

    def test_password_mismatch(self):
        form_data = {"email": "test@example.com", "password1": "pass123", "password2": "different123"}
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())


class UserProfileFormTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="test@example.com", password="testpass123")

    def test_valid_profile_form(self):
        form_data = {"first_name": "John", "last_name": "Doe", "city": "New York", "phone": "+1234567890"}
        form = UserProfileForm(data=form_data, instance=self.user)
        self.assertTrue(form.is_valid())

    def test_form_save(self):
        form_data = {"first_name": "Jane", "last_name": "Smith"}
        form = UserProfileForm(data=form_data, instance=self.user)
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(self.user.last_name, "Smith")


class ProfileDeleteConfirmFormTest(TestCase):
    def test_empty_password(self):
        form = ProfileDeleteConfirmForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_valid_password(self):
        form = ProfileDeleteConfirmForm(data={"password": "somepassword"})
        self.assertTrue(form.is_valid())


class UserViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="user@example.com", password="userpass123")
        self.staff_user = User.objects.create_user(email="staff@example.com", password="staffpass123", is_staff=True)

    @patch("users.views.send_welcome_email")
    def test_registration_view_success(self, mock_email):
        form_data = {"email": "newuser@example.com", "password1": "complexpass123", "password2": "complexpass123"}
        response = self.client.post(reverse("users:registration"), data=form_data)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("users:login"))

        self.assertTrue(User.objects.filter(email="newuser@example.com").exists())
        mock_email.delay.assert_called_once_with("newuser@example.com")

    def test_registration_view_failure(self):
        form_data = {"email": "user@example.com", "password1": "pass123", "password2": "different"}  # Already exists
        response = self.client.post(reverse("users:registration"), data=form_data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="user@example.com").count() > 1)

    def test_login_view_success(self):
        response = self.client.post(
            reverse("users:login"), {"username": "user@example.com", "password": "userpass123"}
        )
        self.assertEqual(response.status_code, 302)

    def test_login_view_failure(self):
        response = self.client.post(
            reverse("users:login"), {"username": "user@example.com", "password": "wrongpassword"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_view(self):
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.post(reverse("users:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("store:base"))

    def test_profile_detail_view_own_profile(self):
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": self.user.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "user@example.com")

    def test_profile_detail_view_other_profile_denied(self):
        other_user = User.objects.create_user(email="other@example.com", password="otherpass123")
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": other_user.pk}))

        self.assertEqual(response.status_code, 403)

    def test_profile_detail_view_staff_can_see_all(self):
        other_user = User.objects.create_user(email="other@example.com", password="otherpass123")
        self.client.login(email="staff@example.com", password="staffpass123")
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": other_user.pk}))

        self.assertEqual(response.status_code, 200)

    def test_profile_detail_view_not_authenticated(self):
        response = self.client.get(reverse("users:profile_detail", kwargs={"pk": self.user.pk}))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_update_view(self):
        self.client.login(email="user@example.com", password="userpass123")
        form_data = {"first_name": "Updated", "last_name": "Name", "city": "New City", "phone": "+9876543210"}
        response = self.client.post(reverse("users:profile_edit"), data=form_data)

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Name")

    def test_profile_update_view_not_authenticated(self):
        response = self.client.get(reverse("users:profile_edit"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_delete_view_success(self):
        self.client.login(email="user@example.com", password="userpass123")
        form_data = {"password": "userpass123"}
        response = self.client.post(reverse("users:profile_delete"), data=form_data)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("store:base"))
        self.assertFalse(User.objects.filter(email="user@example.com").exists())

    def test_profile_delete_view_wrong_password(self):
        self.client.login(email="user@example.com", password="userpass123")
        form_data = {"password": "wrongpassword"}
        response = self.client.post(reverse("users:profile_delete"), data=form_data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email="user@example.com").exists())
        self.assertContains(response, "Неверный пароль")

    def test_profile_delete_view_not_authenticated(self):
        response = self.client.get(reverse("users:profile_delete"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_list_view_staff(self):
        self.client.login(email="staff@example.com", password="staffpass123")
        response = self.client.get(reverse("users:profile_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "user@example.com")
        self.assertContains(response, "staff@example.com")

    def test_profile_list_view_regular_user_denied(self):
        self.client.login(email="user@example.com", password="userpass123")
        response = self.client.get(reverse("users:profile_list"))

        self.assertEqual(response.status_code, 403)

    def test_profile_list_view_not_authenticated(self):
        response = self.client.get(reverse("users:profile_list"))
        self.assertEqual(response.status_code, 403)  # Permission denied due to raise_exception=True


class UserIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()

    @patch("users.views.send_welcome_email")
    def test_full_user_flow(self, mock_email):
        # 1. Register new user
        form_data = {"email": "flowtest@example.com", "password1": "complexpass123", "password2": "complexpass123"}
        response = self.client.post(reverse("users:registration"), data=form_data)
        self.assertEqual(response.status_code, 302)

        # 2. Login
        response = self.client.post(
            reverse("users:login"), {"username": "flowtest@example.com", "password": "complexpass123"}
        )
        self.assertEqual(response.status_code, 302)

        # 3. View profile
        user = User.objects.get(email="flowtest@example.com")
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
    def setUp(self):
        from users.forms import UserRegistrationForm, UserLoginForm, UserProfileForm, ProfileDeleteConfirmForm

        self.UserRegistrationForm = UserRegistrationForm
        self.UserLoginForm = UserLoginForm
        self.UserProfileForm = UserProfileForm
        self.ProfileDeleteConfirmForm = ProfileDeleteConfirmForm

    def test_user_login_form_fields(self):
        form = self.UserLoginForm()
        self.assertIn("username", form.fields)
        self.assertIn("password", form.fields)
        self.assertEqual(form.fields["username"].label, "Email")
        self.assertEqual(form.fields["password"].label, "Пароль")
