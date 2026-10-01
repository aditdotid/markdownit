import asyncio
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import List, Optional

from telegram import Document, PhotoSize, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from batch_manager import BatchManager, QueuedFile
from config import (
    ALLOWED_USER_IDS,
    MAX_FILE_SIZE_MB,
    OCR_LANGUAGES,
    OPENAI_API_KEY,
    SUPPORTED_EXTENSIONS,
    TEMP_DIR,
)
from converter import converter_instance
from zip_handler import create_markdown_zip, extract_zip

logger = logging.getLogger(__name__)


def is_user_allowed(user_id: int) -> bool:
    """Cek apakah user memiliki izin untuk menggunakan bot."""
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


async def safe_send_message(
    bot,
    chat_id: int,
    text: str,
    parse_mode: Optional[str] = ParseMode.MARKDOWN,
):
    """
    Mengirim pesan dengan aman. Jika formatting Markdown gagal (misal karena
    karakter khusus dalam nama file atau pesan error), otomatis beralih ke teks polos.
    """
    # Telegram message character limit is 4096
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=parse_mode,
            )
        except BadRequest as e:
            logger.warning(f"Formatting markdown gagal ({e}), mengirim sebagai teks biasa.")
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=None,
            )
        except Exception as e:
            logger.error(f"Gagal mengirim pesan ke chat {chat_id}: {e}")


