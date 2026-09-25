import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import database as db
from banner import broadcast_scheduled_banner

TZ = ZoneInfo("Asia/Tehran")


async def process_scheduled_banners(context):
    while True:
        try:
            pending = await db.get_pending_banners()
            now = datetime.now(TZ)
            for bid, message_json, run_at in pending:
                try:
                    run_dt = datetime.fromisoformat(run_at)
                    if run_dt.tzinfo is None:
                        run_dt = run_dt.replace(tzinfo=TZ)
                except Exception:
                    continue
                if run_dt <= now:
                    try:
                        count = await broadcast_scheduled_banner(context, message_json)
                        await db.mark_banner_sent(bid)
                        print(f"[SCHED-BANNER] ✅ #{bid} → {count} کاربر")
                    except Exception as e:
                        print(f"[SCHED-BANNER] ❌ #{bid}: {e}")
                        await db.increment_banner_retry(bid)
        except Exception as e:
            print(f"[SCHEDULER] {e}")
        await asyncio.sleep(20)
