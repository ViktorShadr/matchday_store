from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView, TemplateView, UpdateView, CreateView

from store.mixins import CatalogQuerysetMixin, CategoriesContextMixin, ModeratorRequiredMixin
from store.mixins.cart_mixins import CartContextMixin
from store.models import Product
from store.services import enrich_product, enrich_products, ProductDisplayService, PermissionService


class MainView(CategoriesContextMixin, CartContextMixin, CatalogQuerysetMixin, TemplateView):
    """
    Главная страница магазина.

    Отображает главную страницу с популярными товарами и категориями.

    Context:
        categories: Все категории магазина
        popular_products: 6 последних товаров с обогащёнными данными
    """

    template_name = "main_page/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["popular_products"] = enrich_products(self.get_catalog_queryset().order_by("-created_at")[:6])
        return context


class ProductListView(CategoriesContextMixin, CartContextMixin, CatalogQuerysetMixin, ListView):
    """
    Список товаров каталога.

    Отображает пагинированный список всех товаров с категориями.
    Поддерживает фильтрацию по категориям через параметр category_id.

    Attributes:
        paginate_by: Количество товаров на странице (12)
        context_object_name: Имя переменной в контексте ('products')

    Context:
        categories: Все категории магазина
        products: Список товаров с обогащёнными данными
        selected_category: Выбранная категория (если передана)
    """

    model = Product
    template_name = "main_page/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        queryset = self.get_catalog_queryset().order_by("-created_at")
        category_id = self.request.GET.get("category_id")
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.context_object_name] = enrich_products(context[self.context_object_name])

        category_id = self.request.GET.get("category_id")
        if category_id:
            try:
                from store.models import Category

                context["selected_category"] = Category.objects.get(id=category_id)
            except:
                pass

        return context


class ProductDetailsView(CartContextMixin, CatalogQuerysetMixin, DetailView):
    """
    Детальная страница товара.

    Отображает подробную информацию о товаре,
    включая изображения и варианты.

    Context:
        product: Обогащённый объект товара
        product_images: Все изображения товара
        variants: Все варианты товара
    """

    model = Product
    template_name = "main_page/product_details.html"
    context_object_name = "product"

    def get_queryset(self):
        return self.get_catalog_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = enrich_product(self.object)

        context["product"] = product
        context["product_details"] = ProductDisplayService.prepare_product_details(product)
        context["product_images"] = product.images.all()
        context["variants"] = product.variants.all()
        context["user_permissions"] = PermissionService.get_user_permissions(self.request.user)
        return context


class ProductUpdateView(ModeratorRequiredMixin, UpdateView):
    """
    Редактирование товара (только для персонала).

    Позволяет сотрудникам редактировать основную информацию о товаре.

    Fields:
        name, description, category: Основные поля товара

    Returns:
        HttpResponseRedirect: Перенаправление на страницу товара после сохранения
    """

    model = Product
    template_name = "main_page/product_update.html"
    fields = ["name", "description", "category"]
    context_object_name = "product"

    def get_success_url(self):
        return reverse_lazy("store:product_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_permissions"] = PermissionService.get_user_permissions(self.request.user)
        return context


class ProductCreateView(ModeratorRequiredMixin, CreateView):
    """
    Создание нового товара (только для персонала).

    Позволяет сотрудникам создавать новые товары в каталоге.

    Fields:
        name, description, category: Основные поля товара

    Returns:
        HttpResponseRedirect: Перенаправление на страницу созданного товара
    """

    model = Product
    template_name = "main_page/product_create.html"
    fields = ["name", "description", "category"]
    context_object_name = "product"

    def get_success_url(self):
        return reverse_lazy("store:product_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_permissions"] = PermissionService.get_user_permissions(self.request.user)
        return context


class ProductDeleteView(ModeratorRequiredMixin, DeleteView):
    """
    Удаление товара (только для персонала).

    Позволяет сотрудникам удалять товары из каталога.

    Returns:
        HttpResponseRedirect: Перенаправление на список товаров после удаления
    """

    model = Product
    template_name = "main_page/product_delete.html"
    context_object_name = "product"
    success_url = reverse_lazy("store:product_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_permissions"] = PermissionService.get_user_permissions(self.request.user)
        return context
