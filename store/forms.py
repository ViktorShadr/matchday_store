from django import forms

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
        fields = ["name", "description", "category"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Название товара"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["size", "color", "price", "quantity", "image"]
        widgets = {
            "size": forms.TextInput(attrs={"class": "form-control", "placeholder": "L"}),
            "color": forms.TextInput(attrs={"class": "form-control", "placeholder": "Синий"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
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


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "alt_text": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое описание изображения"}),
            "is_primary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class VariantStockForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["quantity"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
        }
