from django.core.management.base import BaseCommand
from django.conf import settings
from hosting.models import Account, ProvisionJob
from hosting.dns import ensure_records


class Command(BaseCommand):
    help = "Initialize DNS and refresh existing website configurations after upgrading"

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true")

    def handle(self, *args, **options):
        if settings.SERVICE != "panel":
            return
        for account in Account.objects.all():
            ensure_records(account)
            if options["refresh"] and account.status in {"active", "suspended"}:
                for action in ["refresh", "dns"]:
                    if not account.jobs.filter(action=action, state__in=["pending", "running"]).exists():
                        ProvisionJob.objects.create(account=account, action=action)
        self.stdout.write("Hosting feature data initialized")
