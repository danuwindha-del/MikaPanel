import hashlib
import io
import zipfile
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from common.models import AuditEvent
from . import files
from .models import Account, LoginToken, Plan, ProvisionJob


def owned(request):
    return Account.objects.select_related("plan", "owner").all() if request.user.is_staff else Account.objects.select_related("plan", "owner").filter(owner=request.user)


def home(request):
    return redirect("/dashboard/" if request.user.is_authenticated else "/login/")


@login_required
def dashboard(request):
    accounts = owned(request)
    return render(request, "panel/dashboard.html", {"accounts": accounts[:100], "total": accounts.count(),
        "active": accounts.filter(status="active").count(), "queued": accounts.filter(status="queued").count(),
        "plans": Plan.objects.filter(active=True), "events": AuditEvent.objects.all()[:8] if request.user.is_staff else [],
        "jobs": ProvisionJob.objects.select_related("account").order_by("-created_at")[:8] if request.user.is_staff else []})


@login_required
def account_detail(request, pk):
    account = get_object_or_404(owned(request), pk=pk)
    entries = []
    content = None
    name = request.GET.get("file", "")
    if account.status == "active":
        try:
            entries = files.listing(account)
            if name:
                content = files.read_file(account, name).decode("utf-8")
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            messages.error(request, "File tidak bisa dibuka atau bukan teks UTF-8.")
    return render(request, "panel/account.html", {"account": account, "entries": entries, "content": content,
                  "filename": name, "server_ip": settings.MIKA_SERVER_IP})


@login_required
@require_POST
def file_save(request, pk):
    account = get_object_or_404(owned(request), pk=pk, status="active")
    try:
        upload = request.FILES.get("upload")
        if upload:
            if upload.size > files.MAX_FILE:
                raise ValueError("File terlalu besar (maksimal 10 MB).")
            name, data = upload.name, upload.read()
        else:
            name, data = request.POST.get("filename", ""), request.POST.get("content", "").encode("utf-8")
        files.write_file(account, name, data)
        AuditEvent.objects.create(actor=request.user.username, action="file.save", target=f"{account.domain}/{name}")
        messages.success(request, "File berhasil disimpan.")
    except (OSError, ValueError):
        messages.error(request, "Upload gagal: periksa nama file, ukuran, kapasitas, dan izin direktori.")
    return redirect("account_detail", pk=pk)


@login_required
def backup(request, pk):
    account = get_object_or_404(owned(request), pk=pk, status="active")
    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in files.listing(account):
            if total + item["size"] > 50 * 1024 * 1024:
                return HttpResponseForbidden("Backup web dibatasi 50 MB. Gunakan backup administrator untuk situs besar.")
            try:
                data = files.read_file(account, item["name"])
            except (OSError, ValueError):
                continue
            total += len(data)
            archive.writestr(item["name"], data)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f"{account.domain}-root-files.zip")


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
