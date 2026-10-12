import uuid
from django.conf import settings
from django.db import models


class Plan(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    disk_mb = models.PositiveIntegerField(default=1024)
    php_workers = models.PositiveIntegerField(default=2)
    memory_mb = models.PositiveIntegerField(default=128)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(max_length=100, unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    domain = models.CharField(max_length=253, unique=True)
    kind = models.CharField(max_length=10, choices=[("static", "Statis"), ("php", "PHP 8.3")])
    status = models.CharField(max_length=20, default="queued", choices=[
        ("queued", "Dalam antrean"), ("active", "Aktif"), ("suspended", "Ditangguhkan"), ("failed", "Gagal")])
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def system_user(self):
        return "mh" + self.id.hex[:12]

    def __str__(self):
        return self.domain


class ProvisionJob(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="jobs")
    action = models.CharField(max_length=20, choices=[("create", "Create"), ("suspend", "Suspend"), ("resume", "Resume"), ("ssl", "SSL")])
    state = models.CharField(max_length=20, default="pending", choices=[("pending", "Pending"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")])
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LoginToken(models.Model):
    digest = models.CharField(max_length=64, unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
