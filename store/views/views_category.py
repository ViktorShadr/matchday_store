from django.views.generic import DetailView, ListView

from store.models import Category
from store.services import CategoryService, PermissionService, ProductDisplayService
from store.services.catalog_service import enrich_products


class CategoryListView(ListView):
    """
    Список всех категорий.

    Отображает пагинированный список категорий.

    Attributes:
        paginate_by: Количество категорий на странице (20)
        context_object_name: Имя переменной в контексте ('categories')

    Context:
        categories: Список всех категорий
        user_permissions: Права текущего пользователя
    """

    model = Category
    template_name = "main_page/category_list.html"
    context_object_name = "categories"
    paginate_by = 20

    def get_queryset(self):
        """Возвращает queryset для текущего представления."""
        return Category.objects.all().order_by("name")

    def get_context_data(self, **kwargs):
        """Формирует контекст для шаблона."""
        context = super().get_context_data(**kwargs)
        context["user_permissions"] = PermissionService.get_user_permissions(self.request.user)
        return context


class CategoryDetailView(DetailView):
    """
    Детальная страница категории.

    Отображает информацию о категории и связанные товары.

    Context:
        category: Объект категории
        products: Товары этой категории
        category_data: Обогащённые данные категории
        user_permissions: Права текущего пользователя
    """

    model = Category
    template_name = "main_page/category_detail.html"
    context_object_name = "category"

    def get_context_data(self, **kwargs):
        """Формирует контекст для шаблона."""
        context = super().get_context_data(**kwargs)
        products = self.object.products.filter(is_on_sale=True).order_by("-created_at")

        context["products"] = enrich_products(products)
        context["products_prepared"] = [ProductDisplayService.prepare_category_product(p) for p in products]
        context["category_data"] = CategoryService.enrich_category(self.object, self.request.user)
        context["user_permissions"] = PermissionService.get_user_permissions(self.request.user)
        return context
