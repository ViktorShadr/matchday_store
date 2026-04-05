from store.models import Category
from store.services import get_catalog_queryset


class CategoriesContextMixin:
    """
    Миксин для добавления категорий в контекст шаблона.

    Автоматически добавляет все категории, отсортированные по имени,
    в контекст под ключом 'categories'.

    Attributes:
        categories_context_key (str): Ключ для добавления категорий в контекст

    Использование:
        class MyView(CategoriesContextMixin, TemplateView):
            template_name = 'my_template.html'
            # в шаблоне будут доступны {{ categories }}
    """

    categories_context_key = "categories"

    def get_categories(self):
        """
        Получение queryset категорий.

        Returns:
            QuerySet: Категории, отсортированные по имени
        """
        return Category.objects.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.categories_context_key] = self.get_categories()
        return context


class CatalogQuerysetMixin:
    """
    Миксин для получения оптимизированного queryset товаров каталога.

    Предоставляет метод get_catalog_queryset(), который возвращает
    оптимизированный queryset с предварительной загрузкой связанных данных.

    Использование:
        class ProductListView(CatalogQuerysetMixin, ListView):
            def get_queryset(self):
                return self.get_catalog_queryset()
    """

    def get_catalog_queryset(self):
        """
        Получение оптимизированного queryset товаров каталога.

        Returns:
            QuerySet: Оптимизированный queryset товаров с preload данных
        """
        return get_catalog_queryset()
