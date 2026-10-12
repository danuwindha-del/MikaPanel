# Instalasi dan operasi VPS

## Prasyarat

VPS Ubuntu 24.04 baru, disarankan minimal 2 vCPU, RAM 2 GB, disk 20 GB untuk pengujian. Kebutuhan produksi bergantung pada website yang dihosting. Installer khusus IPv4. Domain panel dan toko harus berbeda dan bukan domain pelanggan yang akan diprovisioning.

1. Arahkan A record domain panel dan toko ke IP publik VPS.
2. Buka port 80/443 serta TCP/UDP 53 pada firewall dan security group provider. Pertahankan SSH yang Anda gunakan. Installer tidak mengubah firewall.
3. Unggah/clone proyek, buat venv, lalu install `requirements.lock` dengan `--require-hashes` seperti README. Jika `venv` belum tersedia, pasang `python3.12-venv` melalui apt.
4. Periksa rencana: `.venv/bin/python tools/install_vps.py --plan-only`.
5. Jalankan `sudo .venv/bin/python tools/install_vps.py`. Tinjau ringkasan dan konfirmasi instalasi.

Gunakan server pengujian terlebih dahulu. Installer menginstal Nginx, PHP 8.3 FPM/CLI/MySQL, MariaDB, BIND9, Python venv, Certbot, dan CA certificates. Ia tidak menghapus aplikasi atau konfigurasi yang sudah ada; bentrok instalasi menyebabkan proses berhenti.

Password admin dibuat baru untuk panel/toko, minimal 12 karakter, bukan hanya angka, dan bukan password umum. Saat diketik, karakter tidak ditampilkan. Jika password ditolak atau konfirmasi berbeda, installer menjelaskan alasannya dan meminta ulang pada tahap password, sebelum memasang komponen sistem.

## Hasil instalasi

| Lokasi/layanan | Fungsi |
|---|---|
| `/opt/mikapanels` | Kode dan venv, dimiliki root |
| `/etc/mikapanels/panel.env` | Konfigurasi panel, root:mika 0640 |
| `/etc/mikapanels/shop.env` | Konfigurasi toko dan Tripay, root:mika 0640 |
| `/var/lib/mikapanels/panel` | Database dan static panel |
| `/var/lib/mikapanels/shop` | Database dan static toko |
| `/srv/mika-hosting/mh…/public` | Dokumen website pelanggan |
| `mikapanels.service` | Gunicorn panel, user mika, loopback 8001 |
| `mychahost.service` | Gunicorn toko, user mika, loopback 8002 |
| `mika-provision.service` | Worker root untuk akun Linux/Nginx/PHP/Certbot |
| `mycha-orders.service` | Worker toko, user mika, retry pesanan berbayar |
| `named.service` | DNS authoritative BIND9, zone /etc/bind/mika-zones |
| `mariadb.service` | Database pelanggan dengan socket lokal |

Setiap situs memperoleh user Linux `mh` + ID internal, shell `nologin`, vhost Nginx, dan pool PHP terpisah jika engine PHP. Worker memakai argumen subprocess, bukan shell dari input pelanggan. Hosting dibatasi satu domain utama dan alias `www` per akun.

Situs pelanggan awalnya HTTP. Setelah A record domain utama dan alias `www` siap, pemilik membuka tab SSL pada MikaPanels dan memilih **Ajukan SSL**. Worker memakai Certbot webroot, menguji Nginx, lalu reload. Tombol ini tidak tersedia di demo. Konfigurasi suspend/resume mempertahankan referensi sertifikat yang sudah ada. Certbot timer OS memperbarui sertifikat, dengan deploy hook untuk reload Nginx.

## Membuat hosting tanpa pembayaran

Admin membuka dashboard panel dan menekan **Buat hosting**, atau menggunakan halaman `/admin/hosting/account/add/`. Isi domain, pemilik akun panel, paket aktif, jenis website, dan masa aktif. Untuk pengujian sendiri pilih akun admin sebagai pemilik. Pengguna biasa dan staff tanpa izin membuat akun hosting tidak memiliki akses pembuatan.

Pembuatan manual menghasilkan akun queued, satu job create, serta audit `hosting.manual.create`. Tidak ada invoice atau perubahan status pembayaran. Tunggu worker `mika-provision` menyelesaikan job dan akun berubah Aktif, lalu buka detail akun dan file manager. Domain/subdomain serta SSL tetap perlu konfigurasi DNS yang benar. Akun manual tidak muncul sebagai order MychaHost; pengelolaannya langsung melalui panel.

