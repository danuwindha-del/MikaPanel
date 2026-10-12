from django.conf import settings


def brand(request):
    return {"service": settings.SERVICE, "brand": "MikaPanels" if settings.SERVICE == "panel" else "MychaHost",
            "demo_mode": settings.MIKA_PROVISION_MODE == "demo", "payment_mode": settings.TRIPAY_MODE}
