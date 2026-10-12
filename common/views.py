import hashlib
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import redirect_to_login
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import RegisterForm, TicketForm
from .models import AuditEvent, LoginAttempt, Ticket, TicketReply
from .models import Notification


def health(request):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    from django.http import JsonResponse
    return JsonResponse({"status": "ok", "service": settings.SERVICE})


def signin(request):
    if request.user.is_authenticated:
        return redirect("/dashboard/")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        # Proxy preserves the actual address in REMOTE_ADDR in deployment; use username limit too.
        now = timezone.now()
        username = request.POST.get("username", "").lower()[:150]
        key = hashlib.sha256(username.encode()).hexdigest()
        attempt, _ = LoginAttempt.objects.get_or_create(key=key, defaults={"window_start": now})
        if now - attempt.window_start > timedelta(minutes=15):
            attempt.failures = 0
            attempt.window_start = now
            attempt.save()
        if attempt.failures >= 10:
            return render(request, "form.html", {"title": "Coba lagi dalam 15 menit", "form": form}, status=429)
        if form.is_valid():
            login(request, form.get_user())
            attempt.delete()
            AuditEvent.objects.create(actor=request.user.username, action="login")
            target = request.POST.get("next", "/dashboard/")
            if not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
                target = "/dashboard/"
            return redirect(target)
        LoginAttempt.objects.filter(pk=attempt.pk).update(failures=F("failures") + 1)
    return render(request, "form.html", {"title": "Selamat datang kembali", "form": form,
                  "next": request.GET.get("next", "/dashboard/"), "button": "Masuk ke dashboard"})


@require_POST
def signout(request):
    logout(request)
    return redirect("/")


def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("/dashboard/")
    return render(request, "form.html", {"title": "Mulai perjalanan digital Anda", "form": form, "button": "Buat akun"})


@login_required
def tickets(request):
    form = TicketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.user = request.user
        ticket.save()
        TicketReply.objects.create(ticket=ticket, user=request.user, body=form.cleaned_data["body"])
        messages.success(request, "Tiket berhasil dikirim.")
        return redirect("/tickets/")
    qs = Ticket.objects.all() if request.user.is_staff else Ticket.objects.filter(user=request.user)
    return render(request, "tickets.html", {"tickets": qs[:100], "form": form})


@login_required
def ticket_detail(request, pk):
    qs = Ticket.objects.all() if request.user.is_staff else Ticket.objects.filter(user=request.user)
    ticket = get_object_or_404(qs, pk=pk)
    if request.method == "POST":
        if request.POST.get("action") == "close":
            ticket.status = "closed"
            ticket.save(update_fields=["status"])
        else:
            body = request.POST.get("body", "").strip()
            if body and len(body) <= 5000:
                TicketReply.objects.create(ticket=ticket, user=request.user, body=body)
                ticket.status = "open"
                ticket.save(update_fields=["status"])
        return redirect("ticket_detail", pk=pk)
    return render(request, "ticket.html", {"ticket": ticket})


@login_required
def notifications(request):
    if request.method == "POST":
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return redirect("/notifications/")
    return render(request, "notifications.html", {"notifications": request.user.notifications.all()[:100]})


@login_required
def profile(request):
    from django import forms
    from django.contrib.auth.forms import PasswordChangeForm
    from django.contrib.auth import update_session_auth_hash
    class ProfileForm(forms.Form):
        first_name = forms.CharField(max_length=150, label="Nama tampilan")
    form = ProfileForm(request.POST if request.POST.get("action") == "profile" else None,
                       initial={"first_name": request.user.first_name or request.user.username})
    password_form = PasswordChangeForm(request.user, data=request.POST if request.POST.get("action") == "password" else None)
    if request.method == "POST":
        if request.POST.get("action") == "profile" and form.is_valid():
            request.user.first_name = form.cleaned_data["first_name"]
            request.user.save(update_fields=["first_name"])
            messages.success(request, "Profil diperbarui.")
            return redirect("/profile/")
        elif request.POST.get("action") == "password" and password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password diperbarui.")
            return redirect("/profile/")
    return render(request, "profile.html", {"form": form, "password_form": password_form})
