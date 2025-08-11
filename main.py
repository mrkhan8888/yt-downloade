import telebot
from yt_dlp import YoutubeDL
import os

BOT_TOKEN = "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"
ADMIN_ID = 5073222820

bot = telebot.TeleBot(BOT_TOKEN)

ydl_opts = {
    'format': 'mp4[height<=360]',
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
        err_msg = str(e)
        bot.edit_message_text(f"वीडियो डाउनलोड नहीं हो पाया: {err_msg}", message.chat.id, msg.message_id)
        # Admin को error भेजना
        bot.send_message(ADMIN_ID, f"Error for user {message.from_user.id} ({message.from_user.username}): {err_msg}")

if __name__ == '__main__':
    bot.remove_webhook()  # webhook हटाओ जिससे 409 error न आए
    bot.infinity_polling()
