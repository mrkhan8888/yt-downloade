import os
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"  # आपका Telegram Bot Token
ADMIN_ID = 1234567890  # यहाँ अपना Telegram User ID डालें (int में)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB limit

# --- DOWNLOAD FUNCTION ---
def download_shorts(url):
    ydl_opts = {
        "format": "mp4",
        "outtmpl": "%(title)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "geo_bypass": True,
        "max_filesize": MAX_FILE_SIZE,
        "restrictfilenames": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Access Denied")
        return
    await update.message.reply_text("✅ Send me a YouTube Shorts link to download.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    url = update.message.text
    if "youtube.com/shorts" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ Please send a valid YouTube Shorts URL.")
        return

    await update.message.reply_text("⏳ Downloading...")
    try:
        file_path = download_shorts(url)
        if os.path.getsize(file_path) > MAX_FILE_SIZE:
            await update.message.reply_text("❌ File too large to send via Telegram.")
            os.remove(file_path)
            return

        await update.message.reply_video(video=open(file_path, "rb"))
        os.remove(file_path)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# --- MAIN ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
