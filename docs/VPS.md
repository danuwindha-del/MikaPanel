# Instalasi dan operasi VPS

## Prasyarat

VPS Ubuntu 24.04 baru, disarankan minimal 2 vCPU, RAM 2 GB, disk 20 GB untuk pengujian. Kebutuhan produksi bergantung pada website yang dihosting. Installer khusus IPv4. Domain panel dan toko harus berbeda dan bukan domain pelanggan yang akan diprovisioning.

1. Arahkan A record domain panel dan toko ke IP publik VPS.
2. Buka port 80/443 pada firewall dan security group provider. Pertahankan SSH yang Anda gunakan. Installer tidak mengubah firewall.
3. Unggah/clone proyek, buat venv, lalu install `requirements.lock` dengan `--require-hashes` seperti README. Jika `venv` belum tersedia, pasang `python3.12-venv` melalui apt.
4. Periksa rencana: `.venv/bin/python tools/install_vps.py --plan-only`.
5. Jalankan `sudo .venv/bin/python tools/install_vps.py`. Tinjau ringkasan dan konfirmasi instalasi.

Gunakan server pengujian terlebih dahulu. Installer menginstal Nginx, PHP 8.3 FPM/CLI, Python venv, Certbot, dan CA certificates. Ia tidak menghapus aplikasi atau konfigurasi yang sudah ada; bentrok instalasi menyebabkan proses berhenti.

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

Setiap situs memperoleh user Linux `mh` + ID internal, shell `nologin`, vhost Nginx, dan pool PHP terpisah jika engine PHP. Worker memakai argumen subprocess, bukan shell dari input pelanggan. Hosting dibatasi satu domain utama dan alias `www` per akun.

Situs pelanggan awalnya HTTP. Setelah A record domain utama dan alias `www` siap, administrator membuka detail akun pada MikaPanels dan memilih **Pasang SSL**. Worker memakai Certbot webroot, menguji Nginx, lalu reload. Tombol ini tidak tersedia di demo. Konfigurasi suspend/resume mempertahankan referensi sertifikat yang sudah ada. Certbot timer OS memperbarui sertifikat, dengan deploy hook untuk reload Nginx.

## Pemeriksaan

```bash
sudo systemctl status mikapanels mychahost mika-provision mycha-orders
sudo journalctl -u mikapanels -u mychahost -n 80 --no-pager
sudo journalctl -u mika-provision -u mycha-orders -n 80 --no-pager
sudo nginx -t
sudo php-fpm8.3 -t
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

Installer berhenti pada perintah gagal dan mempertahankan data. Jangan menghapus database/konfigurasi supaya installer bisa diulang. Periksa langkah terakhir, backup direktori konfigurasi dan database, lalu lanjutkan operasi yang gagal secara manual. Misalnya kegagalan TLS akibat DNS diselesaikan dengan DNS yang benar dan mengulang perintah Certbot dari installer. Gunakan log systemd untuk kegagalan web/worker. `--plan-only` tidak membuktikan pemasangan sistem berhasil.

Worker menandai pekerjaan gagal dan menyimpan kelas error. Perbaiki prasyarat, lalu pilih retry pada akun di panel. Job `running` yang ditinggalkan saat mesin mati dikembalikan ke pending oleh startup worker `--recover`. Hanya satu worker provisioning diizinkan oleh file lock. Jika suspend/resume/SSL gagal, status akun sebelumnya dipertahankan; admin dapat mencoba tindakan lagi setelah job gagal selesai.

## Backup dan upgrade

Backup harus mencakup kedua database, `/etc/mikapanels`, `/srv/mika-hosting`, konfigurasi Nginx/PHP, dan `/etc/letsencrypt`. Gunakan SQLite backup API atau hentikan semua penulis database untuk snapshot konsisten; jangan menyalin DB hidup beserta journal yang tidak konsisten. Enkripsi backup yang mengandung konfigurasi rahasia, simpan di luar VPS, dan uji restore.

Untuk upgrade, backup terlebih dahulu, hentikan empat layanan, perbarui kode root-owned tanpa menimpa konfigurasi/data, install lock baru dengan hash, jalankan migrasi kedua service, collectstatic, pulihkan ownership database, lalu mulai layanan dan verifikasi kesehatan serta alur aplikasi. Installer fresh-install tidak menjadi perintah upgrade.

## Sebelum menerima pelanggan produksi

Pengujian cloud tidak menjalankan root installer atau transaksi merchant. Operator perlu menguji instalasi pada VPS staging, seluruh channel pembayaran merchant, callback melalui HTTPS, provisioning PHP nyata, penerbitan/renewal TLS, suspend/resume, dan restore backup. Atur kuota filesystem, batas sumber daya OS, monitoring disk, SMTP, kebijakan privasi/refund, dan isolasi untuk kode tenant yang tidak dipercaya. SQLite cocok untuk satu VPS dengan beban awal; deployment multi-server/volume transaksi tinggi memerlukan desain database dan antrean tambahan.
