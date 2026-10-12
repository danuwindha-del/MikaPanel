from django.contrib import admin
from django.urls import path
from common import views as common
from hosting import api, views

urlpatterns = [
    path("", views.home), path("health/", common.health), path("login/", common.signin),
    path("logout/", common.signout), path("dashboard/", views.dashboard), path("admin/", admin.site.urls),
    path("accounts/create/", views.create_account, name="create_account"),
    path("accounts/<uuid:pk>/", views.account_detail, name="account_detail"),
    path("accounts/<uuid:pk>/files/", views.file_save, name="file_save"),
    path("accounts/<uuid:pk>/backup/", views.backup, name="backup"),
    path("accounts/<uuid:pk>/action/", views.account_action, name="account_action"),
    path("sso/", views.sso),
    path("tickets/", common.tickets), path("tickets/<int:pk>/", common.ticket_detail, name="ticket_detail"),
    path("api/v1/accounts/", api.provision),
    path("api/v1/accounts/<str:external_id>/", api.account_status),
    path("api/v1/accounts/<str:external_id>/sso/", api.sso_token),
]
