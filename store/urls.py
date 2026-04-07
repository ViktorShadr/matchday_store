from django.urls import path

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
from store.views.views_dashboard import (
    DashboardHomeView,
    WarehouseDashboardView,
    WarehouseProductCreateView,
    WarehouseProductUpdateView,
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
    path("dashboard/warehouse/", WarehouseDashboardView.as_view(), name="warehouse_dashboard"),
    path("dashboard/warehouse/products/create/", WarehouseProductCreateView.as_view(), name="warehouse_product_create"),
    path(
        "dashboard/warehouse/products/<int:pk>/",
        WarehouseProductManageView.as_view(),
        name="warehouse_product_manage",
    ),
    path(
        "dashboard/warehouse/products/<int:pk>/edit/",
        WarehouseProductUpdateView.as_view(),
        name="warehouse_product_edit",
    ),
    path(
        "dashboard/warehouse/products/<int:pk>/delete/",
        WarehouseProductDeleteView.as_view(),
        name="warehouse_product_delete",
    ),
    path(
        "dashboard/warehouse/categories/create/",
        WarehouseCategoryCreateView.as_view(),
        name="warehouse_category_create",
    ),
    path(
        "dashboard/warehouse/categories/<int:pk>/edit/",
        WarehouseCategoryUpdateView.as_view(),
        name="warehouse_category_edit",
    ),
    path(
        "dashboard/warehouse/categories/<int:pk>/delete/",
        WarehouseCategoryDeleteView.as_view(),
        name="warehouse_category_delete",
    ),
    path(
        "dashboard/warehouse/products/<int:product_pk>/variants/create/",
        WarehouseVariantCreateView.as_view(),
        name="warehouse_variant_create",
    ),
    path(
        "dashboard/warehouse/variants/<int:pk>/edit/",
        WarehouseVariantUpdateView.as_view(),
        name="warehouse_variant_edit",
    ),
    path(
        "dashboard/warehouse/variants/<int:pk>/delete/",
        WarehouseVariantDeleteView.as_view(),
        name="warehouse_variant_delete",
    ),
    path(
        "dashboard/warehouse/variants/<int:pk>/stock/",
        WarehouseVariantStockUpdateView.as_view(),
        name="warehouse_variant_stock_update",
    ),
    path(
        "dashboard/warehouse/products/<int:product_pk>/images/create/",
        WarehouseImageCreateView.as_view(),
        name="warehouse_image_create",
    ),
    path(
        "dashboard/warehouse/images/<int:pk>/delete/",
        WarehouseImageDeleteView.as_view(),
        name="warehouse_image_delete",
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
]
