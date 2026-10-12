# DNS server sendiri dengan BIND9

MikaPanels mengelola DNS authoritative untuk **domain akun hosting pelanggan**. Installer/upgrade memasang BIND9, menonaktifkan recursion publik dan zone transfer, serta memuat zone dari `/etc/bind/mika-zones.conf`. Worker memvalidasi setiap zone dengan `named-checkzone`, memvalidasi seluruh konfigurasi/zone BIND, memastikan include benar-benar terhubung, kemudian melakukan reconfig/reload. Status published hanya diberikan setelah zonestatus dan jawaban SOA authoritative dengan serial terbaru berhasil melalui **UDP dan TCP**. File zone/config sebelumnya dipulihkan dan dicoba dimuat ulang jika validasi/pemeriksaan gagal.

Dashboard menyediakan tambah, edit, hapus, export, dan publikasi ulang A, AAAA, CNAME, MX, TXT dengan TTL dan prioritas MX. SOA/NS dasar dikelola server. Akun baru memperoleh A `@` ke IP VPS dan CNAME `www` ke domain akun. Record yang sengaja dihapus tidak dibuat ulang ketika worker memublikasikan perubahan.

Status **Diterapkan ke BIND9** berarti server lokal sudah memuat zone; delegasi domain dan firewall tetap harus benar agar Internet memakai server itu. Mode demo menghasilkan file zone lokal, tanpa menjalankan DNS server.

## Konfigurasi MychaHost

Untuk VPS Anda:

| Hostname | A record |
|---|---|
| `mychahost.my.id` | `172.236.9.185` |
| `panel.mychahost.my.id` | `172.236.9.185` |
| `ns1.mychahost.my.id` | `172.236.9.185` |
| `ns2.mychahost.my.id` | `172.236.9.185` |

Tambahkan A record `ns1` dan `ns2` pada **penyedia DNS yang saat ini melayani mychahost.my.id**. Pilih DNS only jika provider mempunyai fitur proxy/CDN. Nameserver bukan trafik HTTP yang dapat diproxy.

Nama NS yang ditampilkan installer/panel tidak otomatis membuat record A di Cloudflare atau mendaftarkan host object di registrar. Kueri A yang kosong/NXDOMAIN berarti hostname NS belum dapat ditemukan melalui IPv4; domain pelanggan belum dapat memakai NS tersebut. Contoh Cloudflare: pada zone `mychahost.my.id`, buat A `ns1` dan A `ns2` ke IP VPS, keduanya **DNS only**. Verifikasi dengan satu perintah:

```bash
dig +noall +answer @1.1.1.1 ns1.mychahost.my.id A ns2.mychahost.my.id A
```

Di pengelola/registrar domain, cari **Child nameserver / Register nameserver / Glue record**. Daftarkan `ns1.mychahost.my.id` dan `ns2.mychahost.my.id` dengan IP tersebut jika fasilitas tersedia. Glue terutama diperlukan ketika sebuah domain menggunakan nameserver di bawah domainnya sendiri. Nama menu bergantung registrar; A record dan registrasi glue adalah pengaturan berbeda.

Ketiadaan menu Child Nameserver tidak membuktikan nameserver ini tidak dapat dipakai. Contoh: `mychamain.my.id` memakai `ns1.mychahost.my.id` dan `ns2.mychahost.my.id`, yang berada di luar zone pelanggan. Alamat kedua NS dapat ditemukan melalui DNS Cloudflare untuk `mychahost.my.id`; delegasi tersebut tidak mempunyai ketergantungan melingkar yang memerlukan glue di zone pelanggan. Kebijakan pendaftaran host pada registrar/registry tetap dapat berbeda, sehingga kebutuhan registrasi host harus dibuktikan dari respons mereka, bukan disimpulkan dari menu yang tidak tersedia.

Jika perubahan NS terlihat berhasil lalu halaman registrar kembali menampilkan default, periksa delegasi langsung pada registry dengan trace. Zone yang menjawab dari VPS sendiri belum membuktikan port DNS dapat diakses dari luar: periksa UFW, firewall provider, dan uji UDP/TCP dari jaringan lain sebelum menganggap registrasi Child Nameserver sebagai penyebab. Jangan mengganti NS domain infrastruktur atau membeli server kedua hanya berdasarkan tampilan default tanpa mengetahui alasan pembaruan belum diterapkan.

**Pertahankan nameserver domain utama mychahost.my.id pada penyedia DNS sekarang.** Domain panel/toko dicadangkan oleh aplikasi dan tidak dibuat sebagai zone pelanggan. Mengganti nameserver domain utama ke BIND ini sebelum menyiapkan zone infrastrukturnya akan memutus domain toko/panel. BIND MikaPanels dipakai untuk domain pelanggan yang sudah dibuat sebagai akun hosting.

Dua nama NS pada satu IP dapat dipakai untuk pengujian, tetapi keduanya bergantung pada satu mesin. Registrar tertentu mensyaratkan IP berbeda; untuk redundansi produksi perlu server DNS kedua dan konfigurasi secondary/transfer terbatas. Versi ini belum menyiapkan replikasi ke mesin kedua.

## Buka port DNS

Buka **UDP 53 dan TCP 53 inbound** pada firewall/security group provider VPS. HTTP/HTTPS tetap membutuhkan 80/443. Jangan menutup akses SSH.

Jika UFW sudah aktif pada Ubuntu, tambahkan aturan:

