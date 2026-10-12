"""Manual recovery after ambiguous creation timeout; verifies Tripay's API before changing state."""
import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone
from common.models import AuditEvent
from storefront.gateway import base_url, configured
from storefront.models import Order


class Command(BaseCommand):
    help = "Reconcile a review invoice with its gateway reference from the Tripay dashboard"

    def add_arguments(self, parser):
        parser.add_argument("invoice")
        parser.add_argument("gateway_reference")

    def handle(self, *args, **options):
        if settings.SERVICE != "shop" or not configured():
            raise CommandError("Shop service and Tripay credentials required")
        if not options["invoice"].startswith("MH-"):
            raise CommandError("Invalid invoice")
        try:
            order = Order.objects.get(id=options["invoice"][3:])
            response = requests.get(base_url() + "/transaction/detail", params={"reference": options["gateway_reference"]},
                                    headers={"Authorization": "Bearer " + settings.TRIPAY_API_KEY}, timeout=(5, 25))
            response.raise_for_status()
            data = response.json()["data"]
            if data["merchant_ref"] != order.reference or data["reference"] != options["gateway_reference"]:
                raise CommandError("Gateway invoice mismatch")
            fee = int(data.get("fee_customer", 0))
            total = int(data["amount"])
            if total != order.amount + fee or fee < 0:
                raise CommandError("Gateway amount mismatch")
            if data["status"] not in {"PAID", "UNPAID", "EXPIRED", "FAILED"}:
                raise CommandError("Unsupported gateway state; manual refund review required")
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order.pk)
                if order.payment_events.filter(gateway_status="REFUND").exists():
                    raise CommandError("Refund already observed; do not auto-reactivate")
                if order.status not in {"review", "unpaid", "pending"}:
                    raise CommandError("Invoice is not eligible for reconciliation")
                order.payment_reference = data["reference"]
                order.payment_total = total
                order.payment_fee = fee
                order.status = {"PAID": "paid", "UNPAID": "pending", "EXPIRED": "expired", "FAILED": "failed"}[data["status"]]
                if order.status == "paid":
                    order.paid_at = timezone.now()
                # Never trust/reuse a checkout URL obtained through operator input.
                order.save(update_fields=["payment_reference", "payment_total", "payment_fee", "status", "paid_at"])
                AuditEvent.objects.create(actor="operator-cli", action="payment.reconcile", target=order.reference)
        except (requests.RequestException, ValueError, KeyError, TypeError, ValidationError, IntegrityError, Order.DoesNotExist) as exc:
            raise CommandError("Gateway verification failed; invoice unchanged") from exc
        self.stdout.write(f"Verified {order.reference}: {order.status}")
