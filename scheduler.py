import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import database as db
from banner import broadcast_scheduled_banner, send_captured
from config import ADMIN_ID
from texts import REMINDER_MSG

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
                        print(f"[SCHED] ✅ #{bid} → {count}")
                    except Exception as e:
                        print(f"[SCHED] ❌ #{bid}: {e}")
                        await db.increment_banner_retry(bid)
        except Exception as e:
            print(f"[SCHEDULER] {e}")
        await asyncio.sleep(20)


async def process_inactive_users(context):
    while True:
        try:
            await asyncio.sleep(86400)
            days = int(await db.get_setting("inactive_days", "25") or 25)
            users = await db.get_inactive_users(days)
            if not users:
                continue
            text = f"👥 کاربران غیرفعال ({days} روز):\n\n"
            for u in users[:50]:
                uid, uname, fname, last = u
                text += f"👤 {fname} | `{uid}` | @{uname or 'ندارد'}\n"
                try:
                    await context.bot.send_message(uid, REMINDER_MSG)
                except Exception:
                    pass
            try:
                await context.bot.send_message(ADMIN_ID, text)
            except Exception:
                pass
        except Exception as e:
            print(f"[INACTIVE] {e}")


async def process_upcoming_books(context):
    """هر روز اطلاعات کتاب‌های بزودی رو برای رزروکننده‌ها بفرست"""
    while True:
        try:
            await asyncio.sleep(86400)
            books = await db.get_upcoming_books()
            for b in books:
                bid, title_fa, title_en, author = b
                users = await db.get_book_reservations(bid)
                if not users:
                    continue
                info = f"🔔 کتاب بزودی میاد:\n\n📖 {title_fa}\n"
                if title_en:
                    info += f"📕 {title_en}\n"
                if author:
                    info += f"✍️ {author}\n"
                for uid in users:
                    try:
                        await context.bot.send_message(uid, info)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[UPCOMING] {e}")


async def process_reading_reminder(context):
    """یادآور خواندن برای کاربرانی که N روز کتاب نخوندن"""
    while True:
        try:
            await asyncio.sleep(86400 * 3)  # هر ۳ روز
            days = int(await db.get_setting("reminder_days", "7") or 7)
            users = await db.get_inactive_users(days)
            for u in users:
                uid = u[0]
                try:
                    await context.bot.send_message(
                        uid,
                        "📖 یادت نره ما هنوز کتابای جدید داریم\n"
                        "سر بزن یه نگاه بنداز 👀"
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"[REMINDER] {e}")
