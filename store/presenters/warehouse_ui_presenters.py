from django.urls import reverse


class WarehouseUiPresenter:
    """Подготовка UI-контекста для warehouse CRUD шаблонов."""

    @staticmethod
    def product_create_context() -> dict:
        return {
            "page_title": "Добавить товар",
            "submit_label": "Создать товар",
        }

    @staticmethod
    def product_delete_context(product) -> dict:
        return {
            "page_title": "Удалить товар",
            "cancel_url": reverse("store:warehouse_product_manage", kwargs={"pk": product.pk}),
            "warning_text": "Товар и все его варианты будут удалены со склада.",
        }

    @staticmethod
    def category_create_context() -> dict:
        return {
            "page_title": "Создать категорию",
            "submit_label": "Создать категорию",
        }

    @staticmethod
    def category_update_context() -> dict:
        return {
            "page_title": "Редактировать категорию",
            "submit_label": "Сохранить",
        }

    @staticmethod
    def category_delete_context() -> dict:
        return {
            "page_title": "Удалить категорию",
            "cancel_url": reverse("store:warehouse_dashboard"),
            "warning_text": "Если в категории есть товары, они также будут удалены.",
        }

    @staticmethod
    def variant_create_context(product) -> dict:
        return {
            "product": product,
            "page_title": "Добавить вариант товара",
            "submit_label": "Создать вариант",
        }

    @staticmethod
    def variant_update_context(variant) -> dict:
        return {
            "product": variant.product,
            "page_title": "Редактировать вариант",
            "submit_label": "Сохранить",
        }

    @staticmethod
    def variant_delete_context(variant) -> dict:
        return {
            "page_title": "Удалить вариант",
            "cancel_url": reverse("store:warehouse_product_manage", kwargs={"pk": variant.product.pk}),
            "warning_text": "Остаток этого варианта будет удалён со склада.",
        }

    @staticmethod
    def image_create_context(product) -> dict:
        return {
            "product": product,
            "page_title": "Добавить изображение",
            "submit_label": "Загрузить",
        }

    @staticmethod
    def image_delete_context(image) -> dict:
        return {
            "page_title": "Удалить изображение",
            "cancel_url": reverse("store:warehouse_product_manage", kwargs={"pk": image.product.pk}),
            "warning_text": "При удалении изображение будет отвязано от связанных вариантов товара.",
        }
