# MarkItDown Telegram Bot Gateway (Docker)

Gateway bot Telegram yang mengonversi berbagai format dokumen (**DOCX, XLSX, PDF, PPTX, CSV, HTML, TXT**) serta **gambar/foto (OCR)** menjadi format **Markdown (`.md`)** menggunakan pustaka Microsoft MarkItDown dan Tesseract OCR.

Semua layanan telah dikemas dalam **Docker**, sehingga mudah diuji coba dan siap dipindahkan/dideploy ke perangkat atau server lain tanpa perlu instalasi rumit.

---

## 🌟 Fitur Utama

1. **Dukungan Format Dokumen Lengkap**:
   - Microsoft Word (`.docx`)
   - Microsoft Excel (`.xlsx`)
   - Microsoft PowerPoint (`.pptx`)
   - Adobe PDF (`.pdf`)
   - Web & Teks (`.html`, `.csv`, `.tsv`, `.json`, `.xml`, `.txt`)

2. **Dukungan OCR Gambar (Offline & Lokal)**:
   - Terintegrasi langsung dengan **Tesseract OCR** di dalam Docker image.
   - Mendukung bahasa **Indonesia (`ind`)** dan **Inggris (`eng`)**.
   - Kirim foto/gambar (`.png`, `.jpg`, `.jpeg`, `.webp`), dan bot akan mengekstrak teksnya ke format Markdown.
   - *(Opsional)* Mendukung vision LLM (OpenAI API) jika ingin deskripsi gambar berbasis AI.

3. **Multi-File Batching Cerdas**:
   - Telegram mengirim banyak file sebagai pesan terpisah yang beruntun.
   - Bot memiliki sistem **Debounce Batcher** otomatis: saat Anda mengirim 2, 5, atau 10 file sekaligus, bot akan mengumpulkannya dan mengonversinya secara bersamaan.

4. **Deteksi Otomatis ZIP**:
   - **Input ZIP**: Jika Anda mengirim file `.zip`, bot otomatis mengekstrak dokumen di dalamnya dan mengonversi semuanya.
   - **Output Pintar**:
     - Jika hasil konversi **hanya 1 file**: Dikirim langsung sebagai file `.md` (beserta cuplikan teks di chat).
     - Jika hasil konversi **lebih dari 1 file** (dari multi-upload atau dari arsip zip): Otomatis dikemas rapi menjadi satu file `converted_markdowns.zip`.

---

## 🚀 Cara Menjalankan dengan Docker (Rekomendasi)

### Langkah 1: Buat Bot di Telegram & Dapatkan Token
1. Buka Telegram dan cari [@BotFather](https://t.me/BotFather).
2. Ketik `/newbot`, lalu ikuti instruksi (beri nama dan username bot).
3. Salin token API yang diberikan (contoh: `7123456789:AAH...`).

### Langkah 2: Konfigurasi Environment
Salin file `.env.example` menjadi `.env`:
```bash
cp .env.example .env
```
Buka file `.env` dan masukkan token bot Anda:
```env
TELEGRAM_BOT_TOKEN=7123456789:AAH...
```

### Langkah 3: Build & Jalankan Kontainer
Cukup jalankan perintah berikut di direktori proyek:
```bash
docker compose up --build -d
```

Untuk melihat log aktivitas bot:
```bash
docker compose logs -f
```

Untuk mematikan bot:
```bash
docker compose down
```

---

## 💻 Cara Menjalankan Secara Lokal (Tanpa Docker)

Jika Anda ingin mencoba menjalankannya langsung di mesin host:

1. **Pasang Tesseract OCR di Sistem**:
   ```bash
   # Ubuntu / Debian
   sudo apt update
   sudo apt install -y tesseract-ocr tesseract-ocr-ind tesseract-ocr-eng libmagic1 ffmpeg

   # Arch Linux
   sudo pacman -S tesseract tesseract-data-ind tesseract-data-eng

   # macOS (Homebrew)
   brew install tesseract tesseract-lang
   ```

2. **Buat Virtual Environment & Pasang Dependensi**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Jalankan Bot**:
   ```bash
   python main.py
   ```

---

## 📦 Cara Memindahkan / Deploy ke Server (Device) Lain

Karena proyek ini sudah menggunakan Docker dan Git-friendly, proses pemindahan ke VPS atau server lain sangat mudah:

### Opsi A: Menggunakan Git / Salin Folder
1. Salin seluruh folder `markitdown-telegram-bot/` ke server baru (misal via `scp` atau `rsync`):
   ```bash
   scp -r markitdown-telegram-bot user@ip-server:~/
   ```
2. Di server tujuan, masuk ke foldernya:
   ```bash
   cd ~/markitdown-telegram-bot
   ```
3. Buat atau periksa file `.env` dan pastikan `TELEGRAM_BOT_TOKEN` sudah terisi.
4. Jalankan:
   ```bash
   docker compose up -d --build
   ```

---

## ⚙️ Variabel Lingkungan (.env)

| Variabel | Default | Keterangan |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | *Wajib* | Token bot dari @BotFather |
| `ALLOWED_USER_IDS` | *(Kosong)* | ID akun Telegram pengguna yang diizinkan (dipisah koma). Kosongkan jika ingin publik. |
| `OCR_LANGUAGES` | `ind+eng` | Bahasa Tesseract OCR (`ind` untuk Indonesia, `eng` untuk Inggris) |
| `BATCH_DEBOUNCE_SECONDS` | `2.5` | Jeda waktu pengelompokan multi-file upload |
| `MAX_FILE_SIZE_MB` | `50` | Batas maksimum ukuran file |
| `OPENAI_API_KEY` | *(Kosong)* | *(Opsional)* API key OpenAI jika ingin OCR/deskripsi gambar berbasis LLM Vision |

---

## 📁 Struktur Direktori

```text
markitdown-telegram-bot/
├── config.py           # Parsing variabel lingkungan & konfigurasi
├── converter.py        # Logika MarkItDown & Tesseract OCR
├── batch_manager.py    # Debounce antrean pengiriman multi-file
├── zip_handler.py      # Penanganan ekstraksi & pembuatan file ZIP
├── bot.py              # Handler pesan Telegram & alur pengiriman
├── main.py             # Entrypoint aplikasi bot
├── requirements.txt    # Dependensi Python
├── Dockerfile          # Kontainerisasi Debian + Tesseract OCR
├── docker-compose.yml  # Pengaturan servis Docker
├── .env.example        # Template konfigurasi
└── README.md           # Dokumentasi lengkap
```
