# Tripay

Dokumentasi resmi: https://tripay.co.id/developer

Adapter menyediakan endpoint `transaction/create` dan rekonsiliasi `transaction/detail`, menggunakan base URL `https://tripay.co.id/api-sandbox` atau `https://tripay.co.id/api`. Semua request memverifikasi TLS. Payload create menggunakan form encoding dengan key order_items[0][…], sesuai contoh Python resmi. API key dikirim sebagai bearer; private key dipakai lokal untuk HMAC, bukan dikirim ke panel atau browser.

## Konfigurasi

Atur nilai di konfigurasi **shop**:

- `TRIPAY_MODE`: `sandbox` untuk pengujian, `production` untuk merchant aktif.
- `TRIPAY_API_KEY`, `TRIPAY_PRIVATE_KEY`, `TRIPAY_MERCHANT_CODE`: dari akun merchant sesuai mode.
- `TRIPAY_CHANNELS`: channel yang memang aktif di merchant, contoh `BRIVA,BNIVA,QRIS`. Daftar ini tidak melakukan discovery otomatis.
- `MYCHA_PUBLIC_URL`: URL HTTPS toko yang dapat diakses gateway.
- Callback: `<URL toko>/payments/tripay/callback/`.

Installer meminta kredensial dengan prompt tersembunyi. Di lokal, edit `var/config.json` bagian `shop` secara privat dan restart proses. Jangan menaruh nilai kunci di source, screenshot, chat, atau Git. Private key HMAC harus tersedia sebagai nilai asli pada proses toko; placeholder proxy-secret tidak dapat dipakai untuk tanda tangan lokal.

## Verifikasi

Signature transaksi = HMAC-SHA256(private key, merchant code + merchant reference + amount). Callback diverifikasi terhadap **raw body** menggunakan header `X-Callback-Signature`, serta `X-Callback-Event: payment_status`.

Callback harus memiliki closed-payment flag, referensi transaksi yang tersimpan, merchant reference sesuai invoice, dan `total_amount` sesuai total yang dikonfirmasi saat pembuatan transaksi (termasuk biaya pelanggan). Callback gagal pemeriksaan tidak mengubah invoice. Status `PAID` disimpan sebelum provisioning; gateway tidak perlu menunggu Nginx siap. Callback identik diproses sekali. `EXPIRED`/`FAILED` yang datang setelah pembayaran tidak menurunkan layanan berbayar. Refund membawa invoice ke review, tidak otomatis mematikan atau mengaktifkan hosting.

Worker toko mengambil invoice paid/active setiap 30 detik, memakai external ID stabil untuk provisioning, dan memperbarui status panel. Ketika panel tidak tersedia, pembayaran tetap tersimpan. Tombol sinkronisasi pelanggan dapat memicu retry tanpa menciptakan transaksi pembayaran baru.

## Timeout dan rekonsiliasi

Jika create timeout, jangan mencoba membayar invoice yang sama lagi sebelum pemeriksaan: transaksi mungkin sudah dibuat di gateway. Admin mencari merchant reference invoice di dashboard Tripay, kemudian menjalankan:

```bash
# Jalankan dengan environment shop yang sudah dimuat, dari /opt/mikapanels
.venv/bin/python manage.py reconcile_payment MH-<UUID_TANPA_TANDA_HUBUNG> <REFERENSI_TRIPAY>
```

Perintah memverifikasi referensi, merchant reference, jumlah, biaya, dan status melalui API gateway. Ia tidak menerima input `paid` dari operator sebagai bukti pembayaran. Invoice yang pernah menerima refund tidak diaktifkan kembali secara otomatis. Hubungi dukungan merchant untuk transaksi yang tidak dapat dikonfirmasi.

## Status validasi

Suite proyek menggunakan fixture respons dan callback bertanda tangan dengan kunci pengujian. Belum ada kredensial merchant dalam lingkungan ini dan belum ada transaksi sandbox/production sungguhan yang dieksekusi. Dokumentasi resmi Tripay telah dibaca dari cloud (HTTP 200); encoding request, field jumlah pada respons create, dan kontrak callback disesuaikan dengan contoh resminya. Domain `tripay.co.id` juga tersimpan dalam draft jaringan. Uji seluruh channel merchant pada staging sebelum produksi.
