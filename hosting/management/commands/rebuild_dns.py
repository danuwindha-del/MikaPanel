"""Repair DNS publication without creating hosting accounts or touching invoices."""
import fcntl
import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from common.models import AuditEvent
from hosting.dns import publish
from hosting.models import Account
from hosting.validation import domain_name


class Command(BaseCommand):
    help = "Republish existing hosting DNS zones and verify authoritative UDP/TCP SOA"

    def add_arguments(self, parser):
        parser.add_argument("--domain", help="Only an existing hosting domain; omit for all accounts")

    def handle(self, *args, **options):
        if settings.SERVICE != "panel":
            raise CommandError("Run with the panel environment")
        if settings.MIKA_PROVISION_MODE == "system" and os.geteuid() != 0:
            raise CommandError("System DNS publication requires root")
        if settings.MIKA_PROVISION_MODE == "system" and not settings.MIKA_DNS_ENABLED:
            raise CommandError("MIKA_DNS_ENABLED must be 1 in panel.env")
        accounts = Account.objects.order_by("domain")
        if options.get("domain"):
            domain = domain_name(options["domain"])
            accounts = accounts.filter(domain=domain)
            if not accounts.exists():
                raise CommandError("Domain belum memiliki akun/zone di MikaPanels. Pembuatan subdomain tidak membuat zone domain induk.")
        with (settings.DATA_DIR / "provision-worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CommandError("Hentikan mika-provision sebelum menjalankan rebuild_dns; worker sedang memegang lock.")
            failures = 0
            count = 0
            for account in accounts:
                count += 1
                try:
                    publish(account)
                    AuditEvent.objects.create(actor="operator", action="dns.rebuild", target=account.domain)
                    self.stdout.write(f"OK DNS: {account.domain} ({settings.MIKA_PROVISION_MODE})")
                except Exception as exc:
                    failures += 1
                    Account.objects.filter(pk=account.pk).update(dns_state="failed")
                    self.stderr.write(f"FAILED DNS: {account.domain}: {type(exc).__name__}")
                self.stdout.flush(); self.stderr.flush()
            if failures:
                raise CommandError(f"{failures} dari {count} zone gagal; periksa named dan konfigurasi include.")
            self.stdout.write(f"DNS rebuilt: {count} zone. Nameserver A/glue dan firewall provider tetap harus dikonfigurasi di luar panel.")
