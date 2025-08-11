# main.py
import os
import logging
import asyncio
import tempfile
from pathlib import Path
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp
from yt_dlp.utils import DownloadError

# ---- CONFIG ----
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"
RENDER_APP = os.environ.get("RENDER_APP") or "yt-downloade"  # your Render app name
WEBHOOK_URL = f"https://{RENDER_APP}.onrender.com/{BOT_TOKEN}"
PORT = int(os.environ.get("PORT", 8443))

MAX_BYTES = 100 * 1024 * 1024  # 100 MB limit
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "ytbot_dl"
DOWNLOAD_DIR.mkdir(exist_ok=True)

COOKIE_FILE = os.environ.get("COOKIE_FILE")
COOKIE_CONTENT = os.environ.get("COOKIE_CONTENT")
GEO_BYPASS_COUNTRY = os.environ.get("GEO_BYPASS_COUNTRY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ytbot")

# ---- Cookie helper ----
def prepare_cookie_local():
    local = DOWNLOAD_DIR / "cookies.txt"
    try:
        if COOKIE_CONTENT:
            local.write_text(COOKIE_CONTENT, encoding="utf-8")
            logger.info("Saved COOKIE_CONTENT to %s", local)
            return str(local)
        if COOKIE_FILE and os.path.exists(COOKIE_FILE) and os.access(COOKIE_FILE, os.R_OK):
            text = Path(COOKIE_FILE).read_text(encoding="utf-8")
            local.write_text(text, encoding="utf-8")
            logger.info("Copied COOKIE_FILE to %s", local)
            return str(local)
    except Exception as e:
        logger.exception("Cookie prepare error: %s", e)
    return None

def build_ydl_opts(cookie_local=None):
    opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True
    }
    if GEO_BYPASS_COUNTRY:
        opts["geo_bypass_country"] = GEO_BYPASS_COUNTRY
    if cookie_local:
        opts["cookiefile"] = cookie_local
    return opts

# ---- Download queue and worker ----
download_queue = asyncio.Queue()

async def download_worker(app):
    while True:
        update, url = await download_queue.get()
        chat_id = update.effective_chat.id
        cookie_local = prepare_cookie_local()
        try:
            opts = build_ydl_opts(cookie_local)
            with yt_dlp.YoutubeDL({**opts, "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            size = info.get("filesize") or info.get("filesize_approx") or 0
            if size > MAX_BYTES:
                await app.bot.send_message(chat_id, f"⚠️ वीडियो {size/(1024*1024):.1f}MB है—Limit: 100MB.")
                continue
            await app.bot.send_message(chat_id, "Downloading...")
            path = await asyncio.get_event_loop().run_in_executor(None, download_file, url, cookie_local)
            await app.bot.send_document(chat_id, document=open(path, "rb"), filename=path.name)
        except DownloadError as e:
            await app.bot.send_message(chat_id, f"Download error: {e}")
        except Exception as e:
            logger.exception("Unexpected error")
            await app.bot.send_message(chat_id, f"Error: {e}")
        finally:
            try:
                path.unlink(missing_ok=True)
            except:
                pass
            download_queue.task_done()

def download_file(url, cookie_local=None):
    opts = build_ydl_opts(cookie_local)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info))

# ---- Telegram Handlers ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send YouTube Shorts link; I'll download it if under 100MB.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "/shorts/" not in url:
        await update.message.reply_text("Please send a YouTube Shorts link.")
        return
    await update.message.reply_text("Queued your Short for download. You’ll receive it soon.")
    await download_queue.put((update, url))

# ---- Flask App & Webhook Setup ----
app = Flask(__name__)
telegram_app = None

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "OK", 200

@app.route("/")
def index():
    return "Bot is live!"

def main():
    global telegram_app
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    telegram_app.bot.delete_webhook(drop_pending_updates=True)
    telegram_app.bot.set_webhook(WEBHOOK_URL)
    logger.info("Webhook set to %s", WEBHOOK_URL)

    # Launch background worker
    asyncio.get_event_loop().create_task(download_worker(telegram_app))

    app.telegram_app = telegram_app
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
