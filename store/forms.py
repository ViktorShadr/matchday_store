from decimal import Decimal
from pathlib import Path

from django import forms
from PIL import Image, UnidentifiedImageError

from store.models import Category, Product, ProductImage, ProductVariant


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Например, Шарфы"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "short_description",
            "description",
            "old_price",
            "material",
            "care_instructions",
            "size_guide",
            "category",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Название товара"}),
            "short_description": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Короткое описание для карточки"}
            ),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "old_price": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}),
            "material": forms.TextInput(attrs={"class": "form-control", "placeholder": "Например, хлопок 100%"}),
            "care_instructions": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "size_guide": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["sku", "size", "color", "price", "quantity", "image"]
        widgets = {
            "sku": forms.TextInput(attrs={"class": "form-control", "placeholder": "Например, SHIN-SCARF-001"}),
            "size": forms.TextInput(attrs={"class": "form-control", "placeholder": "L"}),
            "color": forms.TextInput(attrs={"class": "form-control", "placeholder": "Синий"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "image": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product or getattr(self.instance, "product", None)
        self.fields["image"].queryset = ProductImage.objects.none()
        if self.product:
            self.fields["image"].queryset = self.product.images.order_by("-is_primary", "-created_at")
        self.fields["image"].empty_label = "Без изображения"

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= Decimal("0.00"):
            raise forms.ValidationError("Цена должна быть больше нуля.")
        return price

    def clean_sku(self):
        return (self.cleaned_data.get("sku") or "").strip()

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        reserved_quantity = getattr(self.instance, "reserved_quantity", 0) or 0
        if quantity < reserved_quantity:
            raise forms.ValidationError(f"Физический остаток не может быть меньше резерва ({reserved_quantity} шт.).")
        return quantity


class ProductImageForm(forms.ModelForm):
    MAX_FILE_SIZE = 5 * 1024 * 1024
    ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
    ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})

    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary"]
        widgets = {
            "image": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/jpeg,image/png,image/webp,image/gif",
                }
            ),
            "alt_text": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Краткое описание изображения"}
            ),
            "is_primary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image

        if image.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError("Размер изображения не должен превышать 5 MB.")

        extension = Path(image.name).suffix.lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Допустимые форматы изображений: JPEG, PNG, WebP, GIF.")

        content_type = getattr(image, "content_type", "")
        if content_type and content_type not in self.ALLOWED_CONTENT_TYPES:
            raise forms.ValidationError("Допустимые форматы изображений: JPEG, PNG, WebP, GIF.")

        try:
            image.seek(0)
            with Image.open(image) as opened_image:
                opened_image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise forms.ValidationError("Загрузите корректный файл изображения.") from exc
        finally:
            image.seek(0)

        return image


class VariantStockForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["quantity"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
        }

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        reserved_quantity = getattr(self.instance, "reserved_quantity", 0) or 0
        if quantity < reserved_quantity:
            raise forms.ValidationError(f"Физический остаток не может быть меньше резерва ({reserved_quantity} шт.).")
        return quantity
