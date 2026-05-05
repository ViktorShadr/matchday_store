import re

from django import forms

PHONE_ALLOWED_CHARS_RE = re.compile(r"^[\d\s()+-]+$")


class CheckoutForm(forms.Form):
    """Форма оформления заказа для MVP-сценария самовывоза."""

    recipient_name = forms.CharField(
        label="Получатель",
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Имя и фамилия",
                "autocomplete": "name",
                "autofocus": True,
            }
        ),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "autocomplete": "email",
                "inputmode": "email",
                "autocapitalize": "off",
                "spellcheck": "false",
            }
        ),
    )
    phone = forms.CharField(
        label="Телефон",
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "+7 (900) 000-00-00",
                "type": "tel",
                "autocomplete": "tel",
                "inputmode": "tel",
            }
        ),
    )
    customer_comment = forms.CharField(
        label="Комментарий к заказу",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Например, подготовьте заказ к вечеру",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            self.fields["email"].initial = user.email
            self.fields["email"].disabled = True

    @staticmethod
    def _normalize_whitespace(value: str) -> str:
        """Убрать лишние пробелы и привести строку к компактному виду."""
        return " ".join(value.split())

    @staticmethod
    def _looks_like_garbage(value: str) -> bool:
        """Отфильтровать явно мусорные значения."""
        compact_value = value.replace(" ", "")
        if not compact_value:
            return True
        if len(compact_value) >= 4 and len(set(compact_value)) == 1:
            return True
        return not any(char.isalnum() for char in compact_value)

    def clean_recipient_name(self):
        recipient_name = self._normalize_whitespace(self.cleaned_data["recipient_name"])

        if self._looks_like_garbage(recipient_name):
            raise forms.ValidationError("Введите корректное имя получателя.")

        if sum(char.isalpha() for char in recipient_name) < 2:
            raise forms.ValidationError("Введите корректное имя получателя.")

        return recipient_name

    def clean_email(self):
        if self.user is not None:
            return self._normalize_whitespace(self.user.email)
        return self._normalize_whitespace(self.cleaned_data["email"])

    def clean_phone(self):
        phone = self._normalize_whitespace(self.cleaned_data["phone"])

        if not PHONE_ALLOWED_CHARS_RE.fullmatch(phone):
            raise forms.ValidationError("Введите корректный номер телефона.")

        if phone.count("+") > 1 or ("+" in phone and not phone.startswith("+")):
            raise forms.ValidationError("Введите корректный номер телефона.")

        digits = re.sub(r"\D", "", phone)
        if not 10 <= len(digits) <= 15:
            raise forms.ValidationError("Введите корректный номер телефона.")

        if len(set(digits)) < 2:
            raise forms.ValidationError("Введите корректный номер телефона.")

        return f"+{digits}"

    def clean_customer_comment(self):
        return self._normalize_whitespace(self.cleaned_data.get("customer_comment", ""))
