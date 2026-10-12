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

## Checkout dan pemeriksaan koneksi

Memilih paket membuka form konfigurasi hosting. Setelah pelanggan membuat invoice, pilih metode pembayaran dan klik **Buat pembayaran Tripay**. Jika gateway berhasil membuat transaksi dan jumlahnya sesuai invoice, aplikasi menyimpan referensi lalu langsung mengarahkan pelanggan ke checkout Tripay. Invoice pending tetap menyediakan tautan **Lanjutkan pembayaran** ketika pelanggan membukanya kembali.

Untuk pemeriksaan read-only pada VPS, jalankan sebagai root dengan environment shop dimuat:

```bash
sudo bash -c 'set -a; . /etc/mikapanels/shop.env; set +a; cd /opt/mikapanels; .venv/bin/python manage.py check_tripay'
```

Perintah hanya menampilkan mode, status terisi/kosong untuk nama kredensial, serta ketersediaan channel. Nilai kunci tidak dicetak dan pembayaran tidak dibuat. Keberhasilan endpoint channel membuktikan akses API key, bukan signature private key/kode merchant; checkout sandbox tetap perlu diuji.

Kode VPS disalin installer ke `/opt/mikapanels`, tanpa metadata Git. `git pull` pada folder clone saja belum memperbarui aplikasi yang sedang berjalan. Untuk patch checkout ini, ambil commit terbaru pada clone, salin `storefront/views.py` dan `storefront/management/commands/check_tripay.py` ke lokasi yang sama di `/opt/mikapanels`, lalu restart `mychahost` dan `mycha-orders`. Patch tidak mengubah model/database atau konfigurasi kredensial.

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
