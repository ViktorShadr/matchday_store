from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

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
            }
        ),
    )
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите пароль",
            }
        ),
    )
    password2 = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Повторите пароль",
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
            }
        ),
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите пароль",
            }
        ),
    )


class UserProfileForm(forms.ModelForm):
    """Класс UserProfileForm."""

    class Meta:
        """Мета-настройки класса."""

        model = User
        fields = ("first_name", "last_name", "city", "avatar", "phone")

        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Введите имя",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Введите фамилию",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Введите город",
                }
            ),
            "avatar": forms.FileInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Введите номер телефона",
                }
            ),
        }


class ProfileDeleteConfirmForm(forms.Form):
    """Класс ProfileDeleteConfirmForm."""

    password = forms.CharField(
        label="Введите пароль для подтверждения",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите ваш текущий пароль",
            }
        ),
    )


class ResendConfirmationEmailForm(forms.Form):
    """Форма повторной отправки письма подтверждения email."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите email при регистрации",
            }
        ),
    )
