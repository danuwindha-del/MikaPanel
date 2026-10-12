# Validasi lingkungan pengembangan

Hasil pada cloud, Python 3.12:

- Instalasi dependency lock dengan `--require-hashes --force-reinstall`: berhasil. Hash diperoleh dari metadata distribusi PyPI, bukan diubah untuk melewati kegagalan verifikasi.
- Migrasi kedua database, katalog awal, admin lokal, dan collectstatic: berhasil.
- Seed/configure berulang mempertahankan konfigurasi dan perubahan katalog.
- `check` kedua service: tidak ada isu.
- `makemigrations --check --dry-run`: tidak ada perubahan model yang belum dimigrasi.
- Suite pytest setelah fitur hosting manual: **68 passed**, tidak ada test skipped/xfail.
- Hosting manual: dashboard dan form add Django admin membuat akun queued/job/audit tanpa order pembayaran; worker demo mengaktifkan akun dan membuat file website. Pelanggan/staff tanpa izin, request tanpa CSRF, domain/masa aktif/engine yang tidak valid, dan pilihan paket/pemilik nonaktif ditolak. Pengulangan submit tidak membuat job ganda; kegagalan penulisan antrean me-rollback akun.
- Checkout berbayar: respons gateway fixture menghasilkan redirect langsung ke URL Tripay; permintaan berulang tetap tidak membuat charge kedua. Perintah pemeriksaan channel menguji konfigurasi kosong, channel aktif/tidak aktif, dan penolakan autentikasi tanpa menampilkan nilai kredensial.
- Preflight password installer: password pendek/numerik dan konfirmasi berbeda diminta ulang tanpa mencetak password. Pengujian standalone tanpa konfigurasi service juga berhasil, tanpa perubahan sistem.
- Browser Chromium pada desktop 1440 px dan ponsel 390 px: halaman depan dan paket tampil, tidak ada overflow horizontal. Daftar akun, checkout/invoice, tiket, API provisioning demo, login admin, edit file, dan SSO sekali pakai antar aplikasi berhasil.
- Browser hosting manual: tombol dashboard/form admin tersedia, form mobile tidak melebar, akun manual diaktifkan worker demo, dan file website dapat diedit. Helper pembaruan manual lulus pemeriksaan syntax/rencana; perubahan sistem VPS belum dieksekusi di cloud.
- Supervisor lokal: kedua web dan worker berjalan, endpoint health memverifikasi koneksi database.
- `install_vps.py --plan-only`: berhasil dan tidak mengubah sistem.
- Dokumentasi resmi Tripay: HTTP 200, adapter mengikuti contoh form encoding dan field respons/callback.

Yang belum dieksekusi: root installer pada Ubuntu 24.04 nyata, akun Linux/Nginx/PHP-FPM produksi, request pembayaran dengan kredensial merchant, callback yang dikirim Tripay sungguhan, Certbot penerbitan/renewal TLS, serta restore backup VPS. Mock dan provisioning demo tidak menggantikan pemeriksaan tersebut.

Screenshot pengujian lokal ada di `var/screenshots/`; file runtime/credential/log tidak termasuk arsip source. Panduan penerapan ada di VPS.md dan TRIPAY.md.
