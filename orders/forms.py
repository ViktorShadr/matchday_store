from django import forms


class CheckoutForm(forms.Form):
    """Форма оформления заказа для MVP-сценария самовывоза."""

    recipient_name = forms.CharField(
        label="Получатель",
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Имя и фамилия",
            }
        ),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
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
