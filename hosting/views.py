import hashlib
import io
import zipfile
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from common.models import AuditEvent
from . import files
from .models import Account, LoginToken, Plan, ProvisionJob
from .models import MetricSample, AccountUsage
from .forms import ManualAccountForm
from .services import can_create_manual_account, save_manual_account


def owned(request):
    return Account.objects.select_related("plan", "owner").all() if request.user.is_staff else Account.objects.select_related("plan", "owner").filter(owner=request.user)


def home(request):
    return redirect("/dashboard/" if request.user.is_authenticated else "/login/")


@login_required
def dashboard(request):
    accounts = owned(request)
    from .telemetry import chart
    samples = list(MetricSample.objects.order_by("-created_at")[:48])[::-1]
    sample = samples[-1] if samples else None
    network_peak = max((s.network_rate or 0 for s in samples), default=0)
    from django.template.defaultfilters import filesizeformat
    from django.db.models import Sum
    usage = AccountUsage.objects.filter(account__in=accounts).aggregate(disk=Sum("disk_bytes"), bandwidth=Sum("bandwidth_bytes"))
    return render(request, "panel/dashboard.html", {"accounts": accounts[:100], "total": accounts.count(),
        "active": accounts.filter(status="active").count(), "queued": accounts.filter(status="queued").count(),
        "plans": Plan.objects.filter(active=True), "events": AuditEvent.objects.all()[:8] if request.user.is_staff else [],
        "can_create_hosting": can_create_manual_account(request.user),
        "jobs": ProvisionJob.objects.select_related("account").order_by("-created_at")[:8] if request.user.is_staff else [],
        "sample": sample, "memory_percent": sample.memory_used / sample.memory_total * 100 if sample and sample.memory_total else 0,
        "disk_percent": sample.disk_used / sample.disk_total * 100 if sample and sample.disk_total else 0,
        "cpu_chart": chart([s.cpu_percent for s in samples if s.cpu_percent is not None]),
        "network_chart": chart([s.network_rate for s in samples if s.network_rate is not None]),
        "network_percent": sample.network_rate / network_peak * 100 if sample and sample.network_rate is not None and network_peak else 0,
        "network_value": filesizeformat(sample.network_rate) if sample and sample.network_rate is not None else None,
        "network_peak_label": filesizeformat(network_peak) + "/s",
        "usage_disk": usage["disk"] or 0, "usage_bandwidth": usage["bandwidth"] or 0})


@login_required
def create_account(request):
    if not can_create_manual_account(request.user):
        return HttpResponseForbidden("Administrator dengan izin membuat akun hosting diperlukan.")
    form = ManualAccountForm(request.POST or None, initial={"owner": request.user.pk})
    if request.method == "POST" and form.is_valid():
        try:
            account = save_manual_account(form.save(commit=False), actor=request.user, days=form.cleaned_data["days"])
        except IntegrityError:
            form.add_error("domain", "Domain sudah digunakan oleh akun lain. Tidak ada pekerjaan tambahan yang dibuat.")
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field, errors in exc.message_dict.items():
                    form.add_error(field if field in form.fields else None, errors)
            else:
                form.add_error(None, exc)
        else:
            messages.success(request, "Akun hosting dibuat tanpa pembayaran dan masuk antrean provisioning. Tunggu status Aktif sebelum mengelola file.")
            return redirect("account_detail", pk=account.pk)
    return render(request, "panel/create_account.html", {"form": form})


