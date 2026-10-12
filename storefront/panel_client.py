import requests
from django.conf import settings
from .models import Order


class PanelError(Exception):
    pass


def call(path, payload=None):
    if not settings.MIKA_API_TOKEN:
        raise PanelError("Panel token missing")
    try:
        method = requests.get if payload is None else requests.post
        response = method(settings.MIKA_PANEL_URL + path, json=payload,
                          headers={"Authorization": "Bearer " + settings.MIKA_API_TOKEN}, timeout=(3, 15))
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PanelError("PanelUnavailable") from exc


def fulfill(order):
    if order.status not in {"paid", "active"}:
        raise PanelError("Order is not paid")
    try:
        if not order.panel_account_id:
            data = call("/api/v1/accounts/", {"external_id": order.reference, "customer_id": str(order.user_id),
                "email": order.user.email, "domain": order.domain, "kind": order.kind,
                "plan": order.panel_plan, "days": order.cycle * 30})
        else:
            data = call(f"/api/v1/accounts/{order.reference}/")
        if data.get("external_id") != order.reference or data.get("domain") != order.domain:
            raise PanelError("PanelIdentityMismatch")
        fields = {"panel_account_id": data["id"], "panel_status": data["status"], "provisioning_error": ""}
        if data["status"] == "active":
            fields["status"] = "active"
        Order.objects.filter(pk=order.pk, status__in=["paid", "active"]).update(**fields)
    except (PanelError, KeyError, TypeError):
        Order.objects.filter(pk=order.pk).update(provisioning_error="PanelUnavailable")
        raise PanelError("PanelUnavailable")
