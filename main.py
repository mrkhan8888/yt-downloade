import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

BOT_TOKEN = "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"
PORT = int(os.environ.get("PORT", 5000))
APP_URL = "https://yt-downloade.onrender.com"  # अपने Render domain से replace करो

app = Flask(__name__)

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a YouTube Shorts link and I'll download it for you!")

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "youtube.com/shorts" not in url and "youtu.be" not in url:
        await update.message.reply_text("Please send a valid YouTube Shorts link.")
        return

    ydl_opts = {
        'format': 'mp4',
        'outtmpl': 'video.mp4',
        'noplaylist': True,
        'max_filesize': 100000000,  # 100 MB limit
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        await update.message.reply_video(video=open("video.mp4", "rb"))
        os.remove("video.mp4")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.telegram_app.bot)
    app.telegram_app.update_queue.put_nowait(update)
    return "OK"

@app.route('/')
def index():
    return "Bot is running!"

if __name__ == '__main__':
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))

    app.telegram_app = application

    # Webhook setup
    application.bot.set_webhook(url=f"{APP_URL}/{BOT_TOKEN}")

    app.run(host="0.0.0.0", port=PORT)
