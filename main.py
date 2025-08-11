import os
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# --- Config ---
BOT_TOKEN = "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"
ADMIN_ID = 5073222820
DOWNLOAD_DIR = Path("/tmp/ytbot_downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# User data store
user_unlocks = set()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Cookie handling ---
COOKIE_FILE = os.environ.get("COOKIE_FILE")
COOKIE_CONTENT = os.environ.get("COOKIE_CONTENT")
COOKIE_LOCAL = None

if COOKIE_CONTENT:
    try:
        tmp_cookie = DOWNLOAD_DIR / "cookies.txt"
        with open(tmp_cookie, "w", encoding="utf-8") as f:
            f.write(COOKIE_CONTENT)
        COOKIE_LOCAL = str(tmp_cookie)
    except Exception as e:
        logger.exception(f"Failed to write COOKIE_CONTENT: {e}")

elif COOKIE_FILE:
    try:
        if os.path.exists(COOKIE_FILE) and os.access(COOKIE_FILE, os.R_OK):
            tmp_cookie = DOWNLOAD_DIR / "cookies.txt"
            with open(COOKIE_FILE, "r", encoding="utf-8") as rf:
                data = rf.read()
            with open(tmp_cookie, "w", encoding="utf-8") as wf:
                wf.write(data)
            COOKIE_LOCAL = str(tmp_cookie)
        else:
            logger.warning(f"COOKIE_FILE not readable: {COOKIE_FILE}")
    except Exception as e:
        logger.exception(f"Error copying COOKIE_FILE: {e}")

# --- yt-dlp options ---
YDL_BASE = {
    "format": "bestvideo+bestaudio/best",
    "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
    "noplaylist": True,
    "geo_bypass": True,
    "merge_output_format": "mp4",
    "quiet": True,
    "nocheckcertificate": True,
    "ignoreerrors": True
}

if COOKIE_LOCAL:
    YDL_BASE["cookiefile"] = COOKIE_LOCAL

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎥 नमस्ते!\nमुझे YouTube लिंक भेजो।\n"
        "🔹 20MB तक free download\n"
        "🔹 20MB+ के लिए 3 friends को share करो या admin unlock करे"
    )

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ यह command केवल admin के लिए है।")
    if not context.args:
        return await update.message.reply_text("Usage: /unlock <user_id>")
    try:
        uid = int(context.args[0])
        user_unlocks.add(uid)
        await update.message.reply_text(f"✅ User {uid} को unlock कर दिया गया।")
    except:
        await update.message.reply_text("❌ Invalid user_id")

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    if not url.startswith("http"):
        return await update.message.reply_text("कृपया एक मान्य YouTube लिंक भेजें।")

    await update.message.reply_text("⏳ वीडियो info चेक हो रहा है...")

    try:
        with yt_dlp.YoutubeDL({**YDL_BASE, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            filesize = info.get("filesize_approx") or info.get("filesize") or 0

        size_mb = filesize / (1024 * 1024)
        logger.info(f"Video size: {size_mb:.2f} MB for user {user_id}")

        # Check size limit
        if size_mb > 20 and user_id not in user_unlocks:
            return await update.message.reply_text(
                f"⚠️ यह वीडियो {size_mb:.1f}MB का है।\n"
                "20MB से ऊपर download करने के लिए:\n"
                "1️⃣ Bot link 3 friends को forward करो\n"
                "2️⃣ या admin से unlock करवाओ"
            )

        await update.message.reply_text("📥 Download शुरू हो रहा है...")

        with yt_dlp.YoutubeDL(YDL_BASE) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        if os.path.exists(file_path):
            await update.message.reply_video(video=open(file_path, "rb"))
            os.remove(file_path)
        else:
            await update.message.reply_text("❌ वीडियो फाइल नहीं मिली।")

    except Exception as e:
        logger.exception("Download error: %s", e)
        await update.message.reply_text(f"त्रुटि: {e}")

# --- Main ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("unlock", unlock))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))

    logger.info("Bot started...")
    app.run_polling()
