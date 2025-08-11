import os
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask, request

BOT_TOKEN = "यहाँ_अपना_BOT_TOKEN_डालो"
ADMIN_ID = 123456789  # यहाँ अपना Telegram user id डालो

# Flask app for Render webhook
flask_app = Flask(__name__)

# Download function
def download_shorts(url):
    ydl_opts = {
        "format": "mp4[filesize<=100M]",  # 100MB तक
        "outtmpl": "/tmp/%(title)s.%(ext)s",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("भेजो कोई YouTube Shorts link, मैं डाउनलोड कर दूँगा 🎬")

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "youtube.com/shorts" in url or "youtu.be" in url:
        try:
            filepath = download_shorts(url)
            await update.message.reply_video(video=open(filepath, "rb"))
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("कृपया एक वैध YouTube Shorts लिंक भेजें।")

# Flask route for Telegram webhook
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    app.update_queue.put_nowait(update)
    return "ok"

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Render webhook setup
    PORT = int(os.environ.get("PORT", 8443))
    WEBHOOK_URL = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{BOT_TOKEN}"
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=WEBHOOK_URL
    )
