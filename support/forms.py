from django import forms

from support.models import SupportRequest

MAX_SUBJECT_LENGTH = 160
MAX_MESSAGE_LENGTH = 4000


class SupportRequestForm(forms.ModelForm):
    website = forms.CharField(
        required=False,
        label="",
        widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1", "class": "d-none"}),
    )
    personal_data_consent = forms.BooleanField(
        required=True,
        label="Я согласен на обработку персональных данных для ответа на обращение",
        error_messages={"required": "Подтвердите согласие на обработку персональных данных."},
    )

    class Meta:
        model = SupportRequest
        fields = ["name", "email", "phone", "subject", "message"]
        labels = {
            "name": "Имя",
            "email": "Email",
            "phone": "Телефон",
            "subject": "Тема",
            "message": "Сообщение",
        }
        help_texts = {
            "phone": "Необязательно. Укажите номер, если удобнее получить ответ по телефону.",
            "message": f"До {MAX_MESSAGE_LENGTH} символов.",
        }
        error_messages = {
            "name": {
                "required": "Укажите имя.",
                "max_length": "Имя не должно быть длиннее 150 символов.",
            },
            "email": {
                "required": "Укажите email для ответа.",
                "invalid": "Введите корректный email.",
            },
            "phone": {
                "max_length": "Телефон не должен быть длиннее 32 символов.",
            },
            "subject": {
                "required": "Укажите тему обращения.",
                "max_length": f"Тема не должна быть длиннее {MAX_SUBJECT_LENGTH} символов.",
            },
            "message": {
                "required": "Напишите сообщение.",
            },
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ваше имя"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+7 999 000-00-00"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "Кратко опишите вопрос"}),
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "Опишите ситуацию: номер заказа, товар или вопрос по доставке.",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["subject"].max_length = MAX_SUBJECT_LENGTH
        self.fields["message"].max_length = MAX_MESSAGE_LENGTH
        self.fields["personal_data_consent"].widget.attrs.update({"class": "form-check-input"})

        if user and getattr(user, "is_authenticated", False):
            full_name = user.get_full_name().strip()
            self.fields["name"].initial = full_name or user.email
            self.fields["email"].initial = user.email
            self.fields["phone"].initial = user.phone or ""

    def clean_website(self):
        value = (self.cleaned_data.get("website") or "").strip()
        if value:
            raise forms.ValidationError("Не удалось отправить обращение. Попробуйте еще раз.")
        return value

    def clean_subject(self):
        return (self.cleaned_data.get("subject") or "").strip()

    def clean_message(self):
        message = (self.cleaned_data.get("message") or "").strip()
        if len(message) > MAX_MESSAGE_LENGTH:
            raise forms.ValidationError(f"Сообщение не должно быть длиннее {MAX_MESSAGE_LENGTH} символов.")
        return message

    def clean_phone(self):
        return (self.cleaned_data.get("phone") or "").strip()