@login_required
def account_detail(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    return render(request, "panel/account.html", file_context(request, account))


def file_context(request, account):
    entries = []
    content = None
    name = request.GET.get("file", "")
    folder = request.GET.get("path", "")
    try:
        files.path_parts(folder)
    except ValueError:
        folder = ""
    if account.status == "active":
        try:
            entries = files.listing(account, folder)
            if name:
                content = files.read_file(account, name).decode("utf-8")
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            messages.error(request, "File tidak bisa dibuka atau bukan teks UTF-8.")
    breadcrumbs = [{"name": p, "path": "/".join(folder.split("/")[:i + 1])} for i, p in enumerate(folder.split("/")) if p]
    return {"account": account, "entries": entries, "content": content, "filename": name,
            "folder": folder, "breadcrumbs": breadcrumbs, "server_ip": settings.MIKA_SERVER_IP}


@login_required
def file_manager(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    return render(request, "panel/files.html", file_context(request, account))


@login_required
@require_POST
def file_save(request, pk):
    account = get_object_or_404(owned(request), pk=pk, status="active")
    try:
        upload = request.FILES.get("upload")
        if upload:
            if upload.size > files.MAX_FILE:
                raise ValueError("File terlalu besar (maksimal 10 MB).")
            folder = request.POST.get("folder", "")
            files.path_parts(folder)
            name, data = "/".join(filter(None, [folder, files.safe_name(upload.name)])), upload.read()
        else:
            name, data = request.POST.get("filename", ""), request.POST.get("content", "").encode("utf-8")
        files.write_file(account, name, data)
        AuditEvent.objects.create(actor=request.user.username, action="file.save", target=f"{account.domain}/{name}")
        messages.success(request, "File berhasil disimpan.")
    except (OSError, ValueError):
        messages.error(request, "Upload gagal: periksa nama file, ukuran, kapasitas, dan izin direktori.")
    if request.POST.get("return_to") == "files":
        from django.urls import reverse
        from urllib.parse import urlencode
        return redirect(reverse("file_manager", kwargs={"pk": pk}) + "?" + urlencode({"path": request.POST.get("folder", "")}))
    return redirect("account_detail", pk=pk)


@login_required
def backup(request, pk):
    account = get_object_or_404(owned(request), pk=pk, status="active")
    try:
        buffer = files.backup_zip(account)
    except (OSError, ValueError):
        return HttpResponseForbidden("Backup tidak tersedia atau melebihi batas 50 MB/5000 file.")
    return FileResponse(buffer, as_attachment=True, filename=f"{account.domain}-website.zip")


@login_required
@require_POST
def file_action(request, pk):
    account = get_object_or_404(owned(request), pk=pk, status="active")
    action, path = request.POST.get("action"), request.POST.get("path", "")
    try:
        if action == "mkdir":
            if request.POST.get("folder_name"):
                folder = request.POST.get("folder", "")
                files.path_parts(folder)
                path = "/".join(filter(None, [folder, files.safe_name(request.POST["folder_name"])]))
            files.create_directory(account, path)
        elif action == "delete":
            files.delete(account, path)
        elif action == "rename":
            files.rename(account, path, request.POST.get("new_name", ""))
        elif action == "extract":
            upload = request.FILES.get("archive")
            if not upload or upload.size > files.MAX_FILE:
                raise ValueError("ZIP maksimal 10 MB.")
            files.extract_zip(account, upload.read(), request.POST.get("folder", ""))
        else:
            raise ValueError("Tindakan tidak valid.")
        AuditEvent.objects.create(actor=request.user.username, action=f"file.{action}", target=account.domain)
        messages.success(request, "Perubahan file berhasil.")
    except (OSError, ValueError, zipfile.BadZipFile):
        messages.error(request, "Perubahan gagal. Periksa nama/path, izin, kapasitas, dan pastikan folder yang dihapus kosong.")
    from django.urls import reverse
    from urllib.parse import urlencode
    return redirect(reverse("file_manager", kwargs={"pk": pk}) + "?" + urlencode({"path": request.POST.get("folder", "")}))


@login_required
def file_download(request, pk):
    account = get_object_or_404(owned(request), pk=pk, status="active")
    path = request.GET.get("path", "")
    try:
        data = files.read_file(account, path)
        name = files.path_parts(path)[-1]
    except (OSError, ValueError):
        from django.http import Http404
        raise Http404
    return FileResponse(io.BytesIO(data), as_attachment=True, filename=name)


@login_required
@require_POST
def account_action(request, pk):
    if not request.user.is_staff:
        return HttpResponseForbidden("Administrator only")
    account = get_object_or_404(Account, pk=pk)
    action = request.POST.get("action")
    allowed = {"suspend": {"active"}, "resume": {"suspended"}, "create": {"failed", "queued"}, "ssl": {"active"}}
    if action in allowed and account.status in allowed[action] and not account.jobs.filter(state__in=["pending", "running"]).exists():
        ProvisionJob.objects.create(account=account, action=action)
        AuditEvent.objects.create(actor=request.user.username, action=action, target=account.domain)
        messages.success(request, "Tindakan ditambahkan ke antrean worker.")
    else:
        messages.error(request, "Tindakan tidak sesuai status atau masih ada pekerjaan berjalan.")
    return redirect("account_detail", pk=pk)


@csrf_exempt
def sso(request):
    if request.method == "GET":
        # Token arrives via POST from MychaHost, never in query strings or access logs.
        return redirect("/login/")
    if request.headers.get("Origin") != settings.MYCHA_PUBLIC_URL:
        return HttpResponseForbidden("Invalid SSO origin")
    token = request.POST.get("token", "")
    digest = hashlib.sha256(token.encode()).hexdigest()
    qs = LoginToken.objects.filter(digest=digest, used=False, expires_at__gt=timezone.now())
    record = qs.first()
    if not record or not qs.update(used=True):
        return HttpResponseForbidden("Tautan masuk kedaluwarsa atau sudah digunakan.")
    login(request, record.owner, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("/dashboard/")
