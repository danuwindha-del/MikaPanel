from datetime import timedelta
import uuid
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from common.models import AuditEvent
from . import dns, files
from .databases import encrypt_password
from .forms import DNSForm, DatabaseForm, DatabasePasswordForm, SecurityForm, BlockIPForm
from .models import Account, AccountUsage, DNSRecord, ManagedDatabase, ProvisionJob, BlockedIP, MetricSample
from .telemetry import chart


def owned(request):
    qs = Account.objects.select_related("plan", "owner")
    return qs if request.user.is_staff else qs.filter(owner=request.user)


@login_required
def tools_home(request, tool):
    allowed = {"files": "Pengelola File", "databases": "Database", "dns": "DNS", "ssl": "SSL", "security": "Keamanan", "statistics": "Statistik"}
    title = allowed.get(tool)
    if not title:
        from django.http import Http404
        raise Http404
    return render(request, "panel/tools.html", {"accounts": owned(request), "tool": tool, "title": title})


@login_required
def dns_records(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    if request.GET.get("edit") and not request.GET["edit"].isdigit():
        from django.http import Http404
        raise Http404
    record = get_object_or_404(DNSRecord, pk=request.GET["edit"], account=account) if request.GET.get("edit") else None
    form = DNSForm(request.POST or None, account=account, instance=record)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if not record and account.dns_records.count() >= 100:
                    form.add_error(None, "Maksimal 100 record per domain.")
                else:
                    saved = form.save()
                    dns.enqueue_sync(account)
                    AuditEvent.objects.create(actor=request.user.username, action="dns.save", target=account.domain)
                    messages.success(request, "Record disimpan. Publikasi DNS diproses melalui antrean.")
                    return redirect("dns_records", pk=pk)
        except IntegrityError:
            form.add_error(None, "Record sudah ada atau perubahan bersamaan terdeteksi.")
    return render(request, "panel/dns.html", {"account": account, "records": account.dns_records.all(), "form": form, "editing": record,
        "nameservers": [settings.MIKA_DNS_PRIMARY, settings.MIKA_DNS_SECONDARY], "dns_enabled": settings.MIKA_DNS_ENABLED})


@login_required
@require_POST
def dns_delete(request, pk, record_id):
    account = get_object_or_404(owned(request), pk=pk)
    with transaction.atomic():
        get_object_or_404(DNSRecord, pk=record_id, account=account).delete()
        dns.enqueue_sync(account)
        AuditEvent.objects.create(actor=request.user.username, action="dns.delete", target=account.domain)
    messages.success(request, "Record dihapus dan perubahan diantrekan.")
    return redirect("dns_records", pk=pk)


@login_required
@require_POST
def dns_sync(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    dns.enqueue_sync(account)
    messages.success(request, "Publikasi ulang DNS diantrekan.")
    return redirect("dns_records", pk=pk)


@login_required
def dns_export(request, pk):
    from django.http import HttpResponse
    account = get_object_or_404(owned(request), pk=pk)
    response = HttpResponse(dns.render_zone(account), content_type="text/plain")
    response["Content-Disposition"] = f'attachment; filename="{account.domain}.zone"'
    return response


@login_required
def databases(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    form = DatabaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if account.status != "active":
            form.add_error(None, "Hosting harus aktif sebelum membuat database.")
        elif not settings.MIKA_MYSQL_ENABLED and settings.MIKA_PROVISION_MODE == "system":
            form.add_error(None, "MariaDB belum diaktifkan pada VPS. Hubungi admin.")
        else:
            try:
                with transaction.atomic():
                    claimed = Account.objects.filter(pk=pk, database_count__lt=account.plan.database_limit).update(database_count=F("database_count") + 1)
                    if not claimed:
                        form.add_error(None, "Batas database paket telah tercapai.")
                    else:
                        existing = account.managed_databases.filter(label=form.cleaned_data["label"]).first()
                        if existing and existing.state != "deleted":
                            raise ValueError("Nama database sudah digunakan.")
                        database = existing or ManagedDatabase(account=account, label=form.cleaned_data["label"])
                        database.database_name = "mika_" + account.id.hex[:12] + "_" + database.label
                        database.username = "mu" + database.id.hex[:16]
                        database.password_ciphertext = encrypt_password(form.cleaned_data["password"])
                        database.state = "pending"
                        database.save()
                        ProvisionJob.objects.create(account=account, action="db_create", resource_id=database.id)
                        AuditEvent.objects.create(actor=request.user.username, action="database.create", target=account.domain)
                        messages.success(request, "Database diantrekan. Password disimpan terenkripsi dan tidak ditampilkan kembali.")
                        return redirect("databases", pk=pk)
            except (ValueError, IntegrityError) as exc:
                form.add_error(None, str(exc) if isinstance(exc, ValueError) else "Nama database tidak tersedia.")
    account.refresh_from_db()
    return render(request, "panel/databases.html", {"account": account, "databases": account.managed_databases.exclude(state="deleted"), "form": form})


@login_required
@require_POST
def database_action(request, pk, db_id):
    account = get_object_or_404(owned(request), pk=pk)
    database = get_object_or_404(ManagedDatabase, account=account, pk=db_id)
    action = request.POST.get("action")
    with transaction.atomic():
        if account.jobs.filter(resource_id=database.id, state__in=["pending", "running"]).exists():
            messages.error(request, "Masih ada pekerjaan database berjalan.")
        elif action == "retry" and database.state == "failed":
            previous = account.jobs.filter(resource_id=database.id).order_by("-created_at").first()
            next_action = "db_delete" if previous and previous.action == "db_delete" else "db_create"
            database.state = "deleting" if next_action == "db_delete" else "pending"
            database.save(update_fields=["state"])
            ProvisionJob.objects.create(account=account, action=next_action, resource_id=database.id)
            messages.success(request, "Pekerjaan database diantrekan kembali.")
        elif action == "delete" and database.state != "deleted":
            database.state = "deleting"
            database.save(update_fields=["state"])
            ProvisionJob.objects.create(account=account, action="db_delete", resource_id=database.id)
            AuditEvent.objects.create(actor=request.user.username, action="database.delete", target=account.domain)
            messages.success(request, "Penghapusan database diantrekan.")
        elif action == "password" and database.state in {"active", "demo"}:
            form = DatabasePasswordForm(request.POST)
            if form.is_valid():
                database.password_ciphertext = encrypt_password(form.cleaned_data["password"])
                database.state = "updating"
                database.save(update_fields=["password_ciphertext", "state"])
                ProvisionJob.objects.create(account=account, action="db_rotate", resource_id=database.id)
                messages.success(request, "Perubahan password diantrekan.")
            else:
                messages.error(request, "Password minimal 12 karakter, tidak umum, dan bukan hanya angka.")
    return redirect("databases", pk=pk)


@login_required
def ssl_status(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    return render(request, "panel/ssl.html", {"account": account, "jobs": account.jobs.filter(action="ssl").order_by("-created_at")[:10],
        "server_ip": settings.MIKA_SERVER_IP})


@login_required
@require_POST
def ssl_request(request, pk):
    account = get_object_or_404(owned(request), pk=pk, status="active")
    if settings.MIKA_PROVISION_MODE == "demo":
        messages.error(request, "SSL memerlukan VPS dan DNS publik; tidak diterbitkan dalam mode demo.")
    elif not account.jobs.filter(state__in=["pending", "running"], action="ssl").exists():
        ProvisionJob.objects.create(account=account, action="ssl")
        AuditEvent.objects.create(actor=request.user.username, action="ssl.request", target=account.domain)
        messages.success(request, "Permintaan SSL diantrekan. Domain utama dan www harus mengarah ke VPS.")
    return redirect("ssl_status", pk=pk)


@login_required
def security(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    form = SecurityForm(request.POST or None, instance=account)
    block_form = BlockIPForm(request.POST if request.POST.get("action") == "block" else None, account=account)
    if request.method == "POST":
        if account.status not in {"active", "suspended"}:
            messages.error(request, "Hosting belum siap untuk menerapkan pengaturan keamanan.")
            return redirect("security", pk=pk)
        try:
            with transaction.atomic():
                if request.POST.get("action") == "settings" and form.is_valid():
                    form.save()
                elif request.POST.get("action") == "block" and block_form.is_valid():
                    if account.blocked_ips.count() >= 100:
                        raise ValueError("Maksimal 100 aturan IP.")
                    block_form.save()
                else:
                    raise ValueError("Pengaturan belum valid.")
                if not account.jobs.filter(action="refresh", state="pending").exists():
                    ProvisionJob.objects.create(account=account, action="refresh")
                AuditEvent.objects.create(actor=request.user.username, action="security.update", target=account.domain)
                messages.success(request, "Pengaturan keamanan disimpan dan penerapan diantrekan.")
                return redirect("security", pk=pk)
        except (ValueError, IntegrityError) as exc:
            messages.error(request, str(exc) if isinstance(exc, ValueError) else "Aturan IP sudah ada.")
    return render(request, "panel/security.html", {"account": account, "form": form, "block_form": block_form,
        "events": AuditEvent.objects.filter(target=account.domain).order_by("-created_at")[:20]})


@login_required
@require_POST
def unblock(request, pk, rule_id):
    account = get_object_or_404(owned(request), pk=pk)
    with transaction.atomic():
        get_object_or_404(BlockedIP, pk=rule_id, account=account).delete()
        if not account.jobs.filter(action="refresh", state="pending").exists():
            ProvisionJob.objects.create(account=account, action="refresh")
        AuditEvent.objects.create(actor=request.user.username, action="security.unblock", target=account.domain)
    return redirect("security", pk=pk)


@login_required
def statistics(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    hours = request.GET.get("hours", "24")
    hours = int(hours) if hours in {"1", "6", "24"} else 24
    samples = list(account.usage_samples.filter(created_at__gte=timezone.now() - timedelta(hours=hours)).order_by("created_at"))
    return render(request, "panel/statistics.html", {"account": account, "usage": AccountUsage.objects.filter(account=account).first(),
        "request_chart": chart([s.requests for s in samples]), "bandwidth_chart": chart([s.bandwidth_bytes for s in samples]),
        "samples": samples, "hours": hours})
