import logging
import sys
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot import (
    TelegramMarkitdownBot,
    help_command,
    start_command,
    status_command,
)
from config import TELEGRAM_BOT_TOKEN

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("markitdown-bot")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN belum disetel! Harap buat file .env dan isi TELEGRAM_BOT_TOKEN Anda."
        )
        sys.exit(1)

    logger.info("Menginisialisasi MarkItDown Telegram Bot...")

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    bot_handler = TelegramMarkitdownBot(application)

    # Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))

    # Message Handlers for Documents and Photos
    application.add_handler(
        MessageHandler(filters.Document.ALL, bot_handler.handle_document)
    )
    application.add_handler(
        MessageHandler(filters.PHOTO, bot_handler.handle_photo)
    )

    logger.info("Bot siap! Memulai polling ke Telegram...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
