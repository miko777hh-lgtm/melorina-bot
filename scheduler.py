import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import database as db
from banner import broadcast_scheduled_banner
from config import ADMIN_ID

TZ = ZoneInfo("Asia/Tehran")
LAST_INACTIVE_CHECK = None


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
                        print(f"[SCHED] ✅ #{bid} → {count}")
                    except Exception as e:
                        print(f"[SCHED] ❌ #{bid}: {e}")
                        await db.increment_banner_retry(bid)
        except Exception as e:
            print(f"[SCHEDULER] {e}")
        await asyncio.sleep(20)


async def process_inactive_users(context):
    """هر ۲۴ ساعت کاربران غیرفعال رو چک میکنه"""
    while True:
        try:
            await asyncio.sleep(86400)  # ۲۴ ساعت
            days = int(await db.get_setting("inactive_days", "25") or 25)
            users = await db.get_inactive_users(days)
            if not users:
                continue

            # لیست برای ادمین
            text = f"👥 کاربران غیرفعال ({days} روز):\n\n"
            for u in users[:50]:
                uid, uname, fname, last = u
                text += f"👤 {fname} | `{uid}` | @{uname or 'ندارد'}\n"
                # پیام اخطار به کاربر
                try:
                    await context.bot.send_message(
                        uid,
                        "⏰ یه مدته به ربات سر نزدی.\n"
                        "منتظرتیم! 📖"
                    )
                except Exception:
                    pass

            # ارسال به ادمین
            try:
                await context.bot.send_message(ADMIN_ID, text)
            except Exception:
                pass
        except Exception as e:
            print(f"[INACTIVE] {e}")
