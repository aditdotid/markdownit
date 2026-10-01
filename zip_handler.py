import logging
import zipfile
from pathlib import Path
from typing import List, Tuple
from config import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


def extract_zip(zip_path: Path, target_dir: Path) -> List[Path]:
    """
    Mengekstrak file ZIP dengan aman (mencegah Zip Slip / directory traversal)
    dan mengembalikan daftar file yang didukung untuk konversi.
    Mendukung normalisasi path Windows dan mengabaikan metadata macOS.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted_files: List[Path] = []

    # Valid extensions inside zip (excluding nested zip for simplicity/safety)
    valid_extensions = {ext for ext in SUPPORTED_EXTENSIONS if ext != ".zip"}

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            # Skip direktori
            if member.is_dir():
                continue

            # Normalisasi path untuk Windows/Unix
            normalized_name = member.filename.replace("\\", "/").strip()
            name_parts = Path(normalized_name).parts

            # Skip file sampah macOS, Windows, atau hidden files
            if any(part.startswith(".") or part == "__MACOSX" for part in name_parts):
                continue

            # Zip slip security check
            target_path = (target_dir / normalized_name).resolve()
            if not str(target_path).startswith(str(target_dir.resolve())):
                logger.warning(f"Melewati file berbahaya dalam zip: {normalized_name}")
                continue

            # Cek apakah ekstensi didukung
            suffix = target_path.suffix.lower()
            if suffix in valid_extensions:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, open(target_path, "wb") as target:
                    target.write(source.read())
                extracted_files.append(target_path)
            else:
                logger.info(f"Mengabaikan file tak didukung dalam zip: {normalized_name}")

    logger.info(f"Berhasil mengekstrak {len(extracted_files)} file didukung dari {zip_path.name}")
    return extracted_files


def create_markdown_zip(output_zip_path: Path, items: List[Tuple[str, str]]) -> Path:
    """
    Membuat file ZIP berisi kumpulan dokumen Markdown (.md).
    items: List of (nama_file_markdown, isi_konten_markdown)
    """
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        used_names = set()
        for filename, content in items:
            stem = Path(filename).stem or "document"
            md_name = f"{stem}.md"

            # Cegah duplikasi nama file di dalam zip
            counter = 1
            final_name = md_name
            while final_name in used_names:
                final_name = f"{stem}_{counter}.md"
                counter += 1
            used_names.add(final_name)

            content_bytes = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(final_name, content_bytes)

    logger.info(f"Berhasil membuat arsip ZIP output: {output_zip_path.name} ({len(items)} file)")
    return output_zip_path