```bash
sudo ufw allow 53/udp
sudo ufw allow 53/tcp
sudo ufw status
```

Installer/update tidak mengaktifkan atau mengganti firewall. Membuka UFW saja tidak mengubah firewall provider.

## Domain pelanggan

1. Buat hosting melalui checkout berbayar atau tombol admin **Buat hosting**.
2. Tunggu hosting Aktif dan buka tab **DNS**; A `@` dan CNAME `www` tersedia.
3. Pada registrar **domain pelanggan**, ganti nameserver ke `ns1.mychahost.my.id` dan `ns2.mychahost.my.id`.
4. Periksa jawaban langsung dari VPS, lalu delegasi publik. Resolver dapat menyimpan cache sesuai TTL/delegasi sebelumnya.
5. Setelah domain utama dan `www` mengarah ke VPS, buka tab **SSL** dan pilih **Ajukan SSL**.

Untuk akun berupa subdomain seperti `test.mychahost.my.id`, Anda boleh tetap memakai A `test` dan CNAME `www.test` pada penyedia DNS domain induk. Agar tab DNS MikaPanels menguasai seluruh zone subdomain tersebut, buat delegasi NS untuk `test` ke kedua nameserver pada zone induk. Mengubah record di panel tidak mengganti DNS eksternal yang belum didelegasikan.

Jika nameserver **domain induk** dipindahkan ke MikaPanels, domain induk juga harus mempunyai zone di VPS. Membuat akun `hosting.daffobotz.my.id` dan `test.daffobotz.my.id` tidak membuat zone `daffobotz.my.id`. Pada versi ini buat akun domain induk melalui hosting manual admin untuk menghasilkan zone; akun subdomain yang sudah ada tetap dipertahankan. Jangan membuat akun induk otomatis dari nama subdomain yang belum terbukti milik pengguna.

Contoh pemeriksaan, ganti `domain-pelanggan.tld` dengan domain akun:

```bash
sudo systemctl status named --no-pager
sudo named-checkconf
sudo rndc status
dig @172.236.9.185 domain-pelanggan.tld A +norecurse
dig @172.236.9.185 domain-pelanggan.tld A +tcp +norecurse
dig domain-pelanggan.tld NS
dig +trace domain-pelanggan.tld A
```

Jawaban langsung harus memiliki flag `aa` (authoritative). Jika langsung benar tetapi resolver publik salah, periksa delegasi/glue/cache. Jika VPS tidak menjawab dari luar, periksa firewall provider, port 53, dan `journalctl -u named`. Untuk domain yang sebelumnya memakai DNSSEC, perbarui/hapus DS lama pada registrar saat pindah; versi ini belum menandatangani zone dengan DNSSEC.

Untuk memeriksa delegasi dari registry dan membedakannya dari cache WHOIS/resolver, gunakan satu perintah `dig +trace domain-pelanggan.tld NS +time=3 +tries=1`. Jangan menggabungkan dua perintah dig pada satu baris: kata `dig` tambahan dapat diperlakukan sebagai nama domain dan menghasilkan REFUSED yang tidak berkaitan dengan domain pelanggan.

## Pemeriksaan dan perbaikan terarah

`sudo python3 tools/check_dns.py --domain domain-pelanggan.tld` dari source terbaru memeriksa alamat IPv4 NS, SOA UDP/TCP melalui loopback/IP VPS, dan NS pada resolver publik. Tidak ada password/kunci yang ditampilkan. Pemeriksaan dari VPS tidak menggantikan pengujian port 53 dari jaringan luar.

Jika konfigurasi/include/reload zone perlu diperbaiki, ambil clone source terbaru lalu jalankan helper khusus berikut pada instalasi Ubuntu 24.04:

```bash
bash <<'MIKA_DNS_REPAIR'
set -eu
mika_dns_source=$(mktemp -d /tmp/mikapanels-dns.XXXXXX)
git clone --depth 1 --branch main https://github.com/danuwindha-del/MikaPanel.git "$mika_dns_source/source"
sudo python3 "$mika_dns_source/source/tools/repair_dns.py"
MIKA_DNS_REPAIR
```

Helper membuat backup privat kode/config/SQLite panel, menghentikan worker, memasang patch DNS tanpa migrasi/dependency baru, menghubungkan konfigurasi BIND yang dikelola MikaPanels, restart named, dan membangun ulang zone akun yang **sudah ada**. Worker dimulai kembali. UFW hanya ditambah aturan TCP/UDP 53 bila sudah aktif; helper tidak mengaktifkan/reset firewall dan tidak mengubah firewall provider. Akun Linux, website, invoice, Tripay, dan registrar/Cloudflare tidak diubah. Konfigurasi BIND khusus yang belum dikelola MikaPanels ditolak untuk integrasi manual.

Perintah `rebuild_dns --domain DOMAIN` dapat memublikasikan ulang satu domain yang sudah ada; hentikan `mika-provision` terlebih dahulu karena perintah memakai lock worker yang sama. Domain yang belum ada tidak dibuat atau ditagihkan secara otomatis.

## Mengubah nameserver panel

Admin mengatur `MIKA_DNS_PRIMARY` dan `MIKA_DNS_SECONDARY` di `/etc/mikapanels/panel.env`, kemudian restart `mikapanels` dan `mika-provision`. Nama harus hostname yang valid. Publikasikan ulang setiap zone dari tab DNS. Pengaturan ini tidak otomatis mengubah registrar atau A/glue eksternal.
