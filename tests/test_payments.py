import hashlib
import hmac
import json
from unittest.mock import Mock, patch
import pytest
from django.utils import timezone
from storefront.gateway import GatewayError, create_payment
from storefront.models import Order, PaymentEvent
from storefront.panel_client import PanelError, fulfill


def callback(client, settings, order, **overrides):
    data = {"reference": order.payment_reference, "merchant_ref": order.reference, "status": "PAID",
            "total_amount": order.payment_total, "is_closed_payment": 1, **overrides}
    raw = json.dumps(data, separators=(",", ":")).encode()
    signature = hmac.new(settings.TRIPAY_PRIVATE_KEY.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/payments/tripay/callback/", raw, content_type="application/json",
                       HTTP_X_CALLBACK_EVENT="payment_status", HTTP_X_CALLBACK_SIGNATURE=signature)


@pytest.mark.django_db
def test_signed_payment_is_durable_and_duplicate_is_idempotent(client, shop, order):
    assert callback(client, shop, order).status_code == 200
    order.refresh_from_db()
    assert order.status == "paid" and order.paid_at is not None
    assert callback(client, shop, order).status_code == 200
    assert PaymentEvent.objects.count() == 1


@pytest.mark.django_db
def test_unsigned_payment_rejected(client, shop, order):
    response = client.post("/payments/tripay/callback/", b'{}', content_type="application/json")
    assert response.status_code == 403
    order.refresh_from_db()
    assert order.status == "pending"
    assert PaymentEvent.objects.count() == 0


@pytest.mark.django_db
def test_reconcile_gateway_reference_checks_amount(shop, order):
    from django.core.management import call_command
    from django.core.management.base import CommandError
    order.status = "review"
    order.save()
    response = Mock()
    response.json.return_value = {"success": True, "data": {"merchant_ref": order.reference, "reference": "T-123", "amount": 1, "fee_customer": 0, "status": "PAID"}}
    with patch("storefront.management.commands.reconcile_payment.requests.get", return_value=response), pytest.raises(CommandError):
        call_command("reconcile_payment", order.reference, "T-123")
    order.refresh_from_db()
    assert order.status == "review"
    response.json.return_value["data"].update(amount=20000, fee_customer=1000)
    with patch("storefront.management.commands.reconcile_payment.requests.get", return_value=response):
        call_command("reconcile_payment", order.reference, "T-123")
    order.refresh_from_db()
    assert order.status == "paid" and order.payment_total == 20000


@pytest.mark.django_db
@pytest.mark.parametrize("override", [{"total_amount": 1}, {"merchant_ref": "MH-other"}, {"reference": "unknown"}, {"is_closed_payment": 0}])
def test_callback_invoice_binding(client, shop, order, override):
    assert callback(client, shop, order, **override).status_code == 400
    order.refresh_from_db()
    assert order.status == "pending"


@pytest.mark.django_db
def test_old_expiry_callback_does_not_downgrade_paid(client, shop, order):
    callback(client, shop, order)
    assert callback(client, shop, order, status="EXPIRED").status_code == 200
    order.refresh_from_db()
    assert order.status == "paid"


@pytest.mark.django_db
def test_refund_requires_review(client, shop, order):
    callback(client, shop, order)
    callback(client, shop, order, status="REFUND")
    order.refresh_from_db()
    assert order.status == "review"
    callback(client, shop, order, status="PAID", late_retry=True)
    order.refresh_from_db()
    assert order.status == "review"


@pytest.mark.django_db
def test_gateway_signature_and_verified_tls(shop, order):
    response = Mock()
    response.json.return_value = {"success": True, "data": {"reference": "T-123", "checkout_url": "https://tripay.co.id/checkout/T-123"}}
    with patch("storefront.gateway.requests.post", return_value=response) as post:
        create_payment(order, "BRIVA")
    args, kwargs = post.call_args
    assert args[0] == "https://tripay.co.id/api-sandbox/transaction/create"
    payload = kwargs["data"]
    expected = hmac.new(shop.TRIPAY_PRIVATE_KEY.encode(), f"TTEST{order.reference}19000".encode(), hashlib.sha256).hexdigest()
    assert payload["signature"] == expected
    assert kwargs.get("verify", True) is True
    assert payload["order_items[0][price]"] == 19000


@pytest.mark.django_db
def test_gateway_rejects_redirect_to_untrusted_host(shop, order):
    response = Mock()
    response.json.return_value = {"success": True, "data": {"reference": "T", "checkout_url": "https://evil.example/"}}
    with patch("storefront.gateway.requests.post", return_value=response), pytest.raises(GatewayError):
        create_payment(order, "BRIVA")


@pytest.mark.django_db
def test_no_charge_when_keys_missing(client, shop, order, user):
    shop.TRIPAY_API_KEY = ""
    order.status = "unpaid"
    order.save()
    client.force_login(user)
    with patch("storefront.views.create_payment") as gateway:
        assert client.post(f"/orders/{order.pk}/pay/", {"method": "BRIVA"}).status_code == 302
        gateway.assert_not_called()


@pytest.mark.django_db
def test_double_click_does_not_create_second_charge(client, shop, order, user):
    order.status = "unpaid"
    order.payment_reference = None
    order.save()
    client.force_login(user)
    data = {"reference": "T-second", "checkout_url": "https://tripay.co.id/checkout/T-second", "amount": 20000, "fee_customer": 1000}
    with patch("storefront.views.create_payment", return_value=data) as gateway:
        first = client.post(f"/orders/{order.pk}/pay/", {"method": "BRIVA"})
        assert first.status_code == 302 and first.url == data["checkout_url"]
        client.post(f"/orders/{order.pk}/pay/", {"method": "BRIVA"})
        assert gateway.call_count == 1
    order.refresh_from_db()
    assert order.status == "pending" and order.payment_total == 20000


@pytest.mark.django_db
def test_ambiguous_gateway_timeout_requires_review(client, shop, order, user):
    order.status = "unpaid"
    order.save()
    client.force_login(user)
    with patch("storefront.views.create_payment", side_effect=GatewayError("Gateway timeout")) as gateway:
        client.post(f"/orders/{order.pk}/pay/", {"method": "BRIVA"})
        client.post(f"/orders/{order.pk}/pay/", {"method": "BRIVA"})
        assert gateway.call_count == 1
    order.refresh_from_db()
    assert order.status == "review"


@pytest.mark.django_db
def test_panel_outage_does_not_lose_payment(shop, order):
    order.status = "paid"
    order.save()
    with patch("storefront.panel_client.call", side_effect=PanelError("offline")), pytest.raises(PanelError):
        fulfill(order)
    order.refresh_from_db()
    assert order.status == "paid" and order.provisioning_error
    with patch("storefront.panel_client.call", return_value={"id": "id-123", "external_id": order.reference, "domain": order.domain, "status": "active"}):
        fulfill(order)
    order.refresh_from_db()
    assert order.status == "active" and order.provisioning_error == ""


@pytest.mark.django_db
def test_unpaid_order_cannot_provision(shop, order):
    with patch("storefront.panel_client.call") as call, pytest.raises(PanelError):
        fulfill(order)
    call.assert_not_called()
