import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Telegram Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Whitelist User IDs (comma-separated, e.g. "12345678,87654321"). If empty, bot is open to all users.
_allowed_users_raw = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS = [int(uid.strip()) for uid in _allowed_users_raw.split(",") if uid.strip().isdigit()]

# OCR Settings
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "ind+eng").strip()

# Optional LLM Settings (for MarkItDown Vision / Image Analysis)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()

# Debounce window in seconds for multi-file batch uploads
try:
    BATCH_DEBOUNCE_SECONDS = float(os.getenv("BATCH_DEBOUNCE_SECONDS", "2.5"))
except ValueError:
    BATCH_DEBOUNCE_SECONDS = 2.5

# Max file size in MB (Telegram standard Bot API limit is 20MB for downloads)
try:
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
except ValueError:
    MAX_FILE_SIZE_MB = 50

# Temp workspace directory
TEMP_DIR = Path(os.getenv("TEMP_DIR", "/tmp/markitdown_bot"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# List of supported file extensions
SUPPORTED_EXTENSIONS = {
    # Office documents
    ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    # PDF & Text
    ".pdf", ".txt", ".rtf", ".csv", ".tsv", ".json", ".xml", ".html", ".htm",
    # Images (for OCR)
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif",
    # Archives (for auto-extract)
    ".zip"
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"
}
