import time
import subprocess
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone
from common.models import AuditEvent
from hosting.models import Account, ProvisionJob, ManagedDatabase
from hosting.provisioner import process


class Command(BaseCommand):
    help = "Process hosting queue; --once for local checks, continuous under systemd"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--recover", action="store_true", help="Recover interrupted jobs after ensuring no worker is running")

    def handle(self, *args, **options):
        if settings.SERVICE != "panel":
            raise CommandError("Run with MIKA_SERVICE=panel")
        import fcntl
        lockfile = settings.DATA_DIR / "provision-worker.lock"
        with lockfile.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CommandError("Another worker is running")
            if options["recover"]:
                ProvisionJob.objects.filter(state="running").update(state="pending")
            while True:
                from hosting.telemetry import collect_all
                try:
                    collect_all()
                except (OSError, ValueError):
                    self.stderr.write("Telemetry not available on this platform")
                # Expired accounts are suspended by the worker, including after downtime.
                for account in Account.objects.filter(status="active", expires_at__lte=timezone.now()):
                    if not account.jobs.filter(state__in=["pending", "running"]).exists():
                        ProvisionJob.objects.create(account=account, action="suspend")
                job = ProvisionJob.objects.select_related("account__plan").filter(state="pending").order_by("created_at").first()
                if job:
                    if not ProvisionJob.objects.filter(pk=job.pk, state="pending").update(state="running", attempts=F("attempts") + 1, updated_at=timezone.now()):
                        continue
                    try:
                        if job.action == "dns":
                            from hosting.dns import publish
                            publish(job.account)
                        elif job.action.startswith("db_"):
                            from hosting.databases import provision
                            database = ManagedDatabase.objects.get(pk=job.resource_id, account=job.account)
                            provision(database, job.action)
                        else:
                            state = process(job.account, job.action)
                            Account.objects.filter(pk=job.account_id).update(status=state)
                        ProvisionJob.objects.filter(pk=job.pk).update(state="done", error="", updated_at=timezone.now())
                        AuditEvent.objects.create(actor="worker", action=f"hosting.{job.action}", target=job.account.domain)
                        from common.models import Notification
                        Notification.objects.create(user=job.account.owner, title=f"{job.account.domain}: pekerjaan selesai",
                            body=f"Tindakan {job.action} selesai diproses.", link=f"/accounts/{job.account_id}/")
                        self.stdout.write(f"OK {job.action}: {job.account.domain} ({settings.MIKA_PROVISION_MODE})")
                    except Exception as exc:
                        # Do not store command output or env values; log only error class.
                        ProvisionJob.objects.filter(pk=job.pk).update(state="failed", error=type(exc).__name__, updated_at=timezone.now())
                        if job.action == "create":
                            Account.objects.filter(pk=job.account_id).update(status="failed")
                        if job.action == "dns":
                            Account.objects.filter(pk=job.account_id).update(dns_state="failed")
                        if job.action.startswith("db_"):
                            ManagedDatabase.objects.filter(pk=job.resource_id, account=job.account).update(state="failed")
                        from common.models import Notification
                        Notification.objects.create(user=job.account.owner, title=f"{job.account.domain}: pekerjaan gagal",
                            body=f"Tindakan {job.action} gagal ({type(exc).__name__}). Hubungi admin untuk pemeriksaan layanan.", link=f"/accounts/{job.account_id}/")
                        self.stderr.write(f"FAILED {job.account.domain}: {type(exc).__name__}")
                        if isinstance(exc, subprocess.CalledProcessError) and not job.action.startswith("db_"):
                            self.stderr.write(f"Command {exc.cmd[0]} exited {exc.returncode}: {(exc.stderr or '')[-2000:]}")
                        if options["once"]:
                            raise CommandError("Provisioning failed; inspect service prerequisites") from exc
                elif options["once"]:
                    break
                else:
                    time.sleep(3)
