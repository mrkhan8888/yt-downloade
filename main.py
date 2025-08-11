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
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG ----------------
# तुम्हारा bot token — चाहो तो यहाँ hardcode कर दो, या env में BOT_TOKEN डालो (recommended)
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8278209952:AAFVWH7Yl534bZ9BpsRhY5rpX2a-TGItcls"

# अगर तुम Render पर webhook mode चलाना चाहो तो RENDER_APP भर दो (जैसे: yt-downloade)
RENDER_APP = os.environ.get("RENDER_APP")  # example: "yt-downloade"
# या सीधे एक full webhook url भी दे सकते हो: WEBHOOK_URL env var
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# Mode override: अगर WEBHOOK_MODE=1 सेट होगा तो webhook इस्तेमाल करेगा
WEBHOOK_MODE = os.environ.get("WEBHOOK_MODE", "0") == "1"

# Cookie options
COOKIE_FILE = os.environ.get("COOKIE_FILE")         # e.g. /etc/secrets/cookies.txt on Render
COOKIE_CONTENT = os.environ.get("COOKIE_CONTENT")   # or paste whole cookie text in env (secret)
GEO_BYPASS_COUNTRY = os.environ.get("GEO_BYPASS_COUNTRY")  # optional, e.g. "IN"

# limits
MAX_BYTES = 100 * 1024 * 1024  # 100 MB

# download dir (writable)
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "ytbot_downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ytbot")

# ---------------- helpers ----------------
def prepare_cookie_local() -> Optional[str]:
    """Return a writable cookie file path for yt-dlp, or None."""
    try:
        local = DOWNLOAD_DIR / "cookies.txt"
        if COOKIE_CONTENT:
            with open(local, "w", encoding="utf-8") as f:
                f.write(COOKIE_CONTENT)
            logger.info("Written COOKIE_CONTENT to %s", local)
            return str(local)

        if COOKIE_FILE and os.path.exists(COOKIE_FILE) and os.access(COOKIE_FILE, os.R_OK):
            with open(COOKIE_FILE, "r", encoding="utf-8") as rf:
                data = rf.read()
            with open(local, "w", encoding="utf-8") as wf:
                wf.write(data)
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
    if GEO_BYPASS_COUNTRY:
        opts["geo_bypass_country"] = GEO_BYPASS_COUNTRY
    if cookie_local:
        opts["cookiefile"] = cookie_local
    return opts

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

async def yt_download(url: str, cookie_local: Optional[str] = None) -> Path:
    loop = asyncio.get_event_loop()
    opts = build_ydl_opts(cookie_local=cookie_local)

    def _download():
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

    path = await loop.run_in_executor(None, _download)
    return Path(path)

# ---------------- Telegram handlers ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("नमस्ते! YouTube लिंक भेजो — मैं 100MB तक का वीडियो डाउनलोड करके भेज दूँगा।")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if not text or ("youtube.com" not in text and "youtu.be" not in text):
        await update.message.reply_text("कृपया एक valid YouTube लिंक भेजें।")
        return

    await update.message.reply_text("🔎 वीडियो जानकारी ले रहा हूँ — थोड़ी देर...")

    cookie_local = prepare_cookie_local()

    # first get info
    try:
        opts_info = build_ydl_opts(cookie_local=cookie_local)
        opts_info["skip_download"] = True
        with yt_dlp.YoutubeDL(opts_info) as ydl:
            info = ydl.extract_info(text, download=False)
    except DownloadError as e:
        err = str(e)
        logger.info("DownloadError on extract_info: %s", err)
        if "Sign in to confirm" in err or "use --cookies" in err.lower():
            await update.message.reply_text(
                "त्रुटि: YouTube sign-in/captcha माँग रहा है — cookies उपयोग करने से चलेगा।\n"
                "यदि तुमने cookies अपलोड की हैं, उन्हें refresh करके retry करो।"
            )
        else:
            await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {err}")
        return
    except Exception as e:
        logger.exception("extract_info error")
        await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {e}")
        return

    estimated = estimate_size(info)
    size_mb = estimated / (1024 * 1024) if estimated else None
    if size_mb:
        await update.message.reply_text(f"अनुमानित आकार: {size_mb:.2f} MB")
    else:
        await update.message.reply_text("अनुमानित आकार उपलब्ध नहीं है — आगे बढ़कर पता लगाएंगे।")

    if estimated and estimated > MAX_BYTES:
        await update.message.reply_text(
            f"⚠️ यह वीडियो ~{size_mb:.1f}MB का है — अधिकतम सीमा {MAX_BYTES/(1024*1024):.0f}MB है।"
        )
        return

    await update.message.reply_text("📥 डाउनलोड शुरू कर रहा हूँ — कृपया धैर्य रखें...")

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

    try:
        await context.bot.send_document(chat_id, document=open(path, "rb"), filename=path.name, caption=info.get("title"))
        await update.message.reply_text("✅ भेज दिया गया।")
    except Exception as e:
        logger.exception("Error sending file")
        await update.message.reply_text(f"फाइल भेजने में दिक्कत: {e}\n(टीप: Telegram की file-size limit लग सकती है)")
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

# ---------------- main ----------------
def main():
    if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_YOUR_BOT_TOKEN"):
        logger.error("BOT_TOKEN missing. Set BOT_TOKEN env or hardcode it.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    # Decide mode:
    use_webhook = WEBHOOK_MODE or bool(WEBHOOK_URL) or bool(RENDER_APP)
    if use_webhook:
        # Build webhook url
        if WEBHOOK_URL:
            webhook_url = WEBHOOK_URL
        elif RENDER_APP:
            webhook_url = f"https://{RENDER_APP}.onrender.com/{BOT_TOKEN}"
        else:
            logger.error("Webhook mode requested but no WEBHOOK_URL or RENDER_APP set.")
            return

        # set webhook and run
        logger.info("Setting webhook to %s", webhook_url)
        # delete existing and set
        app.bot.delete_webhook(drop_pending_updates=True)
        app.bot.set_webhook(webhook_url)
        port = int(os.environ.get("PORT", 8443))
        logger.info("Running webhook server on port %s", port)
        app.run_webhook(listen="0.0.0.0", port=port, url_path=BOT_TOKEN, webhook_url=webhook_url)
    else:
        logger.info("Starting polling mode (run in shell).")
        app.run_polling()

if __name__ == "__main__":
    main()
