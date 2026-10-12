from django.conf import settings


def brand(request):
    unread = 0
    if request.user.is_authenticated:
        unread = request.user.notifications.filter(is_read=False).count()
    return {"service": settings.SERVICE, "brand": "MikaPanels" if settings.SERVICE == "panel" else "MychaHost",
            "demo_mode": settings.MIKA_PROVISION_MODE == "demo", "payment_mode": settings.TRIPAY_MODE,
            "unread_notifications": unread}
