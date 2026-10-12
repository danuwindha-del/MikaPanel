import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Product(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    tagline = models.CharField(max_length=180)
    price = models.PositiveIntegerField()
    disk_mb = models.PositiveIntegerField()
    memory_mb = models.PositiveIntegerField(default=128)
    php_workers = models.PositiveIntegerField(default=2)
    panel_plan = models.SlugField()
    featured = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Coupon(models.Model):
    code = models.CharField(max_length=32, unique=True)
    percent = models.PositiveIntegerField(default=10)
    expires_at = models.DateTimeField()
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=100)
    panel_plan = models.SlugField()
    domain = models.CharField(max_length=253, unique=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    kind = models.CharField(max_length=10, choices=[("static", "Website statis"), ("php", "PHP 8.3")])
    cycle = models.PositiveIntegerField(default=1)
    amount = models.PositiveIntegerField()
    discount = models.PositiveIntegerField(default=0)
    coupon_code = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=30, default="unpaid", choices=[
        ("unpaid", "Belum dibayar"), ("pending", "Menunggu pembayaran"), ("paid", "Dibayar"),
        ("active", "Aktif"), ("expired", "Kedaluwarsa"), ("failed", "Gagal"), ("review", "Perlu tinjauan")])
    payment_reference = models.CharField(max_length=100, blank=True, unique=True, null=True)
    payment_url = models.URLField(max_length=1000, blank=True)
    payment_method = models.CharField(max_length=32, blank=True)
    payment_total = models.PositiveIntegerField(null=True, blank=True)
    payment_fee = models.PositiveIntegerField(default=0)
    payment_requested_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    panel_account_id = models.CharField(max_length=36, blank=True)
    panel_status = models.CharField(max_length=20, blank=True)
    provisioning_error = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def reference(self):
        return "MH-" + self.id.hex.upper()


class PaymentEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payment_events")
    digest = models.CharField(max_length=64, unique=True)
    gateway_status = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
