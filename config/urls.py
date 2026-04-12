from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from store.views.views_legal import Error404View, Error500View

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("store.urls", namespace="main_page")),
    path("", include("orders.urls", namespace="orders")),
    path("users/", include("users.urls", namespace="users")),
]

# Custom error handlers
handler404 = 'store.views.views_legal.error_404_view'
handler500 = 'store.views.views_legal.error_500_view'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
