# main.py
import os
import logging
import asyncio
import tempfile
from pathlib import Path
from typing import Optional

import yt_dlp
from yt_dlp.utils import DownloadError
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ---------------- CONFIG ----------------
# Prefer to set BOT_TOKEN in environment on Render. If not, you can hardcode here.
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "PUT_YOUR_BOT_TOKEN_HERE"

# Max allowed download size (bytes)
MAX_BYTES = 100 * 1024 * 1024  # 100 MB

# Download dir (writable)
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "ytbot_downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Cookie support (either set COOKIE_FILE path, or COOKIE_CONTENT with file contents)
COOKIE_FILE = os.environ.get("COOKIE_FILE")         # e.g. /etc/secrets/cookies.txt (Render secret file)
COOKIE_CONTENT = os.environ.get("COOKIE_CONTENT")   # if you paste entire cookies content into env (secret)
GEO_BYPASS_COUNTRY = os.environ.get("GEO_BYPASS_COUNTRY")  # optional, e.g. "IN"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ytbot")

# ---------------- Helper: prepare cookie local copy ----------------
def prepare_cookie_local() -> Optional[str]:
    """
    Ensure a writable cookie-file exists and return its path for yt-dlp.
    Uses COOKIE_CONTENT (preferred) or reads COOKIE_FILE (read-only on Render) and writes a copy to DOWNLOAD_DIR.
    Returns path string or None if not available.
    """
    try:
        local = DOWNLOAD_DIR / "cookies.txt"
        # If COOKIE_CONTENT provided, write it
        if COOKIE_CONTENT:
            with open(local, "w", encoding="utf-8") as f:
                f.write(COOKIE_CONTENT)
            logger.info("Wrote COOKIE_CONTENT to %s", local)
            return str(local)

        # Else if COOKIE_FILE path exists and readable, copy it
        if COOKIE_FILE and os.path.exists(COOKIE_FILE) and os.access(COOKIE_FILE, os.R_OK):
            with open(COOKIE_FILE, "r", encoding="utf-8") as rf:
                data = rf.read()
            with open(local, "w", encoding="utf-8") as wf:
                wf.write(data)
            logger.info("Copied secret cookie file to writable %s", local)
            return str(local)

    except Exception as e:
        logger.exception("Error preparing cookie local copy: %s", e)

    return None

# Build base yt-dlp options (we will update cookiefile dynamically)
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
    if GEO_BYPASS_COUNTRY:
        opts["geo_bypass_country"] = GEO_BYPASS_COUNTRY
    if cookie_local:
        opts["cookiefile"] = cookie_local
    return opts

# Estimate filesize from info dict (best effort)
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

# Download function runs in executor to avoid blocking event loop
async def yt_download(url: str, cookie_local: Optional[str] = None) -> Path:
    loop = asyncio.get_event_loop()
    opts = build_ydl_opts(cookie_local=cookie_local)

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fname = ydl.prepare_filename(info)
            # try mp4 suffix if merged
            p = Path(fname)
            if p.exists():
                return p
            mp4 = p.with_suffix(".mp4")
            if mp4.exists():
                return mp4
            return p

    path = await loop.run_in_executor(None, _download)
    return Path(path)

# ---------------- Telegram Handlers ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("नमस्ते! YouTube लिंक भेजो — मैं 100MB तक का वीडियो डाउनलोड करके भेज दूँगा।")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if not text or ("youtube.com" not in text and "youtu.be" not in text):
        await update.message.reply_text("कृपया एक सही YouTube लिंक भेजें।")
        return

    await update.message.reply_text("🔎 वीडियो जानकारी ले रहा हूँ — थोड़ी देर...")

    # prepare cookie local copy (if any)
    cookie_local = prepare_cookie_local()

    # first get info (skip download) to estimate size
    try:
        opts_info = build_ydl_opts(cookie_local=cookie_local)
        opts_info["skip_download"] = True
        with yt_dlp.YoutubeDL(opts_info) as ydl:
            info = ydl.extract_info(text, download=False)
    except DownloadError as e:
        err = str(e)
        logger.info("yt-dlp DownloadError on extract_info: %s", err)
        # friendly messages
        if "Sign in to confirm" in err or "use --cookies" in err.lower():
            await update.message.reply_text(
                "त्रुटि: YouTube ने sign-in/captcha माँगा — cookies भेजने से समाधान हो सकता है.\n"
                "यदि तुमने cookies अपलोड की हैं तो उन्हें अपडेट/refresh करो।"
            )
        else:
            await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {err}")
        return
    except Exception as e:
        logger.exception("Error extracting info")
        await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {e}")
        return

    estimated = estimate_size(info)
    size_mb = estimated / (1024 * 1024) if estimated else None
    if size_mb:
        await update.message.reply_text(f"अनुमानित आकार: {size_mb:.2f} MB")
    else:
        await update.message.reply_text("अनुमानित आकार उपलब्ध नहीं है — डाउनलोड करके पता लगाएंगे (warning).")

    # enforce MAX_BYTES
    if estimated and estimated > MAX_BYTES:
        await update.message.reply_text(
            f"⚠️ यह वीडियो लगभग {size_mb:.1f} MB का है — अधिकतम अनुमत सीमा {MAX_BYTES/(1024*1024):.0f} MB है।\n"
            "यदि तुम चाहो तो cookies अपलोड करो या छोटा format चुनो।"
        )
        return

    # proceed to download
    await update.message.reply_text("📥 डाउनलोड शुरू कर रहा हूँ — धैर्य रखें...")

    try:
        path = await yt_download(text, cookie_local=cookie_local)
    except DownloadError as e:
        logger.exception("DownloadError during download")
        await update.message.reply_text(f"डाउनलोड एरर: {e}")
        return
    except Exception as e:
        logger.exception("Unexpected download error")
        await update.message.reply_text(f"डाउनलोड में एरर: {e}")
        return

    # send file to user
    try:
        # send as document (safer for size)
        await context.bot.send_document(chat_id, document=open(path, "rb"), filename=path.name, caption=info.get("title"))
        await update.message.reply_text("✅ भेज दिया गया।")
    except Exception as e:
        logger.exception("Error sending file")
        await update.message.reply_text(f"फाइल भेजने में दिक्कत: {e}\n(संदेश: Telegram फाइल साइज लिमिट आ सकती है।)")
    finally:
        # cleanup
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

# ---------------- Main ----------------
def main():
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        logger.error("BOT_TOKEN not set. Set BOT_TOKEN env or hardcode it in main.py")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    logger.info("Bot is starting (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
