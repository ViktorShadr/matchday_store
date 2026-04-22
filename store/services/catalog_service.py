from store.presenters.catalog_presenters import ProductCardPresenter
from store.queries.catalog_queries import CatalogQueryService


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
    return CatalogQueryService.base_queryset()


def enrich_product(product):
    """
    Обогащает объект товара дополнительными данными для отображения.

    Добавляет атрибуты:
    - display_image: основное изображение товара
    - display_price: цена первого варианта товара
    - in_stock: есть ли хотя бы один вариант в наличии

    Алгоритм выбора изображения:
    1. Основное изображение (is_primary=True)
    2. Первое изображение из списка
    3. Изображение первого варианта товара

    Args:
        product (Product): Объект товара для обогащения

    Returns:
        Product: Тот же объект товара с добавленными атрибутами
    """
    return ProductCardPresenter.enrich(product)


def enrich_products(products):
    """
    Обогащает список товаров дополнительными данными.

    Применяет функцию enrich_product к каждому товару в списке.

    Args:
        products (Iterable[Product]): Список или queryset товаров

    Returns:
        list[Product]: Список обогащённых товаров
    """
    return ProductCardPresenter.enrich_many(products)
