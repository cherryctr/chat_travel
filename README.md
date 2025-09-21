## Chat TravelGO (FastAPI + Gemini)

Proyek contoh chatbot berbasis FastAPI yang terhubung ke database TravelGO dan model Gemini. Chat dibatasi hanya menjawab berdasarkan konteks data di database dump `devwebmy_travel.sql`.

### Arsitektur Singkat
- FastAPI sebagai web framework
- SQLAlchemy untuk akses MariaDB/MySQL (tanpa migrasi; gunakan dump SQL yang diberikan)
- Auth JWT (login via email/password dari tabel `users` dengan hash bcrypt)
- Layanan Gemini dengan guardrails: hanya menjawab dari konteks DB; jika tidak ada konteks → menolak
- Struktur terpisah: `app/core`, `app/db`, `app/services`, `app/controllers`, `app/routes`

### Prasyarat
- Python 3.10+ (disarankan)
- MariaDB/MySQL berjalan lokal
- Akun Google API + API Key untuk Gemini (Models API)

### 1) Siapkan Database
1. Buat database (via MySQL/MariaDB client):
   ```sql
   CREATE DATABASE devwebmy_travel CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
2. Import dump SQL (PowerShell/CMD di folder proyek):
   ```powershell
   mysql -u root -p devwebmy_travel < devwebmy_travel.sql
   ```
   - Ganti `root` dan `-p` sesuai kredensial Anda.

### 2) Konfigurasi Environment
1. Salin `.env.example` menjadi `.env` lalu isi nilai Anda:
   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```
2. Variabel penting:
   - `DATABASE_URL` → contoh: `mysql+pymysql://root:password@127.0.0.1:3306/devwebmy_travel`
   - `GOOGLE_API_KEY` → isi API key Gemini Anda
   - `GEMINI_MODEL` → default `gemini-1.5-flash`
   - `JWT_SECRET` → ubah ke nilai acak yang kuat

> Catatan: Jika Anda tadi sudah membuat `.env` otomatis, cukup periksa ulang nilainya di file tersebut.

### 3) Buat & Aktifkan Virtual Environment (WAJIB sebelum install requirements)
- Windows (PowerShell):
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```
  Jika PowerShell memblokir eksekusi skrip:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- Windows (CMD):
  ```cmd
  python -m venv .venv
  .\.venv\Scripts\activate.bat
  ```
- Linux/macOS (bash/zsh):
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 4) Install Dependensi
```powershell
pip install -r requirements.txt
```
(Optional) upgrade pip/wheel:
```powershell
python -m pip install --upgrade pip wheel
```

### 5) Jalankan Server
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Health check:
```powershell
curl http://127.0.0.1:8000/health
```

### 6) Login (JWT)
Aplikasi menggunakan kredensial pada tabel `users`. Jika Anda belum tahu password user di DB, setel ulang password dengan membuat hash bcrypt baru lalu update tabel.

- Buat hash bcrypt dengan Python:
  ```powershell
  python -c "from passlib.hash import bcrypt; print(bcrypt.hash('admin123'))"
  ```
  Salin output hash.
- Update di DB (contoh untuk `superadmin@gmail.com`):
  ```sql
  UPDATE users SET password = '<HASH_HASIL_PYTHON>' WHERE email = 'superadmin@gmail.com';
  ```

- Minta token:
  ```powershell
  curl -X POST http://127.0.0.1:8000/auth/login ^
    -H "Content-Type: application/json" ^
    -d "{\"email\":\"superadmin@gmail.com\",\"password\":\"admin123\"}"
  ```
  Respons berisi `access_token` (Bearer).

### 7) Gunakan Endpoint Chat
- Tanpa login (umum, akses terbatas):
  ```powershell
  curl -X POST http://127.0.0.1:8000/chat ^
    -H "Content-Type: application/json" ^
    -d "{\"message\":\"Tampilkan 5 trip terbaru yang published\"}"
  ```
- Dengan login (akses info privat milik user):
  ```powershell
  $TOKEN = "<ACCESS_TOKEN>"
  curl -X POST http://127.0.0.1:8000/chat ^
    -H "Authorization: Bearer $TOKEN" ^
    -H "Content-Type: application/json" ^
    -d "{\"message\":\"Tolong tampilkan booking saya terakhir\"}"
  ```

Chat akan:
- Menolak hard-constraint jika pertanyaan sensitif (password, token, API key, dsb)
- Menolak pertanyaan di luar konteks database ini (balasan standar)
- Untuk intent privat (booking saya, riwayat), wajib login

### 7.1) Contoh Request & Response Chat

#### A) List promo (tanpa membatasi tanggal)
Request:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "list promo nya apa aja"
  }'
```
Response (contoh):
```json
{
  "reply": "Berikut beberapa promo yang tersedia.",
  "used_context_keys": ["promos.ai"],
  "suggested_actions": ["Gunakan kode WELCOME200"],
  "related_trips": [],
  "user_bookings": [],
  "related_promos": [
    {
      "name": "Welcome Bonus Rp 200.000",
      "promo_code": "WELCOME200",
      "discount_type": "amount",
      "discount_value": 200000.00,
      "start_date": "2024-01-01T00:00:00",
      "end_date": "2026-12-31T23:59:59",
      "is_active": 1
    }
  ],
  "generated_queries": [
    "SELECT name, promo_code, discount_type, discount_value, start_date, end_date, is_active FROM promos WHERE is_active = 1 ORDER BY (discount_value IS NULL) ASC, discount_value DESC LIMIT 10"
  ],
  "summary": "Permintaan: list promo nya apa aja Ada 1 promo aktif yang relevan. Jawaban: Berikut beberapa promo yang tersedia.",
  "related_collections": {
    "promos": [
      {
        "name": "Welcome Bonus Rp 200.000",
        "promo_code": "WELCOME200",
        "discount_type": "amount",
        "discount_value": "200000.00",
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2026-12-31T23:59:59",
        "is_active": 1
      }
    ]
  }
}
```

