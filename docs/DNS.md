# DNS server sendiri dengan BIND9

MikaPanels mengelola DNS authoritative untuk **domain akun hosting pelanggan**. Installer/upgrade memasang BIND9, menonaktifkan recursion publik dan zone transfer, serta memuat zone dari `/etc/bind/mika-zones.conf`. Worker memvalidasi setiap zone dengan `named-checkzone`, memvalidasi konfigurasi dengan `named-checkconf`, kemudian memanggil `rndc reload`. Konfigurasi zone sebelumnya dipulihkan jika validasi/reload gagal.

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

Di pengelola/registrar domain, cari **Child nameserver / Register nameserver / Glue record**. Daftarkan `ns1.mychahost.my.id` dan `ns2.mychahost.my.id` dengan IP tersebut jika fasilitas tersedia. Glue terutama diperlukan ketika sebuah domain menggunakan nameserver di bawah domainnya sendiri. Nama menu bergantung registrar; A record dan registrasi glue adalah pengaturan berbeda.

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

## Mengubah nameserver panel

Admin mengatur `MIKA_DNS_PRIMARY` dan `MIKA_DNS_SECONDARY` di `/etc/mikapanels/panel.env`, kemudian restart `mikapanels` dan `mika-provision`. Nama harus hostname yang valid. Publikasikan ulang setiap zone dari tab DNS. Pengaturan ini tidak otomatis mengubah registrar atau A/glue eksternal.
