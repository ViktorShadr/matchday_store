from django.urls import reverse_lazy
from django.db.models import Min, Q, Sum, Value
from django.db.models.functions import Coalesce
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
        """Формирует контекст для шаблона."""
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
        """Возвращает queryset для текущего представления."""
        queryset = self.get_catalog_queryset()

        query = (self.request.GET.get("q") or "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))

        category_id = self.request.GET.get("category_id")
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        sort = self.request.GET.get("sort")
        if sort in {"price_asc", "price_desc"}:
            queryset = queryset.annotate(
                min_available_variant_price=Min("variants__price", filter=Q(variants__quantity__gt=0)),
                min_variant_price=Coalesce(
                    "min_available_variant_price",
                    Min("variants__price"),
                ),
            )

        if sort == "price_asc":
            return queryset.order_by("min_variant_price", "name", "id")
        if sort == "price_desc":
            return queryset.order_by("-min_variant_price", "name", "id")
        if sort == "name_asc":
            return queryset.order_by("name", "id")
        if sort == "name_desc":
            return queryset.order_by("-name", "id")

        queryset = queryset.annotate(
            popularity_score=Coalesce(Sum("variants__order_items__quantity"), Value(0)),
        )
        return queryset.order_by("-popularity_score", "-created_at", "id")

    def get_context_data(self, **kwargs):
        """Формирует контекст для шаблона."""
        context = super().get_context_data(**kwargs)
        context[self.context_object_name] = enrich_products(context[self.context_object_name])

        # Breadcrumbs
        breadcrumbs = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
        ]

        category_id = self.request.GET.get("category_id")
        if category_id:
            try:
                from store.models import Category

                category = Category.objects.get(id=category_id)
                context["selected_category"] = category
                breadcrumbs.append({"title": category.name, "url": None})
            except:
                breadcrumbs.append({"title": "Каталог", "url": None})
        else:
            breadcrumbs.append({"title": "Каталог", "url": None})

        context["breadcrumbs"] = breadcrumbs
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
        """Возвращает queryset для текущего представления."""
        return self.get_catalog_queryset()

    def get_context_data(self, **kwargs):
        """Формирует контекст для шаблона."""
        context = super().get_context_data(**kwargs)
        product = enrich_product(self.object)

        # Breadcrumbs
        breadcrumbs = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
            {"title": "Каталог", "url": reverse_lazy("store:product_list")},
        ]
        if product.category:
            breadcrumbs.append({
                "title": product.category.name,
                "url": reverse_lazy("store:product_list") + f"?category_id={product.category.id}"
            })
        breadcrumbs.append({"title": product.name, "url": None})
        context["breadcrumbs"] = breadcrumbs

        # Variants data
        variants = list(product.variants.all())
        available_variants = [variant for variant in variants if variant.quantity > 0]
        variant_prices = [v.price for v in variants if v.price]
        variant_quantities = [v.quantity for v in variants if v.quantity > 0]

        context["product"] = product
        context["product_details"] = ProductDisplayService.prepare_product_details(product)
        context["product_images"] = product.images.all()
        context["variants"] = variants
        context["available_variants"] = available_variants
        context["user_permissions"] = PermissionService.get_user_permissions(self.request.user)

        # Price range for Schema.org
        if variant_prices:
            context["min_price"] = min(variant_prices)
            context["max_price"] = max(variant_prices)
        else:
            context["min_price"] = product.display_price or 0
            context["max_price"] = product.display_price or 0

        # Stock info
        total_stock = sum(variant_quantities)
        context["total_stock"] = total_stock
        context["low_stock"] = 0 < total_stock <= 5

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
        """Возвращает URL для перенаправления после успешного действия."""
        return reverse_lazy("store:product_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        """Формирует контекст для шаблона."""
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
        """Возвращает URL для перенаправления после успешного действия."""
        return reverse_lazy("store:product_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        """Формирует контекст для шаблона."""
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
        """Формирует контекст для шаблона."""
        context = super().get_context_data(**kwargs)
        context["user_permissions"] = PermissionService.get_user_permissions(self.request.user)
        return context