#### B) Promo hari ini (otomatis menambahkan filter tanggal)
Request:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "promo apa saja hari ini"
  }'
```
Response (contoh ringkas):
```json
{
  "reply": "Ada 2 promo aktif hari ini.",
  "generated_queries": [
    "SELECT name, promo_code, discount_type, discount_value, start_date, end_date, is_active FROM promos WHERE is_active = 1 AND start_date <= NOW() AND end_date >= NOW() ORDER BY (discount_value IS NULL) ASC, discount_value DESC LIMIT 10"
  ],
  "related_promos": [
    {"name": "Diskon Musim Panas", "promo_code": "SUMMER", "discount_type": "percent", "discount_value": 10, "start_date": "2025-06-01T00:00:00", "end_date": "2025-09-30T23:59:59", "is_active": 1},
    {"name": "Welcome Bonus Rp 200.000", "promo_code": "WELCOME200", "discount_type": "amount", "discount_value": 200000.00, "start_date": "2024-01-01T00:00:00", "end_date": "2026-12-31T23:59:59", "is_active": 1}
  ]
}
```

#### C) Cari trip (public)
Request:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "trip bali yang sedang tersedia"
  }'
```
Response (contoh ringkas):
```json
{
  "reply": "Ini beberapa trip yang cocok dengan pencarian Anda.",
  "related_trips": [
    {"id": 101, "name": "Bali Explorer 4D3N", "slug": "bali-explorer-4d3n", "location": "Bali", "duration": "4D3N", "price": 3500000.00, "status": "published", "is_active": 1}
  ],
  "generated_queries": ["SELECT id, name, slug, location, duration, price, status, is_active FROM trips WHERE is_active = 1 AND status = 'published' ORDER BY id DESC LIMIT 10"]
}
```

#### D) Info booking saya (private; wajib Bearer token)
Request:
```bash
TOKEN="<ACCESS_TOKEN>"
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "tampilkan booking saya terakhir"
  }'
```
Response (contoh ringkas):
```json
{
  "reply": "Berikut ringkasan booking terbaru Anda.",
  "user_bookings": [
    {"id": 501, "booking_code": "TG-ABC123", "trip_id": 101, "status": "confirmed", "payment_status": "paid", "customer_email": "user@example.com", "participants": 2, "total_amount": 7000000.00}
  ]
}
```

#### E) Cek booking by code (private; akan dicocokkan dengan email user login)
Request:
```bash
TOKEN="<ACCESS_TOKEN>"
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "status booking TG-ABC123"
  }'
```
Response (contoh ringkas):
```json
{
  "reply": "Booking TG-ABC123 berstatus confirmed dan sudah dibayar.",
  "user_bookings": [
    {"booking_code": "TG-ABC123", "status": "confirmed", "payment_status": "paid"}
  ],
  "used_context_keys": ["bookings.by_code"]
}
```

### 7.2) Kebijakan Jawaban: Database-First + Thematic Fallback

Bot menerapkan prioritas berikut:
- Database-First: Jika ada data dari database yang relevan, jawaban disusun berdasarkan hasil query (field seperti `related_trips`, `related_promos`, `related_collections`, dan ringkasan `summary`).
- Thematic Fallback (on-topic): Jika tidak ada data DB relevan, bot tetap menjawab secara umum namun tetap dalam tema travel (tips/rekomendasi best-practices) tanpa mengarang data spesifik dari DB. Ditandai dengan `used_context_keys` berisi `"general.ai"` atau `"thematic.ai"`.
- Off-topic: Jika topik di luar tema travel (mis. saham, kripto), bot menolak dengan pesan singkat.

