import os
import yt_dlp
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"

# Download function
def download_youtube_video(url):
    ydl_opts = {
        "format": "mp4",
        "outtmpl": "video.mp4",
        "max_filesize": 100 * 1024 * 1024,  # 100MB limit
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return "video.mp4"
    except yt_dlp.utils.DownloadError:
        return None

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("YouTube लिंक भेजो, मैं 100MB तक का वीडियो डाउनलोड करके भेज दूँगा।")

# Handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "youtube.com" in url or "youtu.be" in url:
        await update.message.reply_text("⏳ डाउनलोड हो रहा है...")
        video_file = download_youtube_video(url)
        if video_file and os.path.exists(video_file):
            try:
                await update.message.reply_video(video=open(video_file, "rb"))
            except Exception as e:
                await update.message.reply_text(f"⚠️ फ़ाइल भेजने में दिक्कत: {e}")
            finally:
                os.remove(video_file)
        else:
            await update.message.reply_text("⚠️ वीडियो डाउनलोड नहीं हो पाया या 100MB से बड़ा है।")
    else:
        await update.message.reply_text("कृपया सही YouTube लिंक भेजें।")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