async def safe_edit_message(
    bot,
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: Optional[str] = ParseMode.MARKDOWN,
):
    """Mengedit pesan status tanpa membuat alur proses crash jika pesan tidak ditemukan."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
        )
    except BadRequest:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=None,
            )
        except Exception:
            pass
    except Exception:
        pass


async def safe_delete_message(bot, chat_id: int, message_id: int):
    """Menghapus pesan sementara dengan penanganan error aman."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /start"""
    user = update.effective_user
    if not is_user_allowed(user.id):
        await update.message.reply_text("⛔ Maaf, Anda tidak terdaftar dalam whitelist pengguna bot ini.")
        return

    text = (
        f"Halo, *{user.first_name}*! 👋\n\n"
        "Selamat datang di *MarkItDown Gateway Bot*.\n"
        "Kirim dokumen atau gambar ke bot ini, dan bot akan mengonversinya menjadi format *Markdown (.md)*.\n\n"
        "✨ *Fitur Unggulan:*\n"
        "• 📄 *Dokumen:* Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), PDF, CSV, HTML, TXT.\n"
        "• 🖼️ *OCR Gambar:* Ekstraksi teks otomatis via Tesseract OCR (`ind+eng`).\n"
        "• 🗂️ *Multi-file Batch:* Kirim banyak file sekaligus tanpa harus menunggu giliran!\n"
        "• 📦 *Deteksi Otomatis ZIP:*\n"
        "  - Jika kirim file `.zip` ➔ Isi dokumen di dalamnya otomatis diekstrak & dikonversi.\n"
        "  - Jika hasil konversi *lebih dari 1 file* ➔ Otomatis dibungkus menjadi file `.zip`.\n"
        "  - Jika hanya *1 file* ➔ Dikirim langsung sebagai file `.md`.\n\n"
        "Silakan kirim file dokumen atau gambar sekarang!"
    )
    await safe_send_message(context.bot, update.effective_chat.id, text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /help"""
    text = (
        "📖 *Panduan Penggunaan MarkItDown Bot*\n\n"
        "1. *Konversi 1 Dokumen / Gambar:*\n"
        "   Kirim file `.docx`, `.xlsx`, `.pdf`, atau gambar langsung ke chat.\n"
        "   Bot akan membalas dengan file `.md` hasil konversi.\n\n"
        "2. *Konversi Banyak File Sekaligus:*\n"
        "   Pilih beberapa file sekaligus di Telegram lalu kirim.\n"
        "   Bot otomatis mengumpulkan file dalam antrean dan mengembalikan file `.zip`.\n\n"
        "3. *Konversi dari File ZIP:*\n"
        "   Kirim file `.zip` (misal berisi 20+ file dokumen).\n"
        "   Bot akan mengekstrak, mengonversi satu per satu secara asinkron, dan mengemas hasilnya ke ZIP baru.\n\n"
        "4. *Kirim File Kapan Saja (Antrean Cerdas):*\n"
        "   Anda tidak perlu menunggu proses konversi selesai untuk mengirim file baru. "
        "Bot akan otomatis memasukkan file baru Anda ke antrean dan mengerjakannya secara berurutan.\n\n"
        "📐 *Batas Ukuran File:* Hingga 50 MB per file.\n"
        f"🌐 *Bahasa OCR:* `{OCR_LANGUAGES}`\n"
    )
    await safe_send_message(context.bot, update.effective_chat.id, text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memeriksa status bot dan konfigurasi sistem."""
    llm_status = "Aktif (OpenAI API / Vision)" if OPENAI_API_KEY else "Tidak aktif (Tesseract OCR Lokal)"
    whitelist_status = f"{len(ALLOWED_USER_IDS)} Pengguna" if ALLOWED_USER_IDS else "Terbuka untuk Umum (Publik)"

    text = (
        "📊 *Status Sistem MarkItDown Bot*\n\n"
        f"• *OCR Engine:* Tesseract OCR ({OCR_LANGUAGES})\n"
        f"• *LLM Multimodal:* {llm_status}\n"
        f"• *Akses Pengguna:* {whitelist_status}\n"
        f"• *Maksimal Ukuran File:* {MAX_FILE_SIZE_MB} MB\n"
        "• *Sistem Antrean:* FIFO Async Queue Aktif\n"
        "• *Lingkungan:* Docker Container\n"
    )
    await safe_send_message(context.bot, update.effective_chat.id, text)


class TelegramMarkitdownBot:
    def __init__(self, application: Application):
        self.application = application
        self.batch_manager = BatchManager(
            process_callback=self.process_batch,
            notify_queued_callback=self.notify_queued,
        )

    async def notify_queued(self, chat_id: int, queue_position: int, file_count: int):
        """Memberi kabar kepada pengguna jika file baru mereka masuk antrean."""
        text = (
            f"📥 *{file_count} file baru diterima!*\n"
            f"⏳ Bot sedang menyelesaikan tugas Anda sebelumnya. "
            f"File ini dimasukkan ke *Antrean #{queue_position}* dan akan otomatis dikonversi segera setelahnya."
        )
        await safe_send_message(self.application.bot, chat_id, text)

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menangani dokumen yang dikirim pengguna."""
        user = update.effective_user
        if not is_user_allowed(user.id):
            await update.message.reply_text("⛔ Akses ditolak.")
            return

        doc: Document = update.message.document
        filename = doc.file_name or f"doc_{doc.file_unique_id}.bin"
        suffix = Path(filename).suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            await update.message.reply_text(
                f"⚠️ Ekstensi `{suffix}` belum didukung.\n"
                "Format yang didukung: docx, xlsx, pptx, pdf, txt, csv, html, json, jpg, png, zip.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Cek batas ukuran
        if doc.file_size and doc.file_size > (MAX_FILE_SIZE_MB * 1024 * 1024):
            await update.message.reply_text(
                f"❌ Ukuran file `{filename}` ({doc.file_size // (1024*1024)} MB) melebihi batas {MAX_FILE_SIZE_MB} MB.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        queued_file = QueuedFile(
            file_id=doc.file_id,
            file_name=filename,
            file_size=doc.file_size or 0,
            telegram_file_obj=doc,
        )

        await self.batch_manager.add_file(
            chat_id=update.effective_chat.id,
            queued_file=queued_file,
        )

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING,
        )

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menangani foto/gambar kompresi yang dikirim pengguna."""
        user = update.effective_user
        if not is_user_allowed(user.id):
            await update.message.reply_text("⛔ Akses ditolak.")
            return

        photo: PhotoSize = update.message.photo[-1]
        filename = f"photo_{photo.file_unique_id}.jpg"

        queued_file = QueuedFile(
            file_id=photo.file_id,
            file_name=filename,
            file_size=photo.file_size or 0,
            telegram_file_obj=photo,
        )

        await self.batch_manager.add_file(
            chat_id=update.effective_chat.id,
            queued_file=queued_file,
        )

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING,
        )

    async def process_batch(
        self,
        chat_id: int,
        queued_files: List[QueuedFile],
        status_message_id: Optional[int],
    ):
        """
        Logika eksekusi batch: download, ekstrak zip (jika ada), konversi semua file
        secara asinkron (non-blocking), lalu kirim output sebagai .md atau .zip.
        """
        bot = self.application.bot
        work_dir = TEMP_DIR / f"batch_{chat_id}_{uuid.uuid4().hex[:8]}"
        work_dir.mkdir(parents=True, exist_ok=True)

        status_msg = await bot.send_message(
            chat_id=chat_id,
            text=f"⏳ *Memulai pemrosesan {len(queued_files)} file...*\nMengunduh file dari Telegram...",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            downloaded_paths: List[Path] = []

            # 1. Unduh semua file dari Telegram
            for idx, qf in enumerate(queued_files, 1):
                dest_path = work_dir / qf.file_name
                tg_file = await bot.get_file(qf.file_id)
                await tg_file.download_to_drive(custom_path=dest_path)
                downloaded_paths.append(dest_path)

            # 2. Siapkan daftar semua file yang akan dikonversi (ekstrak ZIP jika ada)
            files_to_convert: List[Path] = []
            has_zip_input = False

            for p in downloaded_paths:
                if p.suffix.lower() == ".zip":
                    has_zip_input = True
                    await safe_edit_message(
                        bot,
                        chat_id,
                        status_msg.message_id,
                        f"📦 *Mengekstrak file ZIP:* `{p.name}`...",
                    )
                    extract_dir = work_dir / f"extracted_{p.stem}"
                    extracted = extract_zip(p, extract_dir)
                    files_to_convert.extend(extracted)
                else:
                    files_to_convert.append(p)

            total_files = len(files_to_convert)
            if total_files == 0:
                await safe_edit_message(
                    bot,
                    chat_id,
                    status_msg.message_id,
                    "⚠️ Tidak ada file dokumen yang didukung untuk dikonversi.",
                )
                return

            await safe_edit_message(
                bot,
                chat_id,
                status_msg.message_id,
                f"⚙️ *Mengonversi {total_files} file ke Markdown...*",
            )

            # 3. Lakukan konversi satu per satu dalam thread terpisah (Non-blocking asyncio)
            successful_conversions: List[tuple[str, str]] = []  # (filename, markdown_content)
            failed_conversions: List[tuple[str, str]] = []      # (filename, error_message)

            last_edit_time = time.time()

            for idx, file_path in enumerate(files_to_convert, 1):
                # Update status berkala untuk progres banyak file (misal 24 file)
                now = time.time()
                if (now - last_edit_time > 1.5) or idx == 1 or idx == total_files:
                    last_edit_time = now
                    await safe_edit_message(
                        bot,
                        chat_id,
                        status_msg.message_id,
                        f"⚙️ *Mengonversi ({idx}/{total_files}):*\n`{file_path.name}`",
                    )

                # Jalankan konversi CPU-bound di background thread agar event loop tidak freeze
                res = await asyncio.to_thread(converter_instance.convert_file, file_path)
                if res.success:
                    successful_conversions.append((res.original_filename, res.markdown_content))
                else:
                    failed_conversions.append(
                        (res.original_filename, res.error_message or "Unknown conversion error")
                    )

            total_success = len(successful_conversions)

            # 4. Jika semua file gagal
            if total_success == 0:
                err_text = "❌ *Semua file gagal dikonversi:*\n"
                for fname, err in failed_conversions:
                    err_text += f"• `{fname}`: {err}\n"
                await safe_edit_message(bot, chat_id, status_msg.message_id, err_text)
                return

            # Hapus pesan status sementara agar ruang chat rapi
            await safe_delete_message(bot, chat_id, status_msg.message_id)

            # KASUS A: HANYA 1 FILE BERHASIL (Kirim file .md langsung)
            if total_success == 1 and not has_zip_input and len(queued_files) == 1:
                filename, content = successful_conversions[0]
                stem = Path(filename).stem or "document"
                md_filename = f"{stem}.md"
                md_file_path = work_dir / md_filename
                md_file_path.write_text(content, encoding="utf-8")

                # Kirim preview teks jika konten tidak terlalu panjang
                if 0 < len(content.strip()) <= 2500:
                    preview_text = (
                        f"✅ *Konversi Selesai:* `{filename}` ➔ `{md_filename}`\n\n"
                        "📝 *Preview Konten:*\n"
                        "```markdown\n"
                        f"{content.strip()}\n"
                        "```"
                    )
                    await safe_send_message(bot, chat_id, preview_text)

                # Kirim file dokumen .md
                with open(md_file_path, "rb") as doc_file:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=doc_file,
                        filename=md_filename,
                        caption=f"📄 Hasil konversi Markdown: `{md_filename}`",
                        parse_mode=ParseMode.MARKDOWN,
                    )

            # KASUS B: LEBIH DARI 1 FILE (Otomatis dibungkus ke ZIP)
            else:
                zip_filename = "converted_markdowns.zip"
                zip_path = work_dir / zip_filename
                create_markdown_zip(zip_path, successful_conversions)

                # Caption dokumen aman (singkat, tidak memicu error batas karakter / parse entity)
                safe_caption = f"📦 Selesai! Berhasil mengonversi {total_success} file ke Markdown (.zip)."

                with open(zip_path, "rb") as zf:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=zf,
                        filename=zip_filename,
                        caption=safe_caption,
                    )

                # Kirim rincian daftar file yang berhasil dan gagal sebagai pesan tersendiri
                summary_lines = [
                    f"📋 *Rincian Hasil Konversi ({total_success} file):*",
                    "",
                ]
                # Tampilkan hingga 40 file pertama agar pesan tidak melebihi batas Telegram
                for fname, _ in successful_conversions[:40]:
                    stem = Path(fname).stem or "document"
                    summary_lines.append(f"• `{fname}` ➔ `{stem}.md`")

                if len(successful_conversions) > 40:
                    summary_lines.append(
                        f"... dan {len(successful_conversions) - 40} file lainnya di dalam ZIP."
                    )

                if failed_conversions:
                    summary_lines.append("\n⚠️ *File yang gagal dikonversi:*")
                    for fname, err in failed_conversions:
                        short_err = (err[:60] + "...") if len(err) > 60 else err
                        summary_lines.append(f"• `{fname}` ({short_err})")

                await safe_send_message(bot, chat_id, "\n".join(summary_lines))

        except Exception as e:
            logger.error(f"Terjadi kesalahan saat memproses batch: {e}", exc_info=True)
            await safe_send_message(
                bot,
                chat_id,
                f"❌ Terjadi kesalahan saat memproses file: {str(e)}",
                parse_mode=None,
            )
        finally:
            # Bersihkan file sementara
            shutil.rmtree(work_dir, ignore_errors=True)
