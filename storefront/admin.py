from django.conf import settings
from django.contrib import admin
from .models import Coupon, Order, PaymentEvent, Product

if settings.SERVICE == "shop":
    @admin.register(Product)
    class ProductAdmin(admin.ModelAdmin):
        list_display = ["name", "price", "panel_plan", "active", "featured"]

    @admin.register(Coupon)
    class CouponAdmin(admin.ModelAdmin):
        list_display = ["code", "percent", "expires_at", "active"]

    @admin.register(Order)
    class OrderAdmin(admin.ModelAdmin):
        list_display = ["reference", "user", "domain", "amount", "status", "panel_status", "created_at"]
        list_filter = ["status", "panel_status"]
        search_fields = ["domain", "user__email", "payment_reference"]
        readonly_fields = [f.name for f in Order._meta.fields]

        def has_add_permission(self, request):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    @admin.register(PaymentEvent)
    class EventAdmin(admin.ModelAdmin):
        list_display = ["order", "gateway_status", "created_at"]
        readonly_fields = ["order", "digest", "gateway_status", "created_at"]

        def has_add_permission(self, request):
            return False

        def has_delete_permission(self, request, obj=None):
            return False
