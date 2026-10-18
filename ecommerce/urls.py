from django.contrib import admin
from django.urls import path, include
from shop import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.product_list, name="home"),
    path("", include("shop.urls")),
]
