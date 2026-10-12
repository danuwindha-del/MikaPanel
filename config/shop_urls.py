from django.contrib import admin
from django.urls import path
from common import views as common
from storefront import views

urlpatterns = [
    path("", views.home), path("health/", common.health), path("login/", common.signin),
    path("register/", common.register), path("logout/", common.signout), path("admin/", admin.site.urls),
    path("dashboard/", views.dashboard), path("terms/", views.terms),
    path("checkout/<slug:slug>/", views.checkout, name="checkout"),
    path("orders/<uuid:pk>/", views.order_detail, name="order_detail"),
    path("orders/<uuid:pk>/pay/", views.pay, name="pay"),
    path("orders/<uuid:pk>/sync/", views.sync, name="sync"),
    path("orders/<uuid:pk>/panel/", views.panel_login, name="panel_login"),
    path("payments/tripay/callback/", views.tripay_callback),
    path("tickets/", common.tickets), path("tickets/<int:pk>/", common.ticket_detail, name="ticket_detail"),
]
