from datetime import datetime
from zoneinfo import ZoneInfo
from config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)


async def send_channel_post(context, chat_id, file_id, ftype, caption):
    caption = caption or None
    if ftype == "text":
        await context.bot.send_message(chat_id, caption or "", disable_web_page_preview=True)
    elif ftype == "photo":
        await context.bot.send_photo(chat_id, file_id, caption=caption)
    elif ftype == "video":
        await context.bot.send_video(chat_id, file_id, caption=caption)
    elif ftype == "audio":
        await context.bot.send_audio(chat_id, file_id, caption=caption)
    elif ftype == "voice":
        await context.bot.send_voice(chat_id, file_id, caption=caption)
    elif ftype == "animation":
        await context.bot.send_animation(chat_id, file_id, caption=caption)
    else:
        await context.bot.send_document(chat_id, file_id, caption=caption)
