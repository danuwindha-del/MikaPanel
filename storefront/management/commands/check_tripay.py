"""Read-only gateway diagnostic; never prints credentials or creates a transaction."""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from storefront.gateway import GatewayError, base_url


class Command(BaseCommand):
    help = "Check Tripay configuration and active channels without creating a payment"

    def handle(self, *args, **options):
        if settings.SERVICE != "shop":
            raise CommandError("Jalankan dengan environment MychaHost/shop.")
        self.stdout.write(f"Mode Tripay: {settings.TRIPAY_MODE}")
        missing = []
        for name in ("TRIPAY_API_KEY", "TRIPAY_PRIVATE_KEY", "TRIPAY_MERCHANT_CODE"):
            present = bool(getattr(settings, name, "").strip())
            self.stdout.write(f"{name}: {'TERISI' if present else 'KOSONG'}")
            if not present:
                missing.append(name)
        if missing:
            raise CommandError("Lengkapi konfigurasi shop.env lalu restart MychaHost. Nilai kunci tidak ditampilkan.")
        try:
            url = base_url() + "/merchant/payment-channel"
            response = requests.get(url, headers={"Authorization": "Bearer " + settings.TRIPAY_API_KEY}, timeout=(5, 15))
            if response.status_code in (401, 403):
                raise CommandError("Tripay menolak akses. Periksa API key dan kecocokan mode sandbox/production.")
            response.raise_for_status()
            body = response.json()
            if body.get("success") is not True:
                raise CommandError("Tripay menolak permintaan channel. Periksa API key dan status merchant pada mode yang dipilih.")
            channels = body["data"]
            if not isinstance(channels, list):
                raise ValueError("Invalid channel response")
            available = {item["code"] for item in channels if item.get("active") is True}
            unavailable = []
            for code in settings.PAYMENT_CHANNELS:
                active = code in available
                self.stdout.write(f"Channel {code}: {'AKTIF' if active else 'TIDAK TERSEDIA'}")
                if not active:
                    unavailable.append(code)
            if unavailable:
                raise CommandError("Sesuaikan TRIPAY_CHANNELS dengan channel aktif merchant, lalu restart MychaHost.")
        except GatewayError as exc:
            raise CommandError(str(exc)) from exc
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise CommandError("Koneksi atau respons Tripay belum dapat diverifikasi. Periksa jaringan VPS dan status API gateway.") from exc
        self.stdout.write(self.style.SUCCESS("Koneksi API key dan channel berhasil diperiksa. Tidak ada pembayaran yang dibuat."))
        self.stdout.write("Private key dan kode merchant belum dibuktikan oleh pemeriksaan ini; signature transaksi tetap perlu diuji melalui checkout sandbox.")
