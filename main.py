import telebot
from yt_dlp import YoutubeDL
import os

BOT_TOKEN = "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"

bot = telebot.TeleBot(BOT_TOKEN)

ydl_opts = {
    'format': 'mp4[height<=360]',  # 360p तक डाउनलोड करेगा
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
}

if not os.path.exists('downloads'):
    os.mkdir('downloads')

@bot.message_handler(commands=['start'])
def start_msg(message):
    bot.reply_to(message, "नमस्ते! YouTube Shorts का लिंक भेजो, मैं वीडियो डाउनलोड करके दूंगा।")

@bot.message_handler(func=lambda message: True)
def download_shorts(message):
    url = message.text.strip()

    if "youtube.com/shorts/" not in url:
        bot.reply_to(message, "कृपया केवल YouTube Shorts का लिंक भेजें।")
        return

    msg = bot.reply_to(message, "डाउनलोड शुरू कर रहा हूँ, कृपया इंतजार करें...")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        with open(file_path, 'rb') as video:
            bot.send_video(message.chat.id, video)

        bot.edit_message_text("डाउनलोड पूरा हो गया!", message.chat.id, msg.message_id)

        os.remove(file_path)

    except Exception as e:
        bot.edit_message_text(f"कुछ गलत हो गया: {str(e)}", message.chat.id, msg.message_id)

if __name__ == '__main__':
    bot.remove_webhook()  # webhook हटाओ ताकि polling ठीक चले
    bot.infinity_polling()
