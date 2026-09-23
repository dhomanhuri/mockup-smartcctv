# Smart CCTV AI — Kredensial Login (Demo/POC)

Server: `192.168.56.199` &middot; Semua kredensial di bawah juga ada di
[`.env`](../../.env) dan [`infra/keycloak/import/realm-smart-cctv-ai.json`](../../infra/keycloak/import/realm-smart-cctv-ai.json).
**Ini kredensial demo — rotasi semuanya sebelum dipakai produksi sungguhan.**

Semua password di bawah sengaja disamakan jadi satu (`busDev123!`) untuk
kemudahan demo — lihat [ADR-0016](../architecture/adr/0016-env-driven-internal-slug-and-simple-credentials.md).

---

## 1. Dashboard — 3 role (ADR-0011)

URL: **http://192.168.56.199/**

| Role | Username | Password | Bisa apa |
|---|---|---|---|
| Operator | `operator` | `busDev123!` | Lihat semua halaman kecuali Pengaturan; acknowledge kasus (Baru → Diproses); **tidak bisa** assign/menutup kasus |
| Supervisor | `supervisor` | `busDev123!` | Semua hak Operator + assign kasus ke petugas + menutup kasus (Selesai); **tidak bisa** buka Pengaturan |
| Admin | `admin` | `busDev123!` | Semua hak Supervisor + Pengaturan (kelola kamera, Aturan Notifikasi) + Admin Dashboard |

Satu realm (`smart-cctv-ai`) untuk ketiganya — role yang membedakan, bukan
realm terpisah. Enforcement ada di backend (`apps/backend/app/auth.py`),
bukan cuma disembunyikan di UI — coba assign/close kasus sebagai
`operator` dan itu akan ditolak 403 meski request langsung ke API.

---

## 2. Admin Dashboard (kelola user)

URL: **http://192.168.56.199/admin.html**

| Username | Password |
|---|---|
| `admin` | `busDev123!` |

Realm & login sama dengan dashboard operator (satu realm `smart-cctv-ai`) —
akun ini punya role tambahan `admin` sehingga bisa membuka `/admin.html`
untuk melihat, menambah, dan menonaktifkan user Smart CCTV AI. User biasa
(`operator`) tidak bisa membuka halaman ini (akan muncul "Akses ditolak").

---

## 3. Console Admin Keycloak (native, master realm)

URL: **http://192.168.56.199:8081/auth/admin/**

| Username | Password |
|---|---|
| `kcadmin` | `busDev123!` |

Ini akun **master admin Keycloak itu sendiri** — terpisah total dari user
di realm `smart-cctv-ai`, dan sengaja hanya bisa diakses lewat port `8081`
(diblok kalau lewat port 80 / domain utama aplikasi). Dipakai untuk
konfigurasi Keycloak tingkat infrastruktur (bikin realm baru, lihat sesi
aktif, dsb) — bukan untuk kerja sehari-hari kelola user (pakai Admin
Dashboard di atas untuk itu).

---

## Kredensial teknis lain (bukan untuk login manusia)

| Nama | Nilai | Kegunaan |
|---|---|---|
| `smart-cctv-ai-user-manager` (client secret) | lihat `KC_USER_MANAGER_SECRET` di `.env` | Service account backend untuk memanggil Keycloak Admin API |
| Postgres app | `smart_cctv_ai` / `busDev123!` | Database kamera & pelanggaran |
| Postgres Keycloak | `keycloak` / `busDev123!` | Database internal Keycloak |

Client secret di atas sengaja TIDAK disamakan ke `busDev123!` — itu bukan
password yang diketik manusia, jadi tetap dibiarkan sebagai string acak
(lihat komentar di `.env`).

---

## Akses lain (tanpa login)

| Layanan | URL |
|---|---|
| Email demo (Mailpit) | http://192.168.56.199:8025 |
