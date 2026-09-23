# Smart CCTV AI — Demo Offline (Backup Presentasi)

Replika aplikasi **Smart CCTV AI** dalam **satu file HTML**, untuk dipakai
kalau server target (`192.168.56.199`) tidak bisa diakses saat demo.

## Cara pakai

Buka `index.html` di browser manapun (Chrome/Edge/Firefox).
Tidak perlu server, tidak perlu internet, tidak perlu login ke Keycloak.

1. Di layar masuk, pilih peran (**Admin / Supervisor / Operator**) —
   untuk memperlihatkan perbedaan hak akses (RBAC).
2. Klik **Masuk**.

## Yang bisa didemokan

| Halaman | Interaksi |
|---|---|
| **Dashboard** | KPI, tren mingguan, area terbanyak, live alert feed (auto-update) |
| **APD / Vehicle Detection** | Grid kamera "live" (timestamp jalan), klik tile → tampilan penuh, tabel riwayat, klik baris → modal |
| **Modal Alert/Kasus** | Promosikan alert → kasus, ganti status (Baru→Diproses→Selesai), assign ke operator, tambah catatan |
| **Case Violation** | Filter Semua/APD/Vehicle/Kasus Terbuka |
| **Laporan & Analitik** | Filter rentang tanggal (maks 31 hari) / 7-30 hari, KPI, distribusi, tren, tabel per kamera, tombol "Unduh PDF" (toast) |
| **Pengaturan** (Admin) | Daftar & edit kamera |
| **Manajemen User** (Admin) | Daftar user, tambah user, aktif/nonaktif |
| **RBAC** | Operator tidak melihat menu Pengaturan/Manajemen User; tidak bisa assign/tutup kasus |

## Catatan

- **Semua data dummy.** Pelanggaran, kamera, dan user tidak nyata.
- **Deteksi AI disimulasikan** — alert baru muncul otomatis tiap ~9 detik.
- **Tampilan kamera** dibuat dari grafik (SVG), bukan video CCTV asli.
- **Tidak menyimpan apa pun** — refresh halaman mengembalikan ke kondisi awal.
- Styling = `apps/frontend/styles.css` yang asli (diinline), jadi tampilannya
  identik dengan aplikasi sebenarnya.

Tidak dipakai/di-deploy oleh `docker-compose` — folder ini terpisah dari
aplikasi utama.