Untuk contoh domain `test.mychahost.my.id`, buat A record `test` ke `172.236.9.185`; jika akan memasang SSL, buat CNAME `www.test` ke `test.mychahost.my.id`. Setelah provisioning dan DNS siap, website awal dapat diuji melalui HTTP, kemudian pasang SSL melalui tindakan admin.

## Pembaruan desain dan fitur workspace

Jika source lama berasal dari ZIP atau folder instalasi tidak memiliki `.git`, ambil source terbaru melalui clone baru. Jalankan di VPS:

```bash
bash <<'MIKA_UPDATE'
set -eu
mika_update_dir=$(mktemp -d /tmp/mikapanels-update.XXXXXX)
git clone --depth 1 --branch main https://github.com/danuwindha-del/MikaPanel.git "$mika_update_dir/source"
sudo python3 "$mika_update_dir/source/tools/update_vps.py"
MIKA_UPDATE
```

Helper menyimpan backup privat kode, konfigurasi, database SQLite konsisten, dan venv lama ke `/var/backups/mikapanels-…` (direktori 0700). Ia menyiapkan dependensi baru dengan SHA256 lock sebelum menghentikan layanan, kemudian memperbarui kode, menjalankan migrasi kedua service, collectstatic, konfigurasi BIND9/MariaDB, dan health HTTPS. File website, konfigurasi Tripay, password admin, serta secret key lama dipertahankan. Hosting lama mendapat job refresh/DNS. Pembaruan memerlukan downtime singkat; jangan menjalankan dua updater sekaligus.

`python3 tools/update_vps.py --plan-only` hanya menampilkan operasi. Root updater hanya mendukung Ubuntu 24.04 dan instalasi `/opt/mikapanels` yang dibuat installer. Ia menolak konfigurasi BIND khusus yang belum diintegrasikan; tidak mengambil alih zone DNS lain. Script `update_manual_hosting.sh` merupakan alias updater lengkap.

Sesudah pembaruan, ikuti [DNS](DNS.md) untuk A/glue `ns1`/`ns2`, port 53, dan delegasi domain pelanggan. Profil, statistik, file manager baru, database, SSL, serta keamanan dijelaskan di [Workspace](WORKSPACE.md). Migrasi juga diperlukan untuk halaman notifikasi MychaHost.

