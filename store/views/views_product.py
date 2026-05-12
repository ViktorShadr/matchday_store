from django.urls import reverse, reverse_lazy
from django.views.generic import DetailView, ListView, TemplateView

from store.mixins import CatalogQuerysetMixin, CategoriesContextMixin
from store.mixins.cart_mixins import CartContextMixin
from store.models import Category, InfoCard, Product
from store.queries import CatalogQueryService
from store.services import PermissionService, ProductDisplayService, enrich_product, enrich_products


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
        context["popular_products"] = enrich_products(CatalogQueryService.build_popular_products_queryset()[:6])
        context["info_cards"] = InfoCard.objects.filter(is_published=True).order_by("sort_order", "id")
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
    FILTER_KEYS = ("q", "category_id", "sort", "size", "in_stock", "price_min", "price_max")

    def _get_filter_params(self):
        return {
            "query": (self.request.GET.get("q") or "").strip(),
            "category_id": (self.request.GET.get("category_id") or "").strip(),
            "sort": (self.request.GET.get("sort") or "").strip(),
            "size": (self.request.GET.get("size") or "").strip(),
            "in_stock": self.request.GET.get("in_stock") == "1",
            "price_min": (self.request.GET.get("price_min") or "").strip(),
            "price_max": (self.request.GET.get("price_max") or "").strip(),
        }

    def _build_catalog_url(self, **updates):
        params = self.request.GET.copy()
        params.pop("page", None)
        for key, value in updates.items():
            if value in (None, "", False):
                params.pop(key, None)
            else:
                params[key] = str(value)
        query_string = params.urlencode()
        base_url = reverse("store:product_list")
        return f"{base_url}?{query_string}" if query_string else base_url

    def _build_category_links(self, categories):
        links = [
            {
                "name": "Все",
                "url": self._build_catalog_url(category_id=""),
                "is_active": not self.request.GET.get("category_id"),
            }
        ]
        current_category_id = self.request.GET.get("category_id")
        for category in categories:
            links.append(
                {
                    "name": category.name,
                    "url": self._build_catalog_url(category_id=category.pk),
                    "is_active": current_category_id == str(category.pk),
                }
            )
        return links

    def get_queryset(self):
        """Возвращает queryset для текущего представления."""
        filters = self._get_filter_params()
        category_id = filters["category_id"] if filters["category_id"].isdigit() else ""
        return CatalogQueryService.build_product_list_queryset(
            query=filters["query"],
            category_id=category_id,
            sort=filters["sort"],
            size=filters["size"],
            in_stock=filters["in_stock"],
            price_min=filters["price_min"],
            price_max=filters["price_max"],
        )

    def get_context_data(self, **kwargs):
        """Формирует контекст для шаблона."""
        context = super().get_context_data(**kwargs)
        context[self.context_object_name] = enrich_products(context[self.context_object_name])

        # Breadcrumbs
        breadcrumbs = [
            {"title": "Главная", "url": reverse_lazy("store:base")},
        ]

        filters = self._get_filter_params()
        category_id = filters["category_id"]
        selected_category = None
        if category_id.isdigit():
            selected_category = Category.objects.filter(id=category_id).first()
        if selected_category:
            context["selected_category"] = selected_category
            breadcrumbs.append({"title": selected_category.name, "url": None})
        else:
            breadcrumbs.append({"title": "Каталог", "url": None})

        pagination_params = self.request.GET.copy()
        pagination_params.pop("page", None)
        context["catalog_filters"] = filters
        context["catalog_available_sizes"] = CatalogQueryService.build_available_sizes_queryset()
        context["catalog_category_links"] = self._build_category_links(context.get("categories", []))
        context["catalog_page_query"] = pagination_params.urlencode()
        context["has_active_catalog_filters"] = any(
            [
                filters["query"],
                selected_category,
                filters["sort"],
                filters["size"],
                filters["in_stock"],
                filters["price_min"],
                filters["price_max"],
            ]
        )
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
            breadcrumbs.append(
                {
                    "title": product.category.name,
                    "url": reverse_lazy("store:product_list") + f"?category_id={product.category.id}",
                }
            )
        breadcrumbs.append({"title": product.name, "url": None})
        context["breadcrumbs"] = breadcrumbs

        # Variants data
        variants = list(product.variants.all())
        available_variants = [variant for variant in variants if variant.available_quantity > 0]
        variant_prices = [v.price for v in variants if v.price]
        variant_quantities = [v.available_quantity for v in variants if v.available_quantity > 0]

        gallery_images = list(getattr(product, "gallery_images", []))
        prepared_gallery_images = [
            {
                "url": image.image.url,
                "alt": image.alt_text or product.name,
            }
            for image in gallery_images
            if getattr(image, "image", None)
        ]
        if not prepared_gallery_images and getattr(product, "display_image", None):
            prepared_gallery_images.append(
                {
                    "url": product.display_image.url,
                    "alt": product.name,
                }
            )

        context["product"] = product
        context["product_details"] = ProductDisplayService.prepare_product_details(product)
        context["product_images"] = gallery_images
        context["product_gallery_images"] = prepared_gallery_images
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
