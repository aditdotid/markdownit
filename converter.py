import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image
import pytesseract
from markitdown import MarkItDown

from config import (
    IMAGE_EXTENSIONS,
    OCR_LANGUAGES,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    original_filename: str
    markdown_content: str
    success: bool
    error_message: Optional[str] = None


class DocumentConverter:
    def __init__(self):
        self._llm_client = None
        if OPENAI_API_KEY:
            try:
                from openai import OpenAI
                kwargs = {"api_key": OPENAI_API_KEY}
                if OPENAI_BASE_URL:
                    kwargs["base_url"] = OPENAI_BASE_URL
                self._llm_client = OpenAI(**kwargs)
                logger.info("OpenAI client initialized for MarkItDown multimodal vision.")
            except Exception as e:
                logger.warning(f"Gagal menginisialisasi OpenAI client: {e}")

        # Initialize MarkItDown
        if self._llm_client:
            self._markitdown = MarkItDown(
                llm_client=self._llm_client,
                llm_model=OPENAI_MODEL,
            )
        else:
            self._markitdown = MarkItDown()

    def _ocr_image(self, file_path: Path) -> str:
        """
        Lakukan ekstraksi teks dari gambar menggunakan Tesseract OCR lokal (offline).
        """
        try:
            with Image.open(file_path) as img:
                # Convert image to RGB if needed (e.g. RGBA or Palette)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                
                # Perform OCR with configured languages (default: ind+eng)
                extracted_text = pytesseract.image_to_string(img, lang=OCR_LANGUAGES).strip()

                if not extracted_text:
                    return f"# OCR Result: {file_path.name}\n\n*(Tidak ada teks yang berhasil dideteksi dari gambar ini)*\n"

                return f"# OCR Result: {file_path.name}\n\n{extracted_text}\n"
        except Exception as e:
            logger.error(f"Error pada Tesseract OCR untuk {file_path.name}: {e}")
            raise

    def convert_file(self, file_path: Path) -> ConversionResult:
        """
        Konversi file tunggal (DOCX, XLSX, PDF, Gambar/OCR, dll.) ke Markdown.
        """
        filename = file_path.name
        suffix = file_path.suffix.lower()

        logger.info(f"Memulai konversi file: {filename} ({suffix})")

        try:
            # 1. Kasus Khusus: Gambar untuk OCR
            if suffix in IMAGE_EXTENSIONS:
                # Jika ada OpenAI LLM terpasang, coba gunakan MarkItDown multimodal terlebih dahulu
                if self._llm_client:
                    try:
                        md_res = self._markitdown.convert(str(file_path))
                        if md_res and md_res.text_content:
                            return ConversionResult(
                                original_filename=filename,
                                markdown_content=md_res.text_content,
                                success=True,
                            )
                    except Exception as llm_err:
                        logger.warning(f"LLM vision gagal untuk {filename}, beralih ke Tesseract OCR: {llm_err}")

                # Fallback / default: Gunakan Tesseract OCR lokal
                text = self._ocr_image(file_path)
                return ConversionResult(
                    original_filename=filename,
                    markdown_content=text,
                    success=True,
                )

            # 2. Dokumen Standar (DOCX, XLSX, PPTX, PDF, CSV, TXT, HTML, dll.)
            result = self._markitdown.convert(str(file_path))
            content = result.text_content if result else ""

            if not content or not content.strip():
                # Jika dokumen kosong atau PDF hasil scan tanpa layer teks
                content = f"# {filename}\n\n*(File berhasil dibaca, namun tidak ada konten teks yang ditemukan)*\n"

            return ConversionResult(
                original_filename=filename,
                markdown_content=content,
                success=True,
            )

        except Exception as e:
            logger.warning(f"MarkItDown gagal untuk {filename}: {e}. Mencoba fallback...")
            # Fallback untuk file teks jika MarkItDown gagal membaca encoding tertentu
            if suffix in {".txt", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".md"}:
                for enc in ("utf-8", "latin-1", "cp1252"):
                    try:
                        content = file_path.read_text(encoding=enc)
                        return ConversionResult(
                            original_filename=filename,
                            markdown_content=content,
                            success=True,
                        )
                    except UnicodeDecodeError:
                        continue

            logger.error(f"Gagal mengonversi file {filename}: {e}", exc_info=True)
            return ConversionResult(
                original_filename=filename,
                markdown_content="",
                success=False,
                error_message=str(e),
            )


# Global singleton converter instance
converter_instance = DocumentConverter()
