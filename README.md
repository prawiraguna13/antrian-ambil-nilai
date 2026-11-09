# ⚡ Sistem Antrian Praktik Siswa (Firebase Real-Time SPA)

Aplikasi web **Single-Page Application (SPA)** berbasis **HTML5 + Tailwind CSS + Vanilla JavaScript** yang terhubung langsung ke **Google Firebase (Cloud Firestore)**. Sinkronisasi antrian, pemanggilan suara (TTS), penilaian guru, dan rekap nilai berjalan secara **real-time instan** antar-perangkat (HP, Tablet, Laptop, Layar Proyektor) di mana pun tanpa perlu server lokal.

---

## 🌐 Cara Membuka / Menjalankan Aplikasi

Aplikasi bersifat **Serverless** dan dapat dijalankan dengan cara:

### Opsi 1: Lewat GitHub Pages (Online Publik)
Aktifkan GitHub Pages di repositori:
1. Masuk ke **Settings** → **Pages** pada repositori GitHub.
2. Pilih branch `main` dan folder `/(root)`, lalu klik **Save**.
3. Akses via link: 👉 **`https://prawiraguna13.github.io/antrian-ambil-nilai/`**

### Opsi 2: Buka Langsung File HTML
Cukup buka file [`index.html`](file:///Users/kien/Documents/Web-Antrian/index.html) langsung di browser Anda. Aplikasi langsung terhubung ke database cloud Firebase!

---

## 🔒 Aturan Keamanan (Firestore Security Rules)
File [`firestore.rules`](file:///Users/kien/Documents/Web-Antrian/firestore.rules) telah disediakan untuk mengamankan data antrian di Firebase.
Salin isi file tersebut ke tab **Firestore Database** → **Rules** di Firebase Console.

---

## 🔑 Kredensial Login Admin Guru
- **Username**: `kien`
- **Password**: `123!@#`

*(Username & Password dapat diubah sewaktu-waktu di Panel Guru melalui menu **Pengaturan Akun**).*

---

## ✨ Fitur & Panduan Penggunaan

### 1. Form Pendaftaran Siswa (Tampilan Awal)
- Form input: **Nama Lengkap**, dropdown **Kelas/Jurusan**, dan dropdown **Materi Praktik**.
- Data dropdown kelas dan materi terhubung secara dinamis dengan inputan guru.
- Tombol **"Daftar Antrian"**: Ketika ditekan, muncul popup **Modal Konfirmasi Tiket** (misal: `#A-01`) dengan rincian nama, kelas, materi, dan opsi langsung melihat layar antrian.

### 2. Layar Antrian (Monitor / Proyektor)
- **Sesi Kiri/Atas**: Kartu *highlight* raksasa untuk **Siswa yang Sedang Praktik** (Nomor antrian raksasa bercahaya, Nama, Kelas, Materi, dan durasi waktu praktik).
- **Sesi Kanan/Bawah**: Daftar antrian **Menunggu Giliran**. Urutan nomor 1 memiliki lencana khusus beranimasi **"Siap Maju"**.
- **Tombol Clear Antrian**: Terletak langsung di dalam header kartu antrian menunggu (lengkap dengan modal konfirmasi aman) untuk mereset antrian.
- Jam digital real-time & tombol **Layar Penuh (Fullscreen)**.

### 3. Panel Guru (Terproteksi Login)
- **Modal Login Minimalis**: Hanya form username dan password tanpa hint atau opsi register.
- **Pengaturan Akun**: Modal untuk mengubah username dan password admin.
- **Manajemen Kelas**: Tambah kelas baru, hapus per item (*chips*), dan tombol **"Clear Semua Kelas"** di header dengan modal konfirmasi.
- **Manajemen Materi**: Tambah materi modul baru, hapus per item (*chips*), dan tombol **"Clear Semua Materi"** di header dengan modal konfirmasi.
- **Kontrol Antrian & Penilaian**: Menampilkan siswa yang sedang maju, input skor (0-100), status Lulus/Ulang (Remedial), catatan masukan, dan tombol **"Simpan & Panggil Berikutnya"**.
- **Suara Pemanggilan Otomatis (TTS)**: Web Speech Synthesis menyebutkan: *"Panggilan antrian nomor [...], atas nama [...], silakan maju."*
- **Rekap Nilai Siswa**: Tabel responsif (*horizontal scroll* di perangkat mobile).
- **Tombol "Download Excel"**: Tombol hijau emerald untuk mengunduh rekapitulasi nilai berformat `.xls` lengkap dengan header tabel rapi.

### 4. UI/UX & Tema
- **Tema Glassmorphism**: Gradien *Electric Blue* ke *Deep Purple / Indigo* dengan kartu transparan dan efek glow.
- **Dark Mode / Light Mode**: Tombol toggle (matahari/bulan) di header navigasi, tersimpan di `localStorage`.
- **Notifikasi Toast**: Pop-up toast muncul dari **bawah layar** (*bottom-right* pada desktop, *bottom-center* pada mobile) dengan animasi meluncur ke atas sehingga tidak menutupi navigasi utama.
