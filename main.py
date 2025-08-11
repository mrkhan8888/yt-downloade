# main.py — YouTube Shorts-only downloader (100MB limit)
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

# ---------- CONFIG ----------
# Token and admin (आपने दिया हुआ token + admin id)
BOT_TOKEN = "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"
ADMIN_ID = 5073222820

# Max file size (bytes) — 100 MB
MAX_BYTES = 100 * 1024 * 1024

# Cookies support (optional)
# If on Render, upload secret file (eg /etc/secrets/cookies.txt) and set COOKIE_FILE env to that path.
# Or set COOKIE_CONTENT env with whole cookies text (secret).
COOKIE_FILE = os.environ.get("COOKIE_FILE")
COOKIE_CONTENT = os.environ.get("COOKIE_CONTENT")

# Download dir (writable)
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "yt_shorts_dl"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("yt-shorts-bot")

# ---------- helpers ----------
def prepare_cookie_local() -> Optional[str]:
    """Return writable cookie file path, or None."""
    try:
        local = DOWNLOAD_DIR / "cookies.txt"
        if COOKIE_CONTENT:
            local.write_text(COOKIE_CONTENT, encoding="utf-8")
            logger.info("Wrote COOKIE_CONTENT to %s", local)
            return str(local)
        if COOKIE_FILE and Path(COOKIE_FILE).exists() and os.access(COOKIE_FILE, os.R_OK):
            data = Path(COOKIE_FILE).read_text(encoding="utf-8")
            local.write_text(data, encoding="utf-8")
            logger.info("Copied COOKIE_FILE to writable %s", local)
            return str(local)
    except Exception as e:
        logger.exception("prepare_cookie_local error: %s", e)
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

def estimate_size(info: dict) -> int:
    if not info:
        return 0
    if info.get("entries"):
        info = info["entries"][0]
    fs = info.get("filesize") or info.get("filesize_approx")
    if fs:
        try:
            return int(fs)
        except:
            pass
    best = 0
    for f in info.get("formats", []) or []:
        for k in ("filesize", "filesize_approx"):
            v = f.get(k)
            if v:
                try:
                    best = max(best, int(v))
                except:
                    pass
    return best

def is_shorts_url(url: str) -> bool:
    u = (url or "").strip()
    return "/shorts/" in u

# ---------- Handlers ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("नमस्ते! केवल YouTube के /shorts/ लिंक भेजो — मैं उन्हें डाउनलोड कर के भेज दूँगा (max 100MB)।")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if not text or not is_shorts_url(text):
        await update.message.reply_text("कृपया केवल YouTube `/shorts/` वाला लिंक भेजें।")
        return

    await update.message.reply_text("🔎 Short info ले रहा हूँ — थोड़ी देर...")

    cookie_local = prepare_cookie_local()

    # get info to estimate size & friendly errors
    try:
        info_opts = build_ydl_opts(cookie_local)
        info_opts["skip_download"] = True
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(text, download=False)
    except DownloadError as e:
        err = str(e)
        logger.info("yt-dlp extract error: %s", err)
        if "Sign in to confirm" in err or "use --cookies" in err.lower():
            await update.message.reply_text(
                "त्रुटि: YouTube sign-in/captcha माँग रहा है — cookies लगाकर retry करो (COOKIE_FILE या COOKIE_CONTENT)."
            )
        else:
            await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {err}")
        return
    except Exception as e:
        logger.exception("extract_info failed")
        await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {e}")
        return

    title = info.get("title", "short")
    estimated = estimate_size(info)
    if estimated:
        await update.message.reply_text(f"अनुमानित आकार: {estimated/(1024*1024):.2f} MB")
    else:
        await update.message.reply_text("अनुमानित आकार उपलब्ध नहीं — आगे चलकर पता करेंगे।")

    if estimated and estimated > MAX_BYTES:
        await update.message.reply_text(f"⚠️ यह short ~{estimated/(1024*1024):.1f}MB है — अधिकतम सीमा {MAX_BYTES/(1024*1024):.0f}MB है।")
        return

    await update.message.reply_text(f"📥 डाउनलोड शुरू कर रहा हूँ: {title}")

    try:
        path = await yt_download(text, cookie_local=cookie_local)
    except DownloadError as e:
        logger.exception("DownloadError")
        await update.message.reply_text(f"डाउनलोड एरर: {e}")
        return
    except Exception as e:
        logger.exception("Unexpected download error")
        await update.message.reply_text(f"डाउनलोड में एरर: {e}")
        return

    # send file
    try:
        await context.bot.send_document(chat_id, document=open(path, "rb"), filename=path.name, caption=title)
        await update.message.reply_text("✅ भेज दिया गया।")
    except Exception as e:
        logger.exception("send_document failed")
        await update.message.reply_text(f"फाइल भेजने में दिक्कत: {e}\n(टिप: Telegram की file-size limit लागू हो सकती है)")
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

# ---------- main ----------
def main():
    # safety: avoid running multiple instances accidentally
    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

        logger.info("Bot starting (polling). Ensure only one instance is running.")
        app.run_polling()
    except Exception as e:
        logger.exception("Bot failed to start: %s", e)
        print("Error starting bot:", e)

if __name__ == "__main__":
    main()
