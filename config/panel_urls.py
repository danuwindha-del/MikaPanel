from django.contrib import admin
from django.urls import path
from common import views as common
from hosting import api, views
from hosting import resource_views as resources

urlpatterns = [
    path("", views.home), path("health/", common.health), path("login/", common.signin),
    path("logout/", common.signout), path("dashboard/", views.dashboard), path("admin/", admin.site.urls),
    path("accounts/create/", views.create_account, name="create_account"),
    path("tools/<str:tool>/", resources.tools_home, name="tools_home"),
    path("accounts/<uuid:pk>/files/manage/", views.file_manager, name="file_manager"),
    path("accounts/<uuid:pk>/files/action/", views.file_action, name="file_action"),
    path("accounts/<uuid:pk>/files/download/", views.file_download, name="file_download"),
    path("accounts/<uuid:pk>/dns/", resources.dns_records, name="dns_records"),
    path("accounts/<uuid:pk>/dns/<int:record_id>/delete/", resources.dns_delete, name="dns_delete"),
    path("accounts/<uuid:pk>/dns/sync/", resources.dns_sync, name="dns_sync"),
    path("accounts/<uuid:pk>/dns/export/", resources.dns_export, name="dns_export"),
    path("accounts/<uuid:pk>/databases/", resources.databases, name="databases"),
    path("accounts/<uuid:pk>/databases/<uuid:db_id>/action/", resources.database_action, name="database_action"),
    path("accounts/<uuid:pk>/ssl/", resources.ssl_status, name="ssl_status"),
    path("accounts/<uuid:pk>/ssl/request/", resources.ssl_request, name="ssl_request"),
    path("accounts/<uuid:pk>/security/", resources.security, name="security"),
    path("accounts/<uuid:pk>/security/<int:rule_id>/delete/", resources.unblock, name="unblock"),
    path("accounts/<uuid:pk>/statistics/", resources.statistics, name="statistics"),
    path("notifications/", common.notifications), path("profile/", common.profile),
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
