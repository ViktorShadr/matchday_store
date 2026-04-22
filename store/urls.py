from django.urls import path
from django.views.generic import RedirectView

from store.views.views_product import (
    MainView,
    ProductListView,
    ProductDetailsView,
    ProductUpdateView,
    ProductDeleteView,
    ProductCreateView,
)
from store.views.views_category import (
    CategoryListView,
    CategoryDetailView,
    CategoryCreateView,
    CategoryUpdateView,
    CategoryDeleteView,
)
from store.views.views_cart import AddToCartView, UpdateCartView, RemoveFromCartView
from store.views.views_cart_page import CartView
from store.views.views_legal import (
    PrivacyPolicyView,
    TermsOfServiceView,
    ReturnPolicyView,
    OfferView,
    Error404View,
    Error500View,
)
from store.views.views_dashboard import (
    DashboardHomeView,
    WarehouseDashboardView,
    OrdersDashboardView,
    DashboardOrderDetailView,
    DashboardOrderStatusUpdateView,
    DashboardOrderPaymentStatusUpdateView,
    WarehouseProductCreateView,
    WarehouseProductDeleteView,
    WarehouseCategoryCreateView,
    WarehouseCategoryUpdateView,
    WarehouseCategoryDeleteView,
    WarehouseProductManageView,
    WarehouseVariantCreateView,
    WarehouseVariantUpdateView,
    WarehouseVariantDeleteView,
    WarehouseVariantStockUpdateView,
    WarehouseImageCreateView,
    WarehouseImageDeleteView,
)

app_name = "store"

