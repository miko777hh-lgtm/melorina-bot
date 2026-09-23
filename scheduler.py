import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import database as db
from config import TIMEZONE, SCHEDULER_INTERVAL

TZ = ZoneInfo(TIMEZONE)


async def process_scheduled(context):
    while True:
        try:
            pending = await db.get_pending_scheduled()
            now = datetime.now(TZ)
            for sid, chat_id, file_id, ftype, caption, run_at in pending:
                try:
                    run_dt = datetime.fromisoformat(run_at)
                    if run_dt.tzinfo is None:
                        run_dt = run_dt.replace(tzinfo=TZ)
                except Exception:
                    continue
                if run_dt <= now:
                    try:
                        await send_post(context, chat_id, file_id, ftype, caption)
                        await db.mark_sent(sid)
                    except Exception as e:
                        print(f"[SCHED] خطا #{sid}: {e}")
                        await db.increment_retry(sid)
        except Exception as e:
            print(f"[SCHED] {e}")
        await asyncio.sleep(SCHEDULER_INTERVAL)


async def send_post(context, chat_id, file_id, ftype, caption):
    caption = caption or None
    if ftype == "text":
        await context.bot.send_message(chat_id, caption or "")
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
