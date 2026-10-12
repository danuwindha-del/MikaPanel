# MikaPanels × MychaHost

Dua aplikasi Python terpisah untuk panel hosting dan toko hosting. Backend menggunakan Django 5.2, installer terminal menggunakan Rich, dan web menggunakan HTML/CSS dengan tema navy–emas, landing premium, dan dashboard terang yang responsif. Tidak membutuhkan Node.js untuk build frontend.

**Versi awal yang dapat dijalankan untuk hosting website statis/PHP di Ubuntu 24.04.** Ini belum memiliki seluruh kemampuan cPanel. Provisioning lokal, alur aplikasi, MariaDB socket terisolasi, dan DNS BIND9 nyata diuji; pemasangan sistem VPS, penerbitan sertifikat, dan transaksi Tripay sungguhan masih memerlukan pengujian pada server/merchant Anda.

## Fitur yang tersedia

| MikaPanels | MychaHost |
|---|---|
| Dashboard admin dan pelanggan | Landing page dan tiga paket hosting |
| Akun hosting per domain dan paket | Registrasi, login, dan dashboard pelanggan |
| Pembuatan hosting manual oleh admin tanpa pembayaran | Pemesanan pelanggan tetap melalui verifikasi pembayaran |
| API bearer untuk provisioning idempotent | Checkout statis/PHP, 1/3/12 bulan |
| Antrean worker dengan retry melalui panel | Harga snapshot, kupon persen, dan invoice |
| Akun Linux dan Nginx vhost dalam mode sistem | Tripay sandbox/production, VA/QRIS sesuai merchant |
| PHP-FPM pool per website | Callback HMAC dengan pemeriksaan invoice dan jumlah |
| Folder/file, editor sintaks, upload/download, rename, hapus, ekstrak ZIP | Pencegahan double-click pembayaran |
| Backup ZIP website beserta subfolder | Retry provisioning pesanan berbayar |
| Suspend, resume, dan suspend saat kedaluwarsa | Login sekali pakai ke MikaPanels (60 detik) |
| SSL mandiri pelanggan, HTTPS, header keamanan, blokir IP | Tiket, balasan admin, dan riwayat transaksi |
| DNS BIND9: A/AAAA/CNAME/MX/TXT, TTL, edit/hapus/export | Administrasi produk dan kupon |
| MariaDB: buat database/user, ganti password, hapus, batas slot paket | Profil dan notifikasi aktivasi hosting |
| Gauge Linux dan grafik request/error/bandwidth website | Desain responsif navy–emas |
| Audit aktivitas, profil, notifikasi, administrasi paket | |

Paket contoh: **Launch Rp19.000**, **Stellar Rp49.000**, **Nebula Rp99.000** per bulan. Admin dapat mengubah harga di MychaHost `/admin/`; slug `panel_plan` harus sesuai paket aktif di MikaPanels. Seed tidak menimpa perubahan admin.

## Menjalankan secara lokal

