import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import database as db
from auto_post import send_channel_post
from config import TIMEZONE, SCHEDULER_INTERVAL

TZ = ZoneInfo(TIMEZONE)


async def process_scheduled(context):
    while True:
        try:
            pending = await db.get_pending_auto_posts()
            now = datetime.now(TZ)
            for pid, chat_id, file_id, ftype, caption, run_at in pending:
                try:
                    run_dt = datetime.fromisoformat(run_at)
                    if run_dt.tzinfo is None:
                        run_dt = run_dt.replace(tzinfo=TZ)
                except Exception:
                    continue
                if run_dt <= now:
                    try:
                        await send_channel_post(context, chat_id, file_id, ftype, caption)
                        await db.mark_auto_post_sent(pid)
                        print(f"[AUTO-POST] ✅ #{pid}")
                    except Exception as e:
                        print(f"[AUTO-POST] ❌ #{pid}: {e}")
                        await db.increment_auto_post_retry(pid)
        except Exception as e:
            print(f"[SCHEDULER] {e}")
        await asyncio.sleep(SCHEDULER_INTERVAL)