Kaidah tambahan:
- Filter tanggal untuk promo hanya ditambahkan jika pengguna memintanya ("hari ini", "bulan ini", "tahun ini"). Jika tidak, query promos tidak membatasi tanggal selain `is_active = 1`.
- SQL AI dibatasi SELECT-only dan tabel whitelist.

Contoh Fallback General (intent public, DB kosong):
Request:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Trip apa yang bagus untuk saya ke Eropa"
  }'
```
Response (contoh ringkas):
```json
{
  "reply": "Untuk trip ke Eropa, pertimbangkan musim (spring/summer), durasi 10–14 hari, kombinasi kota ikonik (Paris–Rome–Barcelona) atau fokus satu negara, serta tipe pengalaman (sejarah, kuliner, alam). Tentukan budget dan waktu terbaik, lalu cek ketersediaan dan visa.",
  "used_context_keys": ["general.ai"],
  "related_trips": [],
  "related_promos": [],
  "related_collections": {}
}
```

Contoh Thematic Tips (on-topic di luar DB):
Request:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Berikan saya tips bepergian agar aman"
  }'
```
Response (contoh ringkas):
```json
{
  "reply": "- Simpan dokumen penting dan salinannya terpisah\n- Gunakan asuransi perjalanan\n- Hindari membagikan rincian rencana ke orang asing\n- Pantau barang berharga dan gunakan tas anti-maling\n- Riset area rawan dan nomor darurat lokal",
  "used_context_keys": ["thematic.ai"],
  "related_trips": [],
  "related_promos": [],
  "related_collections": {}
}
```

Contoh Off-topic (ditolak):
Request:
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Harga saham hari ini?"
  }'
```
Response (contoh ringkas):
```json
{
  "reply": "Maaf, topik di luar tema travel. Ajukan pertanyaan seputar promo, trip, itinerary, keamanan perjalanan, dsb.",
  "used_context_keys": []
}
```

### 8) Endpoint Lain
- Daftar booking milik user login:
  ```powershell
  curl http://127.0.0.1:8000/me/bookings -H "Authorization: Bearer <ACCESS_TOKEN>"
  ```

- Profil user + 10 booking terbaru:
  ```bash
  curl http://127.0.0.1:8000/me/profile -H "Authorization: Bearer <ACCESS_TOKEN>"
  ```

#### Contoh Response `/me/bookings` (ringkas)
```json
{
  "bookings": [
    {"id": 501, "booking_code": "TG-ABC123", "trip_id": 101, "status": "confirmed", "payment_status": "paid", "total_amount": 7000000.00},
    {"id": 499, "booking_code": "TG-XYZ789", "trip_id": 95, "status": "completed", "payment_status": "paid", "total_amount": 4200000.00}
  ],
  "total": 12,
  "page": 1,
  "per_page": 20
}
```

#### Contoh Response `/me/profile` (ringkas)
```json
{
  "id": 7,
  "name": "User Demo",
  "email": "user@example.com",
  "bookings": [
    {"id": 501, "booking_code": "TG-ABC123", "status": "confirmed", "payment_status": "paid"}
  ]
}
```

### Cara Kerja Pembatasan & Konteks
- Klasifikasi intent sederhana:
  - `sensitive` → selalu ditolak
  - `private` → hanya jika login; sumber data dari tabel terkait user (mis. `bookings` via `customer_email` == `users.email`)
  - `public`/`unknown` → konteks publik (mis. subset `trips` yang `published` & `is_active=1`)
- Prompt ke Gemini memaksa untuk hanya menjawab dari konteks yang diberikan. Jika tidak ada konteks relevan, bot menolak.

### Troubleshooting
- `Access denied for user 'root'@'localhost'` → periksa `DATABASE_URL`, user, password, port, dan bahwa DB berjalan.
- `GOOGLE_API_KEY belum diatur` → isi nilai pada `.env`.
- `401 Unauthorized` saat panggil endpoint privat → pastikan mengirim header `Authorization: Bearer <token>` hasil login.
- Tidak ada hasil booking padahal login sukses → pastikan email user di `users` sama dengan `customer_email` pada `bookings` Anda.

### Struktur Direktori
```
app/
  core/        # config, security (JWT)
  db/          # session/engine, ORM models
  services/    # auth, chat, gemini
  controllers/ # auth & chat controllers
  routes/      # registrasi router
```

### Catatan Keamanan
- Jangan commit `.env` ke repo publik.
- Ganti `JWT_SECRET` dengan nilai kuat di produksi.
- Batasi izin API key Gemini di Google Cloud.
