import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from config import ADMIN_ID, DB_PATH, TIMEZONE, BACKUP_INTERVAL

TZ = ZoneInfo(TIMEZONE)


async def backup_loop(context):
    while True:
        try:
            await asyncio.sleep(BACKUP_INTERVAL)
            if not os.path.exists(DB_PATH):
                continue
            now = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M")
            with open(DB_PATH, "rb") as f:
                await context.bot.send_document(
                    ADMIN_ID,
                    document=f,
                    filename=f"backup_{now}.sqlite3",
                    caption=f"🗄 بکاپ خودکار\n📅 {now}"
                )
        except Exception as e:
            print(f"[BACKUP] {e}")
