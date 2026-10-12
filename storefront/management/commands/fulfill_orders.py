import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from storefront.models import Order
from storefront.panel_client import PanelError, fulfill


class Command(BaseCommand):
    help = "Retry paid orders and refresh panel states; never create payments"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if settings.SERVICE != "shop":
            raise CommandError("Run with MIKA_SERVICE=shop")
        while True:
            for order in Order.objects.select_related("user", "product").filter(status__in=["paid", "active"]).iterator():
                try:
                    fulfill(order)
                    self.stdout.write(f"OK {order.reference}")
                except PanelError:
                    self.stderr.write(f"WAIT {order.reference}: panel unavailable")
            if options["once"]:
                break
            time.sleep(30)
