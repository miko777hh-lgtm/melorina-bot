import database as db


async def send_file_to_user(context, chat_id, file_id_db):
    row = await db.get_file(file_id_db)
    if not row:
        return False
    file_id, ftype, caption = row
    try:
        if ftype == "photo":
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
        return True
    except Exception:
        return False