Untuk masalah nameserver gunakan `tools/check_dns.py --domain DOMAIN` dan helper khusus `tools/repair_dns.py` dari clone terbaru, sesuai [perbaikan DNS](DNS.md#pemeriksaan-dan-perbaikan-terarah). Helper DNS tidak melakukan pembaruan aplikasi penuh atau migrasi, dan tidak mengubah Cloudflare/registrar.

## Pemeriksaan

```bash
sudo systemctl status mikapanels mychahost mika-provision mycha-orders named mariadb
sudo journalctl -u mikapanels -u mychahost -n 80 --no-pager
sudo journalctl -u mika-provision -u mycha-orders -n 80 --no-pager
sudo nginx -t
sudo php-fpm8.3 -t
sudo named-checkconf
sudo rndc status
```

Periksa `/health/` kedua domain melalui HTTPS, login admin, buat akun pelanggan, dan uji sandbox Tripay. Konfigurasi secure cookie dan HTTPS aktif saat `MIKA_DEBUG=0`. Jangan bind Gunicorn ke publik atau menerima `X-Forwarded-Proto` dari proxy selain Nginx yang dikelola.

MikaPanels dan MychaHost memakai secret key dan database terpisah. Saat menjalankan perintah manajemen produksi, muat environment service terkait tanpa mencetak nilai. Contoh shell root:

```bash
sudo -i
set -a
. /etc/mikapanels/shop.env
set +a
cd /opt/mikapanels
.venv/bin/python manage.py check --deploy
```

File environment menggunakan nilai berpetik dan tidak berisi ekspansi shell. Jangan aktifkan `set -x`, dump environment, atau menyalin konfigurasi ke log/tiket. Setelah perubahan konfigurasi, restart layanan terkait. Jika menjalankan migrasi sebagai root, pulihkan owner `mika:mika` dan izin group-write database/journal sebelum web berjalan.

## Pemulihan instalasi yang terhenti

Jika updater berhenti pada `Health panel belum sesuai`, kode dan migrasi mungkin sudah terpasang: pemeriksaan itu berjalan setelah layanan dimulai. Jangan langsung menjalankan ulang upgrade atau menghapus data. Pada versi terbaru, pemeriksaan menyebutkan apakah Gunicorn lokal gagal, atau aplikasi lokal sehat tetapi HTTPS domain gagal.

Untuk diagnosis tanpa memperbarui instalasi, gunakan `sudo python3 tools/check_vps.py` dari clone source terbaru. Script hanya membaca environment secara privat dan memeriksa systemd, HTTP Gunicorn dengan Host/forwarded HTTPS yang benar, TLS Nginx melalui loopback dengan SNI/verifikasi sertifikat tetap aktif, serta HTTPS domain. Ia tidak menampilkan kunci atau isi respons error.

Gunicorn gagal → periksa log layanan panel/toko. Gunicorn sehat tetapi Nginx lokal HTTP 502 → periksa proxy/upstream Nginx. Kegagalan verifikasi TLS → periksa sertifikat/hostname/chain/waktu server. Nginx TLS lokal sehat tetapi HTTPS domain gagal → periksa resolusi domain, A/AAAA, firewall provider, dan akses VPS ke IP publiknya sendiri. Endpoint lokal saja tidak membuktikan domain dapat diakses publik; pemeriksaan domain tetap diwajibkan oleh updater.

Installer berhenti pada perintah gagal dan mempertahankan data. Jangan menghapus database/konfigurasi supaya installer bisa diulang. Periksa langkah terakhir, backup direktori konfigurasi dan database, lalu lanjutkan operasi yang gagal secara manual. Misalnya kegagalan TLS akibat DNS diselesaikan dengan DNS yang benar dan mengulang perintah Certbot dari installer. Gunakan log systemd untuk kegagalan web/worker. `--plan-only` tidak membuktikan pemasangan sistem berhasil.

Worker menandai pekerjaan gagal dan menyimpan kelas error. Perbaiki prasyarat, lalu pilih retry pada akun di panel. Job `running` yang ditinggalkan saat mesin mati dikembalikan ke pending oleh startup worker `--recover`. Hanya satu worker provisioning diizinkan oleh file lock. Jika suspend/resume/SSL gagal, status akun sebelumnya dipertahankan; admin dapat mencoba tindakan lagi setelah job gagal selesai.

## Backup dan upgrade

Backup harus mencakup kedua database, `/etc/mikapanels`, `/srv/mika-hosting`, konfigurasi Nginx/PHP/BIND, `/etc/letsencrypt`, dan dump SQL database pelanggan MariaDB. Gunakan SQLite backup API atau hentikan semua penulis database untuk snapshot konsisten; jangan menyalin DB hidup beserta journal yang tidak konsisten. Enkripsi backup yang mengandung konfigurasi rahasia, simpan di luar VPS, dan uji restore.

Untuk upgrade, backup terlebih dahulu, hentikan empat layanan, perbarui kode root-owned tanpa menimpa konfigurasi/data, install lock baru dengan hash, jalankan migrasi kedua service, collectstatic, pulihkan ownership database, lalu mulai layanan dan verifikasi kesehatan serta alur aplikasi. Gunakan helper upgrade di atas; installer fresh-install tidak menjadi perintah upgrade. Jika upgrade berhenti, periksa backup dan keluaran terakhir. Jangan langsung menjalankan installer atau menghapus `.venv-update` tanpa pemeriksaan. Rollback migrasi memerlukan pasangan kode/SQLite/environment dari backup yang sama; menghentikan semua penulis sebelum restore mencegah data rusak. Venv lama harus dikembalikan ke `/opt/mikapanels/.venv` agar shebang sesuai.

## Sebelum menerima pelanggan produksi

Pengujian cloud tidak menjalankan root installer atau transaksi merchant. Operator perlu menguji instalasi pada VPS staging, seluruh channel pembayaran merchant, callback melalui HTTPS, provisioning PHP nyata, penerbitan/renewal TLS, suspend/resume, dan restore backup. Atur kuota filesystem, batas sumber daya OS, monitoring disk, SMTP, kebijakan privasi/refund, dan isolasi untuk kode tenant yang tidak dipercaya. SQLite cocok untuk satu VPS dengan beban awal; deployment multi-server/volume transaksi tinggi memerlukan desain database dan antrean tambahan.
