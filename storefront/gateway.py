import hashlib
import hmac
import time
from urllib.parse import urlsplit
import requests
from django.conf import settings


class GatewayError(Exception):
    pass


def base_url():
    if settings.TRIPAY_MODE not in {"sandbox", "production"}:
        raise GatewayError("Mode Tripay tidak valid")
    return "https://tripay.co.id/api-sandbox" if settings.TRIPAY_MODE == "sandbox" else "https://tripay.co.id/api"


def configured():
    return bool(settings.TRIPAY_API_KEY and settings.TRIPAY_PRIVATE_KEY and settings.TRIPAY_MERCHANT_CODE)


def create_payment(order, method):
    if not configured():
        raise GatewayError("Tripay belum dikonfigurasi. Admin perlu mengisi kredensial gateway.")
    if method not in settings.PAYMENT_CHANNELS:
        raise GatewayError("Metode pembayaran tidak tersedia.")
    message = f"{settings.TRIPAY_MERCHANT_CODE}{order.reference}{order.amount}"
    signature = hmac.new(settings.TRIPAY_PRIVATE_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()
    payload = {
        "method": method, "merchant_ref": order.reference, "amount": order.amount,
        "customer_name": order.user.first_name or order.user.username,
        "customer_email": order.user.email,
        "customer_phone": order.customer_phone,
        "order_items[0][sku]": order.product.slug,
        "order_items[0][name]": f"{order.product_name} ({order.cycle} bulan)",
        "order_items[0][price]": order.amount,
        "order_items[0][quantity]": 1,
        "return_url": f"{settings.MYCHA_PUBLIC_URL}/orders/{order.id}/",
        "callback_url": f"{settings.MYCHA_PUBLIC_URL}/payments/tripay/callback/",
        "expired_time": int(time.time()) + 86400, "signature": signature,
    }
    try:
        response = requests.post(base_url() + "/transaction/create", data=payload,
                                 headers={"Authorization": "Bearer " + settings.TRIPAY_API_KEY}, timeout=(5, 25))
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise GatewayError("Tripay menolak transaksi. Periksa pengaturan merchant dan channel.")
        data = body["data"]
        url = urlsplit(data["checkout_url"])
        if url.scheme != "https" or (url.hostname != "tripay.co.id" and not (url.hostname or "").endswith(".tripay.co.id")):
            raise GatewayError("URL pembayaran gateway tidak valid.")
        if not data.get("reference") or len(str(data["reference"])) > 100:
            raise GatewayError("Referensi pembayaran tidak valid.")
        return data
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        # A timeout may occur after gateway creation. Do NOT automatically create a second charge.
        raise GatewayError("Respons Tripay belum dapat dikonfirmasi. Hubungi admin sebelum mencoba transaksi baru.") from exc
