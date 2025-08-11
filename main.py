# main.py — केवल YouTube Shorts डाउनलोड करने वाला Telegram bot
import os
import logging
import asyncio
import tempfile
from pathlib import Path
from typing import Optional

import yt_dlp
from yt_dlp.utils import DownloadError
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "PUT_YOUR_BOT_TOKEN_HERE"
# optional cookies: either path to secret file (e.g. /etc/secrets/cookies.txt) or full content in env
COOKIE_FILE = os.environ.get("COOKIE_FILE")
COOKIE_CONTENT = os.environ.get("COOKIE_CONTENT")
# download directory (writable)
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "yt_shorts_bot"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("yt-shorts-bot")

# ---------------- helpers ----------------
def prepare_cookie_local() -> Optional[str]:
    """Return path to a writable cookie file for yt-dlp, or None."""
    try:
        local = DOWNLOAD_DIR / "cookies.txt"
        if COOKIE_CONTENT:
            with open(local, "w", encoding="utf-8") as f:
                f.write(COOKIE_CONTENT)
            logger.info("Wrote COOKIE_CONTENT to %s", local)
            return str(local)
        if COOKIE_FILE and os.path.exists(COOKIE_FILE) and os.access(COOKIE_FILE, os.R_OK):
            with open(COOKIE_FILE, "r", encoding="utf-8") as rf:
                data = rf.read()
            with open(local, "w", encoding="utf-8") as wf:
                wf.write(data)
            logger.info("Copied COOKIE_FILE to writable %s", local)
            return str(local)
    except Exception as e:
        logger.exception("Cookie prepare error: %s", e)
    return None

def build_ydl_opts(cookie_local: Optional[str] = None):
    opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
    }
    if cookie_local:
        opts["cookiefile"] = cookie_local
    return opts

async def yt_download(url: str, cookie_local: Optional[str] = None) -> Path:
    loop = asyncio.get_event_loop()
    opts = build_ydl_opts(cookie_local)

    def _dl():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fname = ydl.prepare_filename(info)
            p = Path(fname)
            if p.exists():
                return p
            mp4 = p.with_suffix(".mp4")
            if mp4.exists():
                return mp4
            return p

    path = await loop.run_in_executor(None, _dl)
    return Path(path)

def is_shorts_url(url: str) -> bool:
    u = (url or "").strip()
    # Accept URLs that include /shorts/ (common YouTube Shorts pattern)
    if "/shorts/" in u:
        return True
    # also accept share short links like youtu.be but user explicitly asked shorts -> prefer /shorts/
    return False

# ---------------- handlers ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("नमस्ते! केवल YouTube के `/shorts/` वाले लिंक यहाँ भेजो — मैं उन्हें डाउनलोड कर के भेज दूँगा।")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    if not txt:
        await update.message.reply_text("कृपया एक लिंक भेजें।")
        return

    if not is_shorts_url(txt):
        await update.message.reply_text("यह लिंक Short नहीं दिख रहा। कृपया केवल YouTube के `/shorts/` लिंक भेजिए।")
        return

    await update.message.reply_text("🔎 Short जानकारी ले रहा हूँ — थोड़ी देर लगेगी...")

    cookie_local = prepare_cookie_local()

    # try to fetch info first (friendly error handling)
    try:
        opts_info = build_ydl_opts(cookie_local)
        opts_info["skip_download"] = True
        with yt_dlp.YoutubeDL(opts_info) as ydl:
            info = ydl.extract_info(txt, download=False)
    except DownloadError as e:
        err = str(e)
        logger.info("yt-dlp extract error: %s", err)
        if "Sign in to confirm" in err or "use --cookies" in err.lower():
            await update.message.reply_text(
                "YouTube ने sign-in/captcha माँगा — अगर यह आ रहा है तो browser से cookies export करके `COOKIE_FILE` या `COOKIE_CONTENT` set करो।"
            )
        else:
            await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {err}")
        return
    except Exception as e:
        logger.exception("extract_info failed")
        await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {e}")
        return

    title = (info.get("title") if isinstance(info, dict) else "short")
    await update.message.reply_text(f"📥 डाउनलोड शुरू कर रहा हूँ: {title}")

    try:
        path = await yt_download(txt, cookie_local=cookie_local)
    except DownloadError as e:
        logger.exception("DownloadError")
        await update.message.reply_text(f"डाउनलोड एरर: {e}")
        return
    except Exception as e:
        logger.exception("Unexpected download error")
        await update.message.reply_text(f"डाउनलोड में एरर: {e}")
        return

    # send the result
    try:
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(path, "rb"), filename=path.name, caption=title)
        await update.message.reply_text("✅ भेज दिया गया।")
    except Exception as e:
        logger.exception("send_document failed")
        await update.message.reply_text(f"फाइल भेजने में दिक्कत: {e}\n(ध्यान: Telegram का size-limit लागू हो सकता है)")
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

# ---------------- main ----------------
def main():
    if BOT_TOKEN.startswith("PUT_YOUR_BOT_TOKEN"):
        logger.error("BOT_TOKEN नहीं सेट है — environment var BOT_TOKEN में डालें या main.py में hardcode करें।")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot चल रहा है (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
