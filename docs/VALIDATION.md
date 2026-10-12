# Validasi lingkungan pengembangan

Hasil pada cloud, Python 3.12:

- Instalasi dependency lock dengan `--require-hashes --force-reinstall`: berhasil. Hash diperoleh dari metadata distribusi PyPI, bukan diubah untuk melewati kegagalan verifikasi.
- Migrasi kedua database, katalog awal, admin lokal, dan collectstatic: berhasil.
- Seed/configure berulang mempertahankan konfigurasi dan perubahan katalog.
- `check` kedua service: tidak ada isu.
- `makemigrations --check --dry-run`: tidak ada perubahan model yang belum dimigrasi.
- Suite standar terbaru: **112 passed, 4 skipped**; skip adalah empat kasus BIND/MariaDB opt-in. Tiga kasus BIND nyata dijalankan terpisah: **3 passed**, mencakup query dasar, pipeline publication/reconfig, dan include yang tidak terhubung. Pengujian MariaDB nyata sebelumnya berhasil; server SQL sementara tidak dijalankan pada pemeriksaan ulang DNS ini.
- Hosting manual: dashboard dan form add Django admin membuat akun queued/job/audit tanpa order pembayaran; worker demo mengaktifkan akun dan membuat file website. Pelanggan/staff tanpa izin, request tanpa CSRF, domain/masa aktif/engine yang tidak valid, dan pilihan paket/pemilik nonaktif ditolak. Pengulangan submit tidak membuat job ganda; kegagalan penulisan antrean me-rollback akun.
- Checkout berbayar: respons gateway fixture menghasilkan redirect langsung ke URL Tripay; permintaan berulang tetap tidak membuat charge kedua. Perintah pemeriksaan channel menguji konfigurasi kosong, channel aktif/tidak aktif, dan penolakan autentikasi tanpa menampilkan nilai kredensial.
- Preflight password installer: password pendek/numerik dan konfirmasi berbeda diminta ulang tanpa mencetak password. Pengujian standalone tanpa konfigurasi service juga berhasil, tanpa perubahan sistem.
- Browser Chromium pada desktop 1440 px dan ponsel 390 px: halaman depan dan paket tampil, tidak ada overflow horizontal. Daftar akun, checkout/invoice, tiket, API provisioning demo, login admin, edit file, dan SSO sekali pakai antar aplikasi berhasil.
- Browser hosting manual: tombol dashboard/form admin tersedia, form mobile tidak melebar, akun manual diaktifkan worker demo, dan file website dapat diedit. Updater lengkap lulus pemeriksaan syntax/rencana dan tes konfigurasi/idempotensi/preservasi environment; perubahan sistem VPS belum dieksekusi di cloud.
- Browser workspace baru: folder bertingkat, file save/reopen, editor sintaks dan nomor baris, sidebar mobile buka/tutup, DNS tambah/edit, database demo diantrekan, aturan blokir IP, halaman SSL/statistik, notifikasi, dan profil berhasil; tidak ada JavaScript pageerror atau overflow halaman.
- MariaDB **11.8.6** rootless dengan socket lokal sementara (tanpa jaringan): pembuatan schema/user dan tabel, isolasi database lain termasuk pola underscore GRANT, rotasi password (password lama ditolak), penghapusan schema/user, dan pengembalian slot idempotent berhasil.
- BIND **9.20.26** rootless pada port lokal acak: render zone lolos named-checkzone/named-checkconf; jawaban authoritative A, AAAA, CNAME, MX, dan TXT UTF-8/quote diuji. Pipeline publication memanggil RNDC nyata untuk reconfig/reload/zonestatus dan memverifikasi SOA serta A melalui **UDP dan TCP**; serial meningkat saat update. Include yang tidak terhubung ditolak, metadata tidak mengklaim published, dan kegagalan verifikasi memulihkan file serta record sebelumnya melalui RNDC. Binari layanan berasal dari paket Debian resmi dengan metadata apt bertanda tangan; tidak dipasang sebagai daemon sistem. Ubuntu produksi memakai versi paket distributornya sendiri.
- Diagnostik DNS menandai A nameserver yang kosong/NXDOMAIN atau alamat proxy yang berbeda dari VPS. Helper perbaikan terarah lulus pemeriksaan syntax/rencana; perilaku UFW diuji agar hanya menambah TCP/UDP 53 saat firewall sudah aktif, tanpa enable/reset.
- Paket Python **23 dependency** dipasang ulang dengan hash dan TLS terverifikasi, termasuk cryptography/PyMySQL.
- Script setup cloud terbaru dieksekusi penuh dan berulang: dependency lock, migrate, seed, collectstatic, check, initialize_features, lalu suite standar berhasil.
- Supervisor lokal: kedua web dan worker berjalan, endpoint health memverifikasi koneksi database.
- `install_vps.py --plan-only`: berhasil dan tidak mengubah sistem.
- Dokumentasi resmi Tripay: HTTP 200, adapter mengikuti contoh form encoding dan field respons/callback.

Yang belum dieksekusi: root installer/updater pada Ubuntu 24.04 nyata, BIND publik/glue/delegasi/firewall provider, akun Linux/Nginx/PHP-FPM produksi, request pembayaran dengan kredensial merchant, callback yang dikirim Tripay sungguhan, Certbot penerbitan/renewal TLS, serta restore backup VPS. Mock dan provisioning demo tidak menggantikan pemeriksaan tersebut.

Screenshot pengujian lokal ada di `var/screenshots/`; file runtime/credential/log tidak termasuk arsip source. Panduan penerapan ada di VPS.md dan TRIPAY.md.
