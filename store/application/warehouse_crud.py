from store.forms import ProductForm, VariantStockForm


class WarehouseCrudService:
    """Application-сервис CRUD-операций модераторского склада."""

    @staticmethod
    def save_product(form, is_on_sale=None):
        product = form.save(commit=False)
        if is_on_sale is not None:
            product.is_on_sale = bool(is_on_sale)
        product.save()
        form.save_m2m()
        return product

    @staticmethod
    def update_product(product, data):
        form = ProductForm(data, instance=product)
        if form.is_valid():
            form.save()
        return form

    @staticmethod
    def set_product_sale_state(product, is_on_sale: bool):
        product.is_on_sale = bool(is_on_sale)
        product.save(update_fields=["is_on_sale", "updated_at"])
        return product

    @staticmethod
    def save_variant(form, product=None):
        if product is not None:
            form.instance.product = product
        return form.save()

    @staticmethod
    def update_variant_stock(variant, data):
        form = VariantStockForm(data, instance=variant)
        if form.is_valid():
            form.save()
        return form

    @staticmethod
    def save_product_image(form, product):
        form.instance.product = product
        if form.cleaned_data.get("is_primary"):
            product.images.update(is_primary=False)
        return form.save()