urlpatterns = [
    path("", MainView.as_view(), name="base"),
    path("dashboard/", DashboardHomeView.as_view(), name="dashboard_home"),
    path("dashboard/stock/", WarehouseDashboardView.as_view(), name="warehouse_dashboard"),
    path(
        "dashboard/warehouse/",
        RedirectView.as_view(pattern_name="store:warehouse_dashboard", permanent=False),
    ),
    path("dashboard/orders/", OrdersDashboardView.as_view(), name="dashboard_orders"),
    path("dashboard/orders/<int:pk>/", DashboardOrderDetailView.as_view(), name="dashboard_order_detail"),
    path(
        "dashboard/orders/<int:pk>/status/",
        DashboardOrderStatusUpdateView.as_view(),
        name="dashboard_order_status_update",
    ),
    path(
        "dashboard/orders/<int:pk>/payment/",
        DashboardOrderPaymentStatusUpdateView.as_view(),
        name="dashboard_order_payment_status_update",
    ),
    path("dashboard/products/create/", WarehouseProductCreateView.as_view(), name="warehouse_product_create"),
    path(
        "dashboard/warehouse/products/create/",
        RedirectView.as_view(pattern_name="store:warehouse_product_create", permanent=False),
    ),
    path(
        "dashboard/products/<int:pk>/",
        WarehouseProductManageView.as_view(),
        name="warehouse_product_manage",
    ),
    path(
        "dashboard/warehouse/products/<int:pk>/",
        RedirectView.as_view(pattern_name="store:warehouse_product_manage", permanent=False),
    ),
    path(
        "dashboard/products/<int:pk>/edit/",
        RedirectView.as_view(pattern_name="store:warehouse_product_manage", permanent=False),
        name="warehouse_product_edit",
    ),
    path(
        "dashboard/warehouse/products/<int:pk>/edit/",
        RedirectView.as_view(pattern_name="store:warehouse_product_manage", permanent=False),
    ),
    path(
        "dashboard/products/<int:pk>/delete/",
        WarehouseProductDeleteView.as_view(),
        name="warehouse_product_delete",
    ),
    path(
        "dashboard/warehouse/products/<int:pk>/delete/",
        RedirectView.as_view(pattern_name="store:warehouse_product_delete", permanent=False),
    ),
    path(
        "dashboard/categories/create/",
        WarehouseCategoryCreateView.as_view(),
        name="warehouse_category_create",
    ),
    path(
        "dashboard/warehouse/categories/create/",
        RedirectView.as_view(pattern_name="store:warehouse_category_create", permanent=False),
    ),
    path(
        "dashboard/categories/<int:pk>/edit/",
        WarehouseCategoryUpdateView.as_view(),
        name="warehouse_category_edit",
    ),
    path(
        "dashboard/warehouse/categories/<int:pk>/edit/",
        RedirectView.as_view(pattern_name="store:warehouse_category_edit", permanent=False),
    ),
    path(
        "dashboard/categories/<int:pk>/delete/",
        WarehouseCategoryDeleteView.as_view(),
        name="warehouse_category_delete",
    ),
    path(
        "dashboard/warehouse/categories/<int:pk>/delete/",
        RedirectView.as_view(pattern_name="store:warehouse_category_delete", permanent=False),
    ),
    path(
        "dashboard/products/<int:product_pk>/variants/create/",
        WarehouseVariantCreateView.as_view(),
        name="warehouse_variant_create",
    ),
    path(
        "dashboard/warehouse/products/<int:product_pk>/variants/create/",
        RedirectView.as_view(pattern_name="store:warehouse_variant_create", permanent=False),
    ),
    path(
        "dashboard/variants/<int:pk>/edit/",
        WarehouseVariantUpdateView.as_view(),
        name="warehouse_variant_edit",
    ),
    path(
        "dashboard/warehouse/variants/<int:pk>/edit/",
        RedirectView.as_view(pattern_name="store:warehouse_variant_edit", permanent=False),
    ),
    path(
        "dashboard/variants/<int:pk>/delete/",
        WarehouseVariantDeleteView.as_view(),
        name="warehouse_variant_delete",
    ),
    path(
        "dashboard/warehouse/variants/<int:pk>/delete/",
        RedirectView.as_view(pattern_name="store:warehouse_variant_delete", permanent=False),
    ),
    path(
        "dashboard/variants/<int:pk>/stock/",
        WarehouseVariantStockUpdateView.as_view(),
        name="warehouse_variant_stock_update",
    ),
    path(
        "dashboard/warehouse/variants/<int:pk>/stock/",
        RedirectView.as_view(pattern_name="store:warehouse_variant_stock_update", permanent=False),
    ),
    path(
        "dashboard/products/<int:product_pk>/images/create/",
        WarehouseImageCreateView.as_view(),
        name="warehouse_image_create",
    ),
    path(
        "dashboard/warehouse/products/<int:product_pk>/images/create/",
        RedirectView.as_view(pattern_name="store:warehouse_image_create", permanent=False),
    ),
    path(
        "dashboard/images/<int:pk>/delete/",
        WarehouseImageDeleteView.as_view(),
        name="warehouse_image_delete",
    ),
    path(
        "dashboard/warehouse/images/<int:pk>/delete/",
        RedirectView.as_view(pattern_name="store:warehouse_image_delete", permanent=False),
    ),
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/create/", ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/", ProductDetailsView.as_view(), name="product_detail"),
    path("products/<int:pk>/edit/", ProductUpdateView.as_view(), name="product_edit"),
    path("products/<int:pk>/delete/", ProductDeleteView.as_view(), name="product_delete"),
    path("categories/", CategoryListView.as_view(), name="category_list"),
    path("categories/create/", CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/", CategoryDetailView.as_view(), name="category_detail"),
    path("categories/<int:pk>/edit/", CategoryUpdateView.as_view(), name="category_edit"),
    path("categories/<int:pk>/delete/", CategoryDeleteView.as_view(), name="category_delete"),
    # Корзина
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/add/", AddToCartView.as_view(), name="add_to_cart"),
    path("cart/update/", UpdateCartView.as_view(), name="update_cart"),
    path("cart/remove/", RemoveFromCartView.as_view(), name="remove_from_cart"),
    # Юридические страницы
    path("privacy-policy/", PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms-of-service/", TermsOfServiceView.as_view(), name="terms_of_service"),
    path("return-policy/", ReturnPolicyView.as_view(), name="return_policy"),
    path("offer/", OfferView.as_view(), name="offer"),
    # Страницы ошибок (для тестирования)
    path("404/", Error404View.as_view(), name="error_404"),
    path("500/", Error500View.as_view(), name="error_500"),
]
