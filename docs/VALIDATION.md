# Validasi lingkungan pengembangan

Hasil pada cloud, Python 3.12:

- Instalasi dependency lock dengan `--require-hashes --force-reinstall`: berhasil. Hash diperoleh dari metadata distribusi PyPI, bukan diubah untuk melewati kegagalan verifikasi.
- Migrasi kedua database, katalog awal, admin lokal, dan collectstatic: berhasil.
- Seed/configure berulang mempertahankan konfigurasi dan perubahan katalog.
- `check` kedua service: tidak ada isu.
- `makemigrations --check --dry-run`: tidak ada perubahan model yang belum dimigrasi.
- Suite pytest: **47 passed**, tidak ada test skipped/xfail.
- Browser Chromium pada desktop 1440 px dan ponsel 390 px: halaman depan dan paket tampil, tidak ada overflow horizontal. Daftar akun, checkout/invoice, tiket, API provisioning demo, login admin, edit file, dan SSO sekali pakai antar aplikasi berhasil.
- Supervisor lokal: kedua web dan worker berjalan, endpoint health memverifikasi koneksi database.
- `install_vps.py --plan-only`: berhasil dan tidak mengubah sistem.
- Dokumentasi resmi Tripay: HTTP 200, adapter mengikuti contoh form encoding dan field respons/callback.

Yang belum dieksekusi: root installer pada Ubuntu 24.04 nyata, akun Linux/Nginx/PHP-FPM produksi, request pembayaran dengan kredensial merchant, callback yang dikirim Tripay sungguhan, Certbot penerbitan/renewal TLS, serta restore backup VPS. Mock dan provisioning demo tidak menggantikan pemeriksaan tersebut.

Screenshot pengujian lokal ada di `var/screenshots/`; file runtime/credential/log tidak termasuk arsip source. Panduan penerapan ada di VPS.md dan TRIPAY.md.
