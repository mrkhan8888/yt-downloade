import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp
import shutil

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("yt-shorts-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
COOKIE_FILE = os.getenv("COOKIE_FILE")  # Path to cookies.txt (Render Secret Files)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

TMP_DIR = "/tmp/yt_shorts_dl"
os.makedirs(TMP_DIR, exist_ok=True)

def get_cookies_path():
    if COOKIE_FILE and os.path.exists(COOKIE_FILE):
        dst = os.path.join(TMP_DIR, "cookies.txt")
        shutil.copy(COOKIE_FILE, dst)
        logger.info(f"Copied COOKIE_FILE to writable {dst}")
        return dst
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a YouTube Shorts link and I'll download it for you!")

async def download_shorts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if "youtube.com/shorts/" not in url:
        await update.message.reply_text("❌ Please send only YouTube Shorts links!")
        return

    await update.message.reply_text("⏳ Downloading your Shorts video...")

    cookies_path = get_cookies_path()

    ydl_opts = {
        "outtmpl": os.path.join(TMP_DIR, "%(title)s.%(ext)s"),
        "format": "best[filesize<=100M]",  # 100 MB limit
        "geo_bypass": True,
        "geo_bypass_country": "IN",
        "noplaylist": True,
        "quiet": True,
        "cookiefile": cookies_path if cookies_path else None
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        await update.message.reply_video(video=open(file_path, "rb"))
        os.remove(file_path)

    except Exception as e:
        logger.error(f"yt-dlp extract error: {e}")
        await update.message.reply_text(f"❌ Failed to download: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_shorts))

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
