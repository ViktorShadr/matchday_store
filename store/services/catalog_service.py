from django.db.models import Prefetch

from store.models import Product, ProductVariant


def get_catalog_queryset():
    """
    Возвращает оптимизированный queryset для товаров каталога.

    Выполняет предварительную загрузку связанных данных:
    - Категории товаров (select_related)
    - Изображения товаров (prefetch_related)
    - Варианты товаров с изображениями (Prefetch с сортировкой)

    Returns:
        QuerySet: Оптимизированный queryset товаров
    """
    return Product.objects.select_related("category").prefetch_related(
        "images",
        Prefetch(
            "variants",
            queryset=ProductVariant.objects.select_related("image").order_by("price", "id"),
        ),
    )


def enrich_product(product):
    """
    Обогащает объект товара дополнительными данными для отображения.

    Добавляет атрибуты:
    - display_image: основное изображение товара
    - display_price: цена первого варианта товара

    Алгоритм выбора изображения:
    1. Основное изображение (is_primary=True)
    2. Первое изображение из списка
    3. Изображение первого варианта товара

    Args:
        product (Product): Объект товара для обогащения

    Returns:
        Product: Тот же объект товара с добавленными атрибутами
    """
    images = list(product.images.all())
    variants = list(product.variants.all())

    primary_image = next((image for image in images if image.is_primary), None)
    first_image = primary_image or (images[0] if images else None)
    first_variant = variants[0] if variants else None

    product.display_image = (
        first_image.image if first_image else getattr(getattr(first_variant, "image", None), "image", None)
    )
    product.display_price = first_variant.price if first_variant else None
    return product


def enrich_products(products):
    """
    Обогащает список товаров дополнительными данными.

    Применяет функцию enrich_product к каждому товару в списке.

    Args:
        products (Iterable[Product]): Список или queryset товаров

    Returns:
        list[Product]: Список обогащённых товаров
    """
    return [enrich_product(product) for product in products]
