from django.conf import settings
from django.contrib import admin
from .models import Account, Plan, ProvisionJob
from .forms import ManualAccountForm
from .services import save_manual_account

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
            return super().has_add_permission(request)

        def get_fields(self, request, obj=None):
            if obj is None:
                return ["domain", "owner", "plan", "kind", "days"]
            return super().get_fields(request, obj)

        def get_readonly_fields(self, request, obj=None):
            return self.readonly_fields if obj is not None else []

        def get_form(self, request, obj=None, **kwargs):
            if obj is None:
                kwargs["form"] = ManualAccountForm
            return super().get_form(request, obj, **kwargs)

        def get_changeform_initial_data(self, request):
            return {**super().get_changeform_initial_data(request), "owner": request.user.pk}

        def save_model(self, request, obj, form, change):
            if change:
                super().save_model(request, obj, form, change)
            else:
                save_manual_account(obj, actor=request.user, days=form.cleaned_data["days"])
                self.message_user(request, "Hosting dibuat tanpa pembayaran dan diantrekan. Status Aktif diberikan setelah worker berhasil menyiapkan website.")

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
