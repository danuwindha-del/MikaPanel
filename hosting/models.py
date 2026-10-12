import uuid
from django.conf import settings
from django.db import models


class Plan(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    disk_mb = models.PositiveIntegerField(default=1024)
    php_workers = models.PositiveIntegerField(default=2)
    memory_mb = models.PositiveIntegerField(default=128)
    database_limit = models.PositiveIntegerField(default=3)
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
    database_count = models.PositiveIntegerField(default=0)
    dns_serial = models.PositiveIntegerField(default=1)
    dns_initialized = models.BooleanField(default=False)
    dns_state = models.CharField(max_length=20, default="pending")
    ssl_enabled = models.BooleanField(default=False)
    ssl_expires_at = models.DateTimeField(null=True, blank=True)
    force_https = models.BooleanField(default=False)
    directory_listing = models.BooleanField(default=False)
    security_headers = models.BooleanField(default=True)

    @property
    def system_user(self):
        return "mh" + self.id.hex[:12]

    def __str__(self):
        return self.domain


class ProvisionJob(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="jobs")
    action = models.CharField(max_length=20, choices=[("create", "Create"), ("suspend", "Suspend"), ("resume", "Resume"), ("ssl", "SSL"),
        ("refresh", "Refresh"), ("dns", "DNS"), ("db_create", "Database create"), ("db_delete", "Database delete"), ("db_rotate", "Database password")])
    state = models.CharField(max_length=20, default="pending", choices=[("pending", "Pending"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")])
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resource_id = models.UUIDField(null=True, blank=True)


class LoginToken(models.Model):
    digest = models.CharField(max_length=64, unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)


class DNSRecord(models.Model):
    TYPES = [(s, s) for s in ["A", "AAAA", "CNAME", "MX", "TXT"]]
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="dns_records")
    kind = models.CharField(max_length=8, choices=TYPES)
    name = models.CharField(max_length=253, default="@")
    value = models.TextField(max_length=2048)
    ttl = models.PositiveIntegerField(default=3600)
    priority = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "kind", "pk"]
        constraints = [models.UniqueConstraint(fields=["account", "kind", "name", "value"], name="unique_dns_record")]


class ManagedDatabase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="managed_databases")
    label = models.SlugField(max_length=24)
    database_name = models.CharField(max_length=64, unique=True)
    username = models.CharField(max_length=32, unique=True)
    password_ciphertext = models.TextField()
    state = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BlockedIP(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="blocked_ips")
    network = models.CharField(max_length=50)
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "network"], name="unique_blocked_network")]


class MetricSample(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    cpu_total = models.BigIntegerField()
    cpu_idle = models.BigIntegerField()
    cpu_percent = models.FloatField(null=True)
    memory_total = models.BigIntegerField()
    memory_used = models.BigIntegerField()
    disk_total = models.BigIntegerField()
    disk_used = models.BigIntegerField()
    network_rx = models.BigIntegerField()
    network_tx = models.BigIntegerField()
    network_rate = models.FloatField(null=True)
    uptime_seconds = models.BigIntegerField()


class AccountUsage(models.Model):
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name="usage")
    disk_bytes = models.BigIntegerField(default=0)
    file_count = models.PositiveIntegerField(default=0)
    requests = models.BigIntegerField(default=0)
    error_requests = models.BigIntegerField(default=0)
    bandwidth_bytes = models.BigIntegerField(default=0)
    log_offset = models.BigIntegerField(default=0)
    log_inode = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class UsageSample(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="usage_samples")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    requests = models.BigIntegerField(default=0)
    errors = models.BigIntegerField(default=0)
    bandwidth_bytes = models.BigIntegerField(default=0)
