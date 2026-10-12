import hashlib
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from common.models import AuditEvent
from .forms import CheckoutForm
from .gateway import GatewayError, configured, create_payment
from .models import Coupon, Order, PaymentEvent, Product
from .panel_client import PanelError, call, fulfill


def home(request):
    return render(request, "shop/home.html", {"products": Product.objects.filter(active=True).order_by("price")})


def terms(request):
    return render(request, "shop/terms.html")


@login_required
def dashboard(request):
    orders = Order.objects.filter(user=request.user).select_related("product")
    return render(request, "shop/dashboard.html", {"orders": orders[:100], "total": orders.count(),
                  "active": orders.filter(status="active").count(), "pending": orders.filter(status__in=["unpaid", "pending"]).count(),
                  "spent": orders.filter(status__in=["paid", "active"]).aggregate(total=Sum("amount"))["total"] or 0})


@login_required
def checkout(request, slug):
    product = get_object_or_404(Product, slug=slug, active=True)
    form = CheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        price = product.price * values["cycle"]
        discount = 0
        code = values["coupon"].strip().upper()
        coupon = Coupon.objects.filter(code=code, active=True, expires_at__gt=timezone.now(), percent__range=(1, 90)).first() if code else None
        if code and not coupon:
            form.add_error("coupon", "Kode promo tidak valid atau sudah kedaluwarsa.")
        else:
            if coupon:
                discount = price * coupon.percent // 100
            try:
                with transaction.atomic():
                    order = Order.objects.create(user=request.user, product=product, product_name=product.name,
                        panel_plan=product.panel_plan, domain=values["domain"], kind=values["kind"], cycle=values["cycle"],
                        amount=price - discount, discount=discount, coupon_code=code, customer_phone=values["customer_phone"])
                return redirect("order_detail", pk=order.pk)
            except IntegrityError:
                form.add_error("domain", "Domain ini sudah memiliki pesanan atau layanan aktif.")
    return render(request, "shop/checkout.html", {"product": product, "form": form})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("product"), pk=pk, user=request.user)
    return render(request, "shop/order.html", {"order": order, "channels": settings.PAYMENT_CHANNELS,
                  "gateway_ready": configured(), "panel_url": settings.MIKA_PANEL_URL})


@login_required
@require_POST
def pay(request, pk):
    order = get_object_or_404(Order.objects.select_related("user", "product"), pk=pk, user=request.user)
    if not configured():
        messages.error(request, "Pembayaran belum tersedia. Admin perlu mengonfigurasi Tripay.")
        return redirect("order_detail", pk=pk)
    method = request.POST.get("method", "")
    if method not in settings.PAYMENT_CHANNELS:
        return HttpResponseForbidden("Invalid payment channel")
    # Atomic claim prevents duplicate outbound create requests on double-clicks.
    claimed = Order.objects.filter(pk=pk, status="unpaid", payment_requested_at__isnull=True).update(payment_requested_at=timezone.now())
    if not claimed:
        messages.info(request, "Permintaan pembayaran sudah diproses. Periksa invoice atau hubungi admin.")
        return redirect("order_detail", pk=pk)
    try:
        data = create_payment(order, method)
        total = int(data["amount"])
        fee = int(data.get("fee_customer", 0))
        if total != order.amount + fee or fee < 0:
            raise GatewayError("Jumlah transaksi dari gateway tidak sesuai invoice.")
        Order.objects.filter(pk=pk, status="unpaid").update(status="pending", payment_reference=data["reference"],
            payment_url=data["checkout_url"], payment_method=method, payment_total=total, payment_fee=fee,
            expires_at=timezone.now() + timedelta(days=1))
        return redirect(data["checkout_url"])
    except (GatewayError, ValueError, TypeError, KeyError, IntegrityError) as exc:
        messages.error(request, str(exc) if isinstance(exc, GatewayError) else "Respons pembayaran perlu diperiksa admin.")
        # Keep claim until the admin reconciles the reference in Tripay; timeout is ambiguous.
        Order.objects.filter(pk=pk).update(status="review")
    return redirect("order_detail", pk=pk)


@csrf_exempt
@require_POST
def tripay_callback(request):
    private = settings.TRIPAY_PRIVATE_KEY
    if not private:
        return JsonResponse({"success": False}, status=503)
    expected = hmac.new(private.encode(), request.body, hashlib.sha256).hexdigest()
    if request.headers.get("X-Callback-Event") != "payment_status" or not hmac.compare_digest(expected, request.headers.get("X-Callback-Signature", "")):
        return JsonResponse({"success": False}, status=403)
    try:
        data = json.loads(request.body)
        reference = data["reference"]
        merchant_ref = data["merchant_ref"]
        status = data["status"]
        if status not in {"PAID", "UNPAID", "EXPIRED", "FAILED", "REFUND"}:
            raise ValueError("Unknown status")
        if data.get("is_closed_payment") not in {1, True}:
            raise ValueError("Expected closed payment")
        with transaction.atomic():
            order = Order.objects.select_for_update().get(payment_reference=reference)
            if merchant_ref != order.reference or int(data["total_amount"]) != order.payment_total:
                return JsonResponse({"success": False, "message": "Invoice mismatch"}, status=400)
            digest = hashlib.sha256(request.body).hexdigest()
            _, created = PaymentEvent.objects.get_or_create(digest=digest, defaults={"order": order, "gateway_status": status})
            if not created:
                return JsonResponse({"success": True})
            if status == "PAID" and order.status in {"unpaid", "pending", "expired", "failed"}:
                order.status = "paid"
                order.paid_at = timezone.now()
            elif status in {"EXPIRED", "FAILED"} and order.status in {"unpaid", "pending"}:
                order.status = "expired" if status == "EXPIRED" else "failed"
            elif status == "REFUND":
                order.status = "review"
            order.save(update_fields=["status", "paid_at"])
            AuditEvent.objects.create(actor="tripay", action=f"payment.{status.lower()}", target=order.reference)
        # Provisioning is independent. A confirmed payment stays durable when the panel is offline.
        return JsonResponse({"success": True})
    except (ValueError, TypeError, KeyError, Order.DoesNotExist):
        return JsonResponse({"success": False, "message": "Invalid callback"}, status=400)


@login_required
@require_POST
def sync(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    try:
        fulfill(order)
        messages.success(request, "Status layanan diperbarui.")
    except PanelError:
        messages.error(request, "Panel belum tersedia atau pembayaran belum terverifikasi. Worker akan mencoba lagi.")
    return redirect("order_detail", pk=pk)


@login_required
@require_POST
def panel_login(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user, status="active")
    try:
        data = call(f"/api/v1/accounts/{order.reference}/sso/", {})
        return render(request, "shop/sso.html", {"token": data["token"], "panel_url": settings.MIKA_PANEL_URL})
    except (PanelError, KeyError):
        messages.error(request, "Login panel belum tersedia. Coba lagi nanti.")
        return redirect("order_detail", pk=pk)
