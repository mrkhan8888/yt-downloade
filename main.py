# main.py
import os
import sqlite3
import tempfile
import asyncio
from pathlib import Path

from yt_dlp import YoutubeDL
from aiofiles import open as aio_open

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---- CONFIG ----
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "PUT_YOUR_TOKEN_HERE"
ADMIN_ID = int(os.environ.get("ADMIN_ID") or 5073222820)

DB_PATH = "bot_users.db"
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "ytbot_downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# thresholds (bytes)
FREE_LIMIT = 20 * 1024 * 1024  # 20 MB

# ---- DB helpers ----
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            activated INTEGER DEFAULT 0,
            share1 INTEGER DEFAULT 0,
            share2 INTEGER DEFAULT 0,
            share3 INTEGER DEFAULT 0
        )"""
    )
    conn.commit()
    conn.close()

def ensure_user(uid: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()
    conn.close()

def is_activated(uid: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT activated FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def set_activated(uid: int, val: bool):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ensure_user(uid)
    cur.execute("UPDATE users SET activated=? WHERE user_id=?", (1 if val else 0, uid))
    conn.commit()
    conn.close()

def set_share_flag(uid:int, idx:int, val:int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ensure_user(uid)
    col = f"share{idx}"
    cur.execute(f"UPDATE users SET {col}=? WHERE user_id=?", (1 if val else 0, uid))
    conn.commit()
    conn.close()

def get_share_flags(uid:int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ensure_user(uid)
    cur.execute("SELECT share1,share2,share3 FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    if row:
        return list(row)
    return [0,0,0]

# ---- yt-dlp helpers ----
YDL_OPTS_INFO = {"quiet": True, "skip_download": True}
YDL_OPTS_DL = {
    "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
    "format": "bestvideo+bestaudio/best",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
}

def get_info(url: str):
    with YoutubeDL(YDL_OPTS_INFO) as ydl:
        info = ydl.extract_info(url, download=False)
    return info

def estimate_size_from_info(info) -> int:
    # try a few common fields
    # if playlist, take first entry
    if info is None:
        return 0
    if info.get("entries"):
        info = info["entries"][0]
    # prefer filesize fields
    fs = info.get("filesize") or info.get("filesize_approx")
    if fs:
        return int(fs)
    # else try formats
    best = 0
    for f in info.get("formats", []) or []:
        for key in ("filesize", "filesize_approx"):
            v = f.get(key)
            if v:
                best = max(best, int(v))
    return best

async def download_and_return_path(url: str, loop=None) -> Path:
    # download with yt-dlp synchronously but avoid blocking via run_in_executor
    def _download():
        with YoutubeDL(YDL_OPTS_DL) as ydl:
            info = ydl.extract_info(url, download=True)
            # find the downloaded filename
            fn = ydl.prepare_filename(info)
            # if merge extension changed (e.g. .mp4)
            # try common output names
            p = Path(fn)
            if p.exists():
                return p
            # try mp4 variant
            mp4 = p.with_suffix(".mp4")
            if mp4.exists():
                return mp4
            return p  # best effort
    loop = loop or asyncio.get_event_loop()
    filepath = await loop.run_in_executor(None, _download)
    return Path(filepath)

# ---- Telegram handlers ----
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "नमस्ते! मैं YouTube/Shorts/ Reels डाउनलोड बॉट हूँ.\n\n"
        "— किसी भी YouTube लिंक को यहाँ भेजो, मैं उसका साइज़ देख कर बताऊँगा और डाउनलोड कर दूँगा।\n"
        f"— Free डाउनलोड: 0 — {FREE_LIMIT//(1024*1024)} MB तक。\n"
        "— बड़ा विडियो (>20MB) के लिए शेयर कन्फर्म करना पड़ेगा या admin से activate कराना होगा।\n\n"
        "Usage:\n• बस YouTube लिंक भेजो।\n• Admin केवल `/activate <user_id>` और `/deactivate <user_id>` commands चला सकता है।"
    )
    await update.message.reply_text(txt)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    ensure_user(user_id)

    # quick URL check
    if not ("youtube.com" in msg or "youtu.be" in msg):
        await update.message.reply_text("कृपया YouTube या Shorts का लिंक भेजें।")
        return

    # fetch info
    await update.message.reply_text("वीडियो जानकारी ले रहा हूँ — थोड़ी देर लगेगी...")
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, get_info, msg)
    except Exception as e:
        await update.message.reply_text(f"त्रुटि: जानकारी निकालने में दिक्कत: {e}")
        return

    est_size = estimate_size_from_info(info)
    title = info.get("title") if info else "video"
    size_mb = est_size / (1024*1024) if est_size else None

    if est_size and est_size <= FREE_LIMIT:
        await update.message.reply_text(f"'{title}' → आकार ≈ {size_mb:.2f} MB — free, डाउनलोड कर रहा हूँ...")
        try:
            path = await download_and_return_path(msg)
        except Exception as e:
            await update.message.reply_text(f"डाउनलोड में एरर: {e}")
            return
        # send file
        try:
            await context.bot.send_document(chat_id=chat_id, document=open(path, "rb"), filename=path.name, caption=title)
        except Exception as e:
            await update.message.reply_text(f"फाइल भेजने में एरर: {e}\n(यदि फाइल बहुत बड़ी है तो Telegram की सर्भर सिमिट हो सकती है.)")
        finally:
            try:
                path.unlink(missing_ok=True)
            except:
                pass
        return

    # est_size > FREE_LIMIT or unknown size
    if is_activated(user_id):
        await update.message.reply_text("आप admin द्वारा activate हैं — अब डाउनलोड शुरू करता हूँ...")
        try:
            path = await download_and_return_path(msg)
        except Exception as e:
            await update.message.reply_text(f"डाउनलोड में एरर: {e}")
            return
        try:
            await context.bot.send_document(chat_id=chat_id, document=open(path, "rb"), filename=path.name, caption=title)
        except Exception as e:
            await update.message.reply_text(f"फाइल भेजने में एरर: {e}")
        finally:
            try:
                path.unlink(missing_ok=True)
            except:
                pass
        return

    # not activated -> require share
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Share (open dialog)", url=f"https://t.me/share/url?url=Check+this+video:+{msg}"),
        ],
        [
            InlineKeyboardButton("Done: Shared to friend #1", callback_data="share_done_1"),
            InlineKeyboardButton("Done: Shared to friend #2", callback_data="share_done_2"),
            InlineKeyboardButton("Done: Shared to friend #3", callback_data="share_done_3"),
        ],
        [
            InlineKeyboardButton("Verify & Download", callback_data=f"verify_dl::{msg}")
        ]
    ])
    text = (
        f"यह फ़ाइल ~{size_mb:.2f} MB हो सकती है। बड़े वीडियो डाउनलोड करने के लिए कृपया नीचे के चरण पूरे करें:\n\n"
        "1) 'Share (open dialog)' से दोस्तों को शेयर करो\n"
        "2) हर बार शेयर करने के बाद 'Done: Shared to friend #N' दबाओ\n"
        "3) जब तीनों Done दबा लिए हों तो 'Verify & Download' दबाओ — फिर मैं फ़ाइल डाउनलोड कर दूँगा।\n\n"
        "यदि आप चाहते हैं कि admin सीधे बिना शेयर के लोगों को allow करे, तो admin से कहें `/activate <your_user_id>`"
    )
    await update.message.reply_text(text, reply_markup=kb)

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data.startswith("share_done_"):
        idx = int(data.split("_")[-1])
        set_share_flag(uid, idx, 1)
        flags = get_share_flags(uid)
        await q.edit_message_text(f"आपने Share Done #{idx} दबाया — Progress: {sum(flags)}/3.\nअब बाकी बटनों को भी पूरा करें, फिर 'Verify & Download' दबाएँ।")
        return

    if data.startswith("verify_dl::"):
        # extract url
        url = data.split("::",1)[1]
        flags = get_share_flags(uid)
        if sum(flags) >= 3:
            await q.edit_message_text("Share प्रमाणित हुआ — अब डाउनलोड शुरू कर रहा हूँ...")
            # call download flow by sending a private message to user (or reuse bot)
            # download and send
            try:
                path = await download_and_return_path(url)
            except Exception as e:
                await context.bot.send_message(chat_id=uid, text=f"डाउनलोड एरर: {e}")
                return
            try:
                await context.bot.send_document(chat_id=uid, document=open(path, "rb"), filename=path.name)
            except Exception as e:
                await context.bot.send_message(chat_id=uid, text=f"फाइल भेजते समय एरर: {e}\nअगर फाइल बहुत बड़ी है तो Telegram की सीमा आ सकती है।")
            finally:
                try:
                    path.unlink(missing_ok=True)
                except:
                    pass
        else:
            await q.edit_message_text(f"आपने अभी केवल {sum(flags)} शेयर-डन किए हैं — 3 चाहिए।")
        return

async def activate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.id
    if sender != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /activate <user_id>")
        return
    try:
        target = int(args[0])
    except:
        await update.message.reply_text("Invalid user id.")
        return
    set_activated(target, True)
    await update.message.reply_text(f"✅ User {target} activated.")

async def deactivate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user.id
    if sender != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /deactivate <user_id>")
        return
    try:
        target = int(args[0])
    except:
        await update.message.reply_text("Invalid user id.")
        return
    set_activated(target, False)
    await update.message.reply_text(f"✅ User {target} deactivated.")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    act = is_activated(uid)
    flags = get_share_flags(uid)
    await update.message.reply_text(f"Your status:\nActivated by admin: {act}\nShare progress: {sum(flags)}/3")

# ---- main ----
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("activate", activate_cmd))
    app.add_handler(CommandHandler("deactivate", deactivate_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    print("Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
