import os
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
import yt_dlp
import logging

# === CONFIG ===
BOT_TOKEN = "<8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls>"
ADMIN_ID = 5073222820
RENDER_DOMAIN = "<yt-downloade>"  # e.g. mybot.onrender.com

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Start Command ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 नमस्ते! मुझे YouTube लिंक भेजो और मैं तुम्हें वीडियो डाउनलोड करके दूँगा।")

# === Download Handler ===
async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ कृपया एक सही YouTube लिंक भेजें।")
        return

    await update.message.reply_text("⏳ डाउनलोड हो रहा है, कृपया इंतज़ार करें...")

    try:
        ydl_opts = {
            "outtmpl": "%(title)s.%(ext)s",
            "format": "best",
            "noplaylist": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        await update.message.reply_document(open(filename, "rb"))
        os.remove(filename)

    except Exception as e:
        logger.error(f"Download error: {e}")
        await update.message.reply_text(f"❌ त्रुटि: {e}")

# === Main Function ===
async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))

    # Remove old webhook
    await app.bot.delete_webhook()
    # Set new webhook
    await app.bot.set_webhook(f"https://{RENDER_DOMAIN}/webhook")

    logger.info("🚀 Webhook set हो गया!")
    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        url_path=BOT_TOKEN,
        webhook_url=f"https://{RENDER_DOMAIN}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
