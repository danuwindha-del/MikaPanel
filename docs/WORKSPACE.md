# Workspace MikaPanels

Tema baru memakai navy, emas, kartu terang, gauge performa, grafik, dan sidebar responsif. Brand toko tetap MychaHost; brand panel tetap MikaPanels. Menu samping memilih website terlebih dahulu agar tindakan diterapkan pada akun yang tepat. Pelanggan melihat miliknya; staff dapat mengelola semua akun.

## Pengelola file

Pilih **Pengelola File → website**. Buat folder/file, jelajahi subfolder, cari nama, ubah nama, download, upload, atau hapus file/folder kosong. Klik **Edit** untuk editor kode dengan sorotan sintaks, nomor baris, indent Tab, dan Ctrl/Cmd+S. Editor mendukung teks UTF-8; file biner dapat diupload/download.

Upload/edit per file maksimal 10 MB. Ekstraksi ZIP maksimal 10 MB arsip, 50 MB setelah ekstraksi, dan 1000 entri; path traversal, symlink, file khusus, dan arsip terenkripsi ditolak. Bila sebuah penulisan gagal (misalnya kuota), ekstraksi yang sudah berjalan dapat meninggalkan file sebelumnya; periksa hasil sebelum mencoba ulang. Backup ZIP meliputi subfolder/file reguler, maksimal 50 MB/5000 file, tanpa database SQL. Hapus folder membutuhkan folder kosong. Rename tidak menimpa file tujuan.

Nama memakai huruf/angka/titik/underscore/hyphen, termasuk dotfile seperti `.htaccess`. Webserver Nginx **tidak membaca aturan .htaccess**; rewrite aplikasi membutuhkan konfigurasi Nginx admin. File sensitif yang diawali titik ditolak melalui HTTP. Operasi panel menolak symlink dan hardlink file; semua segmen folder dibuka dengan `O_NOFOLLOW`.

## Database MariaDB

Pada hosting Aktif, buka **Database**. Isi nama singkat dan password kuat minimal 12 karakter, lalu antrekan pembuatan. Worker membuat schema dan user unik dengan hak pada schema itu saja. Gunakan **hostname localhost**, nama schema dan username yang ditampilkan, serta password yang Anda buat pada konfigurasi PHP. Password disimpan dengan Fernet, menggunakan kunci turunan `MIKA_SECRET_KEY` panel; tidak ditampilkan kembali.

Anda dapat mengganti password dan menghapus database dari panel. Penghapusan menghapus seluruh tabel/data; lakukan backup SQL terlebih dahulu. Slot paket diatur admin lewat `Plan.database_limit` (bawaan 3). Kegagalan dapat dicoba ulang. Mode demo menampilkan state `demo`, tanpa membuat server SQL.

Pada VPS, MariaDB menerima koneksi lokal; port 3306 tidak perlu dibuka ke Internet. Root worker memakai socket `/run/mysqld/mysqld.sock` dan autentikasi Unix root bawaan Ubuntu. Jangan mengubah `MIKA_SECRET_KEY` tanpa rencana migrasi ciphertext; perubahan itu membuat password tersimpan lama tidak dapat didekripsi. Backup SQLite panel beserta environment secara privat.

## SSL dan keamanan

Pemilik hosting aktif dapat meminta SSL Let's Encrypt setelah domain utama dan www menunjuk VPS. Worker menerbitkan sertifikat, mengaktifkan redirect HTTPS, dan menyimpan masa berlaku yang dibaca dari sertifikat. Timer Certbot memperbarui sertifikat dan hook me-reload Nginx. Mode demo tidak menerbitkan SSL.

Tab **Keamanan** mengatur redirect HTTPS (memerlukan sertifikat aktif), daftar isi direktori (mati secara default), header nosniff/SAMEORIGIN, serta blokir IP/CIDR. Perubahan diterapkan lewat job refresh Nginx. Aturan merupakan aturan website, bukan firewall VPS. Jika memakai proxy/CDN, Nginx dapat melihat IP proxy; admin perlu konfigurasi real IP yang benar sebelum memakai blokir IP pengunjung.

## Statistik dan akun

Dashboard mengambil CPU/RAM/disk/jaringan dari Linux setiap sekitar 30 detik melalui worker. Gauge bandwidth dibandingkan dengan puncak laju yang terukur, bukan kuota paket. Data ini mencakup seluruh VPS; bukan pemakaian proses per tenant. Nilai awal yang belum bisa dihitung ditampilkan kosong. Buka ulang halaman untuk data terbaru.

Statistik website menghitung ukuran file dan jumlah request/error/byte respons dari access log Nginx terpisah. Grafik menyediakan rentang 1/6/24 jam; sampel disimpan dua hari, total trafik bertambah sejak collector aktif. Rotasi log dideteksi dengan inode/offset sehingga log yang sama tidak dihitung ulang. Mode demo tanpa log Nginx menampilkan trafik nol secara eksplisit.

Notifikasi mencatat hasil pekerjaan hosting milik pengguna, serta aktivasi hosting di MychaHost. Tombol tandai dibaca hanya mengubah notifikasi pemilik yang login. Profil mengubah nama tampilan dan password dengan pemeriksaan password lama. Akun pelanggan panel yang dibuat oleh SSO masuk lewat MychaHost; pengubahan password akun toko dilakukan di profil toko.
