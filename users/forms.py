from pathlib import Path

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, UserCreationForm
from phonenumber_field.formfields import PhoneNumberField

from users.models import User

AVATAR_MAX_SIZE_BYTES = 2 * 1024 * 1024
AVATAR_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AVATAR_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
AVATAR_ALLOWED_MIME_TYPES = "image/jpeg,image/png,image/webp"
AVATAR_HELP_TEXT = "Загрузите фото в формате JPG, PNG или WebP. Размер файла — до 2 МБ."


class AvatarImageField(forms.ImageField):
    """Проверяет аватар до сохранения профиля."""

    default_error_messages = {
        **forms.ImageField.default_error_messages,
        "file_too_large": "Размер аватара не должен превышать 2 МБ.",
        "invalid_extension": "Загрузите изображение в формате JPG, PNG или WebP.",
        "invalid_image": "Загрузите корректное изображение в формате JPG, PNG или WebP.",
    }

    def to_python(self, data):
        if data in self.empty_values:
            return None

        if getattr(data, "size", 0) > AVATAR_MAX_SIZE_BYTES:
            raise forms.ValidationError(self.error_messages["file_too_large"], code="file_too_large")

        extension = Path(getattr(data, "name", "")).suffix.lower()
        if extension and extension not in AVATAR_ALLOWED_EXTENSIONS:
            raise forms.ValidationError(self.error_messages["invalid_extension"], code="invalid_extension")

        try:
            image = super().to_python(data)
        except forms.ValidationError as exc:
            raise forms.ValidationError(self.error_messages["invalid_image"], code="invalid_image") from exc

        image_format = getattr(getattr(image, "image", None), "format", "")
        if image_format and image_format.upper() not in AVATAR_ALLOWED_FORMATS:
            raise forms.ValidationError(self.error_messages["invalid_extension"], code="invalid_extension")

        return image


class UserRegistrationForm(UserCreationForm):
    """Класс UserRegistrationForm."""

    email = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите ваш email",
                "autocomplete": "email",
                "inputmode": "email",
                "autocapitalize": "off",
                "spellcheck": "false",
                "autofocus": True,
            }
        ),
    )
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите пароль",
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Повторите пароль",
                "autocomplete": "new-password",
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        """Мета-настройки класса."""

        model = User
        fields = ("email", "password1", "password2")

    def clean_email(self):
        """Проверяет корректность и уникальность электронной почты."""
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже зарегистрирован")
        return email


class UserLoginForm(AuthenticationForm):
    """Класс UserLoginForm."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите ваш email",
                "autocomplete": "username email",
                "inputmode": "email",
                "autocapitalize": "off",
                "spellcheck": "false",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите пароль",
                "autocomplete": "current-password",
            }
        ),
    )


class UserPasswordResetForm(PasswordResetForm):
    """Форма запроса восстановления пароля."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите email аккаунта",
                "autocomplete": "email",
                "inputmode": "email",
                "autocapitalize": "off",
                "spellcheck": "false",
                "autofocus": True,
            }
        ),
    )


class UserSetPasswordForm(SetPasswordForm):
    """Форма установки нового пароля."""

    new_password1 = forms.CharField(
        label="Новый пароль",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите новый пароль",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Подтверждение нового пароля",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Повторите новый пароль",
                "autocomplete": "new-password",
            }
        ),
    )


class UserProfileForm(forms.ModelForm):
    """Класс UserProfileForm."""

    avatar = AvatarImageField(
        required=False,
        label="Аватар",
        help_text=AVATAR_HELP_TEXT,
        widget=forms.FileInput(
            attrs={
                "class": "form-control",
                "accept": AVATAR_ALLOWED_MIME_TYPES,
                "data-avatar-upload": "true",
                "data-max-size": str(AVATAR_MAX_SIZE_BYTES),
                "data-size-error": "Размер аватара не должен превышать 2 МБ.",
                "data-type-error": "Загрузите фото в формате JPG, PNG или WebP.",
            }
        ),
    )
    phone = PhoneNumberField(
        required=False,
        region="RU",
        error_messages={"invalid": "Введите корректный номер телефона в формате +79991234567"},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите номер в формате +79991234567",
                "type": "tel",
                "autocomplete": "tel",
                "inputmode": "tel",
            }
        ),
    )

    class Meta:
        """Мета-настройки класса."""

        model = User
        fields = ("first_name", "last_name", "city", "avatar", "phone")

        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Введите имя",
                    "autocomplete": "given-name",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Введите фамилию",
                    "autocomplete": "family-name",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Введите город",
                    "autocomplete": "address-level2",
                }
            ),
        }

    def clean_phone(self):
        """Нормализует телефон к формату E.164."""
        phone = self.cleaned_data.get("phone")
        if not phone:
            return ""
        return phone.as_e164


class ProfileDeleteConfirmForm(forms.Form):
    """Класс ProfileDeleteConfirmForm."""

    password = forms.CharField(
        label="Введите пароль для подтверждения",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите ваш текущий пароль",
                "autocomplete": "current-password",
            }
        ),
    )
