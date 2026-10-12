from django.contrib import admin
from django.conf import settings
from .models import AuditEvent, Ticket, TicketReply

admin.site.site_header = "MikaPanels Operations" if settings.SERVICE == "panel" else "MychaHost Operations"
admin.site.site_title = "Mika Operations"
admin.site.index_title = "Pusat administrasi"


class ReplyInline(admin.TabularInline):
    model = TicketReply
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ["subject", "user", "priority", "status", "created_at"]
    list_filter = ["status", "priority"]
    inlines = [ReplyInline]


@admin.register(AuditEvent)
class AuditAdmin(admin.ModelAdmin):
    list_display = ["actor", "action", "target", "created_at"]
    readonly_fields = ["actor", "action", "target", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
