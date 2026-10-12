from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    actor = models.CharField(max_length=150)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Ticket(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject = models.CharField(max_length=180)
    priority = models.CharField(max_length=20, choices=[("normal", "Normal"), ("urgent", "Mendesak")], default="normal")
    status = models.CharField(max_length=20, choices=[("open", "Terbuka"), ("closed", "Selesai")], default="open")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TicketReply(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="replies")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=500, blank=True)
    link = models.CharField(max_length=250, default="/dashboard/")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
