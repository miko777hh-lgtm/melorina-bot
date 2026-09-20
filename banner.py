import asyncio
import database as db


async def send_banner(context, chat_id):
    banner = await db.get_banner()
    if not banner:
        return
    file_id, ftype, caption = banner
    try:
        if ftype == "photo":
            await context.bot.send_photo(chat_id, file_id, caption=caption)
        elif ftype == "video":
            await context.bot.send_video(chat_id, file_id, caption=caption)
        elif ftype == "animation":
            await context.bot.send_animation(chat_id, file_id, caption=caption)
        else:
            await context.bot.send_document(chat_id, file_id, caption=caption)
    except Exception as e:
        print(f"[BANNER] {e}")


async def broadcast_banner(context):
    banner = await db.get_banner()
    if not banner:
        return 0
    file_id, ftype, caption = banner
    users = await db.get_all_users()
    count = 0
    for uid in users:
        try:
            if ftype == "photo":
                await context.bot.send_photo(uid, file_id, caption=caption)
            elif ftype == "video":
                await context.bot.send_video(uid, file_id, caption=caption)
            elif ftype == "animation":
                await context.bot.send_animation(uid, file_id, caption=caption)
            else:
                await context.bot.send_document(uid, file_id, caption=caption)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            continue
    return count
