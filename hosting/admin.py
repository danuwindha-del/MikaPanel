from django.conf import settings
from django.contrib import admin
from .models import Account, Plan, ProvisionJob

if settings.SERVICE == "panel":
    @admin.register(Plan)
    class PlanAdmin(admin.ModelAdmin):
        list_display = ["name", "slug", "disk_mb", "memory_mb", "php_workers", "active"]

    @admin.register(Account)
    class AccountAdmin(admin.ModelAdmin):
        list_display = ["domain", "owner", "plan", "kind", "status", "expires_at"]
        list_filter = ["status", "kind", "plan"]
        search_fields = ["domain", "external_id"]
        readonly_fields = ["id", "external_id", "domain", "owner", "kind", "status", "created_at"]

        def has_add_permission(self, request):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    @admin.register(ProvisionJob)
    class JobAdmin(admin.ModelAdmin):
        list_display = ["account", "action", "state", "attempts", "updated_at"]
        readonly_fields = ["account", "action", "state", "attempts", "error", "created_at", "updated_at"]

        def has_add_permission(self, request):
            return False

        def has_delete_permission(self, request, obj=None):
            return False
