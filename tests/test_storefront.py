from datetime import timedelta
import pytest
from django.test import Client
from django.utils import timezone
from storefront.models import Coupon, Order
from common.models import Ticket, TicketReply


@pytest.mark.django_db
def test_catalog_and_checkout_pricing(client, shop, product, user):
    response = client.get("/")
    assert response.status_code == 200 and b"MychaHost" in response.content
    client.force_login(user)
    Coupon.objects.create(code="LAUNCH10", percent=10, expires_at=timezone.now() + timedelta(days=1))
    response = client.post("/checkout/launch/", {"domain": "store.example.test", "kind": "php", "cycle": 3, "coupon": "LAUNCH10", "agree": "on", "customer_phone": "081234567890"})
    assert response.status_code == 302
    order = Order.objects.get()
    assert order.amount == 51300 and order.discount == 5700 and order.status == "unpaid"
    # Client-provided amount cannot override the price.
    assert client.post("/checkout/launch/", {"domain": "next.example.test", "kind": "static", "cycle": 1, "amount": 1, "agree": "on", "customer_phone": "081234567890"}).status_code == 302
    assert Order.objects.get(domain="next.example.test").amount == 19000


@pytest.mark.django_db
def test_invalid_coupon_and_duplicate_domain(client, shop, product, user, order):
    client.force_login(user)
    data = {"domain": "valid.example.test", "kind": "php", "cycle": 1, "coupon": "INVALID", "agree": "on", "customer_phone": "081234567890"}
    assert client.post("/checkout/launch/", data).status_code == 200
    assert Order.objects.count() == 1
    data.update(domain=order.domain, coupon="")
    assert client.post("/checkout/launch/", data).status_code == 200
    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_customer_invoice_access(client, shop, order, other):
    client.force_login(other)
    assert client.get(f"/orders/{order.pk}/").status_code == 404
    assert client.post(f"/orders/{order.pk}/sync/").status_code == 404
    assert client.post(f"/orders/{order.pk}/pay/", {"method": "BRIVA"}).status_code == 404


@pytest.mark.django_db
def test_csrf_enforced_for_customer_actions(shop, user, order):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post(f"/orders/{order.pk}/pay/", {"method": "BRIVA"}).status_code == 403


@pytest.mark.django_db
def test_ticket_access_and_reply(client, shop, user, other):
    client.force_login(user)
    assert client.post("/tickets/", {"subject": "DNS help", "priority": "normal", "body": "Help please"}).status_code == 302
    ticket = Ticket.objects.get()
    assert TicketReply.objects.get().body == "Help please"
    client.force_login(other)
    assert client.get(f"/tickets/{ticket.pk}/").status_code == 404
    assert client.post(f"/tickets/{ticket.pk}/", {"body": "intrusion"}).status_code == 404
    assert ticket.replies.count() == 1


@pytest.mark.django_db
def test_bruteforce_limit(client, shop, user):
    for _ in range(10):
        assert client.post("/login/", {"username": user.username, "password": "wrong"}).status_code == 200
    assert client.post("/login/", {"username": user.username, "password": "wrong"}).status_code == 429


@pytest.mark.django_db
def test_login_redirect_not_external(client, shop, user):
    response = client.post("/login/", {"username": user.username, "password": "Long-test-password-2048!", "next": "https://evil.example/"})
    assert response.status_code == 302 and response.url == "/dashboard/"


@pytest.mark.django_db
def test_seed_repeatable_preserves_changes(shop):
    from django.core.management import call_command
    from storefront.models import Product
    call_command("seed_catalog")
    product = Product.objects.get(slug="launch")
    product.price = 25000
    product.save()
    call_command("seed_catalog")
    assert Product.objects.count() == 3 and Product.objects.get(slug="launch").price == 25000
