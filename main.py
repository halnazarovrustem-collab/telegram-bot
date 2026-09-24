import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import asyncio

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Video linkini geçici olarak sakla
pending = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Bana bir YouTube linki at, sana kalite seçeneklerini göstereyim.\n"
        "Örnek: https://youtube.com/watch?v=..."
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("Lütfen geçerli bir YouTube linki gönder.")
        return

    msg = await update.message.reply_text("Videonun kaliteleri alınıyor...")

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, fetch_formats, url)
    except Exception as e:
        await msg.edit_text(f"Hata: {e}")
        return

    if not info or not info.get("formats"):
        await msg.edit_text("Bu video için format bulunamadı.")
        return

    # Kalite seçenekleri (240p, 360p, 480p, 720p)
    keyboard = []
    seen = set()
    for f in info["formats"]:
        h = f.get("height")
        if h and h in [240, 360, 480, 720] and h not in seen:
            seen.add(h)
            keyboard.append([InlineKeyboardButton(
                f"{h}p",
                callback_data=f"{h}|{url}"
            )])

    if not keyboard:
        await msg.edit_text("Bu video için 240p-720p arası format yok.")
        return

    keyboard.append([InlineKeyboardButton("Sadece Ses (MP3)", callback_data=f"audio|{url}")])

    await msg.edit_text(
        f"🎬 {info.get('title','Video')}\n\nKalite seç:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def fetch_formats(url):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if "|" not in data:
        return

    quality, url = data.split("|", 1)
    await query.edit_message_text(f"İndiriliyor: {quality}... Lütfen bekle.")

    try:
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, download_video, url, quality)
    except Exception as e:
        await query.edit_message_text(f"İndirme hatası: {e}")
        return

    if not file_path or not os.path.exists(file_path):
        await query.edit_message_text("İndirme başarısız.")
        return

    size_mb = os.path.getsize(file_path) / (1024 * 1024)

    if size_mb > 50:
        await query.edit_message_text(
            f"⚠️ Dosya {size_mb:.1f} MB, Telegram bot limiti 50 MB.\n"
            f"Daha düşük kalite seç veya yerel API kullan."
        )
        os.remove(file_path)
        return

    await query.edit_message_text(f"Yükleniyor ({size_mb:.1f} MB)...")

    try:
        if quality == "audio":
            await query.message.reply_audio(audio=open(file_path, "rb"))
        else:
            await query.message.reply_video(video=open(file_path, "rb"))
        await query.delete_message()
    except Exception as e:
        await query.edit_message_text(f"Yükleme hatası: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def download_video(url, quality):
    if quality == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": "/tmp/%(id)s.%(ext)s",
            "quiet": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }],
        }
    else:
        h = int(quality)
        ydl_opts = {
            "format": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
            "outtmpl": "/tmp/%(id)s.%(ext)s",
            "quiet": True,
            "merge_output_format": "mp4",
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def main():
    if not TOKEN:
        print("HATA: TELEGRAM_BOT_TOKEN ortam değişkeni yok!")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Bot çalışıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
