import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import asyncio

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! YouTube'da aramak istediğin şeyi yaz.\n"
        "Örnek: yasak elma 17. bölüm"
    )

async def search_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        return

    msg = await update.message.reply_text(f"Aranıyor: {query}...")

    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, do_search, query)
    except Exception as e:
        await msg.edit_text(f"Arama hatası: {e}")
        return

    if not results:
        await msg.edit_text("Sonuç bulunamadı.")
        return

    # Sonuçları listele
    text = f"🔍 *{query}* için sonuçlar:\n\n"
    keyboard = []
    for i, r in enumerate(results[:5], 1):
        title = r.get("title", "?")[:60]
        dur = r.get("duration", 0)
        dur_str = f"{int(dur//60)}:{int(dur%60):02d}" if dur else "?"
        text += f"{i}. {title} ({dur_str})\n"
        keyboard.append([InlineKeyboardButton(
            f"{i}. {title[:40]}",
            callback_data=f"sel|{r['id']}"
        )])

    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

def do_search(query):
    ydl_opts = {
        "quiet": True,
        "cookiefile": "cookies.txt",
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "default_search": "ytsearch5",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch5:{query}", download=False)
        return info.get("entries", []) if info else []

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("|")

    if parts[0] == "sel":
        video_id = parts[1]
        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, fetch_formats, url)
        except Exception as e:
            await query.edit_message_text(f"Hata: {e}")
            return

        keyboard = []
        seen = set()
        for f in info.get("formats", []):
            h = f.get("height")
            if h and h in [240, 360, 480, 720] and h not in seen:
                seen.add(h)
                keyboard.append([InlineKeyboardButton(f"{h}p", callback_data=f"dl|{h}|{video_id}")])

        if not keyboard:
            await query.edit_message_text("Bu video için uygun format yok.")
            return

        keyboard.append([InlineKeyboardButton("🎵 Sadece Ses (MP3)", callback_data=f"dl|audio|{video_id}")])

        await query.edit_message_text(
            f"🎬 {info.get('title','Video')}\n\nKalite seç:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if parts[0] == "dl":
        quality = parts[1]
        video_id = parts[2]
        url = f"https://www.youtube.com/watch?v={video_id}"

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
            await query.edit_message_text(f"⚠️ Dosya {size_mb:.1f} MB, Telegram limiti 50 MB. Daha düşük kalite seç.")
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

def fetch_formats(url):
    ydl_opts = {"quiet": True,
        "cookiefile": "cookies.txt", "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_video(url, quality):
    if quality == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": "/tmp/%(id)s.%(ext)s",
            "quiet": True,
        "cookiefile": "cookies.txt",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        }
    else:
        h = int(quality)
        ydl_opts = {
            "format": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
            "outtmpl": "/tmp/%(id)s.%(ext)s",
            "quiet": True,
        "cookiefile": "cookies.txt",
            "merge_output_format": "mp4",
        }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def main():
    if not TOKEN:
        print("HATA: TELEGRAM_BOT_TOKEN yok!")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_youtube))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("Bot çalışıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