Memerlukan Python 3.12+. Jalankan dari root proyek:

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.lock
.venv/bin/python tools/configure.py
.venv/bin/python tools/dev.py
```

Installer lokal meminta email dan password admin. Untuk setup otomatis gunakan `tools/configure.py --non-interactive`; password acak disimpan pada `var/local-admin.json` dengan izin 0600. Kedua aplikasi memiliki admin bernama `admin`, database, secret key, dan cookie sesi terpisah.

Port pengembangan: panel **8001**, toko **8002**, hanya bind ke loopback. Supervisor memulai kedua aplikasi dan kedua worker, memeriksa kesehatan database, dan menghentikan proses anak saat ditutup. Log ada pada `var/*-web.log` dan `var/*-worker.log`. Kredensial Tripay kosong berarti tombol pembayaran dinonaktifkan; aplikasi tidak memalsukan pembayaran berhasil.

`var/config.json` berisi konfigurasi lokal untuk `panel` dan `shop`. Jangan commit, menyalin ke dokumentasi, atau membagikan file konfigurasi/kredensial. Mode `demo` hanya membuat direktori situs di `var/sites`; tidak mengubah akun Linux/Nginx dan tidak menjalankan PHP.

Menjalankan komponen sendiri:

```bash
.venv/bin/python tools/run.py panel runserver 127.0.0.1:8001
.venv/bin/python tools/run.py shop runserver 127.0.0.1:8002
.venv/bin/python tools/run.py panel provision_worker --recover
.venv/bin/python tools/run.py shop fulfill_orders
```

Untuk database baru/upgrade, jalankan `tools/run.py panel migrate --noinput` dan `tools/run.py shop migrate --noinput`. Gunakan `tools/run.py panel createsuperuser` atau `tools/run.py shop changepassword admin` untuk administrasi akun. `--recover` aman hanya ketika worker sebelumnya sudah berhenti; worker memakai file lock untuk mencegah worker kedua.

## Instalasi VPS

Ikuti [panduan VPS](docs/VPS.md). Installer memerlukan VPS **Ubuntu 24.04 baru**, akses sudo/root, IPv4 publik, dua domain, DNS yang sudah mengarah ke VPS, dan port 80/443 serta TCP/UDP 53 yang terbuka. Mulai dengan:

```bash
.venv/bin/python tools/install_vps.py --plan-only
sudo .venv/bin/python tools/install_vps.py
```

Installer interaktif meminta domain panel/toko, IP, email, nameserver utama/kedua, password admin, mode dan kredensial Tripay, serta channel merchant. Token API dan secret key dibuat acak. Sumber aplikasi disalin ke `/opt/mikapanels`; data ada di `/var/lib/mikapanels`; konfigurasi rahasia ada di `/etc/mikapanels` dan tidak ditampilkan.

## Hosting manual untuk pengujian

Login sebagai admin MikaPanels, buka `/dashboard/`, lalu pilih **Buat hosting**. Alternatifnya buka `/admin/hosting/account/add/`. Isi domain/subdomain, pemilik akun MikaPanels (pilih admin untuk tes sendiri), paket aktif, jenis statis/PHP, dan masa aktif 1–366 hari. Pembuatan ini memerlukan staff dengan izin `hosting.add_account`; pelanggan biasa tidak dapat menggunakannya.

Akun diberi external ID `MANUAL-…`, masuk antrean provisioning yang sama, dan dicatat dalam audit. Tidak ada invoice, transaksi Tripay, atau pesanan MychaHost yang dibuat. Tunggu status **Aktif**, lalu buka detail akun untuk upload/edit file. Dalam mode demo hanya direktori lokal yang dibuat; pada VPS mode sistem worker menyiapkan hosting nyata. Akun tetap ditangguhkan otomatis setelah masa aktifnya habis.

Untuk tes dengan `test.mychahost.my.id`, buat A record `test` menuju IP VPS. Untuk SSL, siapkan alias `www.test` juga, lalu pemilik memilih **Ajukan SSL** dari tab SSL setelah DNS siap.

Pada VPS yang sudah terpasang, gunakan `tools/update_vps.py` dari clone source baru. Helper menyimpan backup privat kode/config/SQLite, memasang dependensi BIND9/MariaDB, menjalankan migrasi dan collectstatic, menyegarkan hosting lama, dan memeriksa health. Environment serta kunci Tripay yang ada dipertahankan. Helper `update_manual_hosting.sh` kini mengarah ke updater lengkap agar tidak memasang template baru tanpa migrasi. Panduan: [VPS](docs/VPS.md), [DNS sendiri](docs/DNS.md), dan [fitur workspace](docs/WORKSPACE.md).

## Pembayaran Tripay

Panduan konfigurasi dan rekonsiliasi: [Tripay](docs/TRIPAY.md). Mode bawaan adalah sandbox. Merchant harus mengaktifkan channel yang dipilih. Jangan gunakan kredensial produksi di lingkungan demo publik. Callback harus dapat diakses melalui HTTPS oleh Tripay.

Alur: pelanggan membuat invoice → aplikasi membuat transaksi Tripay → gateway memanggil callback bertanda tangan → invoice menjadi `paid` → worker toko memanggil API panel → worker panel menyiapkan situs → status menjadi `active`.

Jika gateway timeout, invoice masuk `review`. Aplikasi tidak membuat transaksi kedua secara otomatis. Administrator mencocokkan referensi gateway melalui perintah `reconcile_payment` yang memverifikasi transaksi ke API Tripay. Refund memerlukan pemeriksaan admin dan tidak otomatis mengaktifkan kembali layanan.

## Pengujian

```bash
.venv/bin/python tools/test.py -q
.venv/bin/python tools/run.py panel check
.venv/bin/python tools/run.py shop check
```

Pengujian memakai database sementara. Suite mencakup callback sah/palsu/berulang, jumlah invoice, urutan status, double charge, timeout, panel offline, provisioning demo, symlink/path traversal, CSRF, isolasi pelanggan, SSO, kupon, dan tiket. HTTP Tripay dimock; suite tidak membuktikan akses merchant sungguhan.

Opsional, setelah `tools/dev.py` berjalan, jalankan `tests/browser_smoke.py` menggunakan Python dengan Playwright dan Chromium tersedia. Pengujian membuat akun/pesanan demo lokal, memeriksa desktop/mobile, checkout, tiket, provisioning API, edit file, dan SSO. Screenshot disimpan di `var/screenshots/`. `tests/browser_features.py` memeriksa editor/folder, DNS CRUD, antrean database, keamanan, SSL/statistik, notifikasi, dan profil. Tes `tests/test_live_services.py` bersifat opt-in dengan `MIKA_TEST_MYSQL_SOCKET` (socket SQL sementara, jangan produksi) dan `MIKA_TEST_BIND_ROOT` (root ekstraksi binari BIND). Tanpa variabel tersebut, dua tes layanan nyata dilaporkan skipped.

## Batas versi ini

- Hosting yang tersedia adalah statis/PHP, bukan penjualan VPS, reseller, game server, atau container terisolasi.
- DNS authoritative BIND9 dan database MariaDB tersedia. Belum ada registrasi domain, email hosting, FTP/SFTP pelanggan, PostgreSQL, phpMyAdmin, atau replikasi DNS secondary otomatis.
- File manager/backup web mendukung subfolder dengan batas ukuran. Backup seluruh server dan database SQL dioperasikan admin.
- Batas paket adalah batas upload panel dan pengaturan proses/memory PHP. Kuota disk OS, CPU, bandwidth, dan isolasi kernel perlu disiapkan terpisah.
- Perpanjangan, perubahan paket, refund, dan penghapusan akun dilakukan admin; belum ada invoice renewal otomatis. Admin dapat memperpanjang `expires_at` lalu resume akun.
- Akun Linux terpisah dan `open_basedir` PHP bukan pengganti isolasi tenant. Hosting PHP menerima kode pelanggan: lakukan hardening dan pengujian keamanan sebelum menerima pengguna yang tidak dipercaya.

Detail operasi, keamanan, dan kontrak API ada di [arsitektur](docs/ARCHITECTURE.md) dan [panduan VPS](docs/VPS.md).
