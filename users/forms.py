from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from phonenumber_field.formfields import PhoneNumberField

from users.models import User


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


class UserProfileForm(forms.ModelForm):
    """Класс UserProfileForm."""

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
            "avatar": forms.FileInput(attrs={"class": "form-control"}),
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
