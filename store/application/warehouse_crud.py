from store.forms import ProductForm, VariantStockForm


class WarehouseCrudService:
    """Application-сервис CRUD-операций модераторского склада."""

    @staticmethod
    def update_product(product, data):
        form = ProductForm(data, instance=product)
        if form.is_valid():
            form.save()
        return form

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
