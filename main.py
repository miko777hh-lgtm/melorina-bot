import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

import database as db
from config import BOT_TOKEN, ADMIN_ID, TIMEZONE
from texts import *
from jalali import jalali_to_gregorian
from force_join import is_user_joined, send_join_prompt, check_join_callback
from admin_panel import admin_keyboard, is_admin, show_admin_panel
from user_panel import user_keyboard
from schedule_panel import schedule_panel_keyboard
from settings_panel import settings_keyboard
from banner import send_banner, broadcast_banner
from auto_reply import find_reply
from scheduler import process_scheduled
from backup import backup_loop
from onetime_link import create_onetime_link, use_onetime_link, generate_bot_link
from file_handler import send_file_to_user
from order import notify_admin_new_order

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)


def parse_datetime(text):
    try:
        parts = text.strip().split()
        date_part = parts[0]
        time_part = parts[1] if len(parts) > 1 else "00:00"
        y, m, d = map(int, date_part.split("-"))
        hh, mm = map(int, time_part.split(":"))
        if y < 1500:
            gy, gm, gd = jalali_to_gregorian(y, m, d)
            dt = datetime(gy, gm, gd, hh, mm, tzinfo=TZ)
        else:
            dt = datetime(y, m, d, hh, mm, tzinfo=TZ)
        return dt.isoformat()
    except Exception:
        return None


# ============ استارت ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username, user.first_name)

    args = context.args

    # ─── لینک یکبار مصرف ───
    if args and args[0].startswith("otl_"):
        code = args[0][4:]
        result = await use_onetime_link(code)
        if not result["ok"]:
            reason = result.get("reason")
            if reason == "used":
                await update.message.reply_text(OTL_USED)
            elif reason == "expired":
                await update.message.reply_text(OTL_EXPIRED)
            else:
                await update.message.reply_text(OTL_INVALID)
            return

        if not await is_user_joined(context, user.id):
            await send_join_prompt(update, context)
            return

        await update.message.reply_text(OTL_WELCOME)
        await send_file_to_user(context, user.id, result["file_id_db"])
        await send_banner(context, user.id)
        return

    # ─── سفارش کتاب از وب ───
    if args and args[0].startswith("buy_"):
        book_name = args[0][4:].replace("_", " ")
        await notify_admin_new_order(context, user, book_name)
        await update.message.reply_text(
            ORDER_WELCOME.format(book=book_name, price="به‌زودی ادمین قیمت رو می‌فرسته")
        )
        return

    # ─── استارت معمولی ───
    if not await is_user_joined(context, user.id):
        await send_join_prompt(update, context)
        return

    if is_admin(user.id):
        await show_admin_panel(update, context)
        return

    await update.message.reply_text(
        WELCOME_AFTER_JOIN,
        reply_markup=user_keyboard()
    )


# ============ کال‌بک ============
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # ─── کاربر ───
    if data == "check_join":
        await check_join_callback(update, context)
        return

    if data == "donate":
        support_text = await db.get_setting("donate_text", DONATE)
        await db.set_fsm(user_id, "awaiting_support", {"type": "donate"})
        await query.edit_message_text(
            f"💰 حمایت مالی\n\n{support_text}\n\nپیامت مستقیم میره به ادمین 👇"
        )
        return

    if data == "contact_admin":
        support_text = await db.get_setting("support_text", CONTACT_ADMIN)
        await db.set_fsm(user_id, "awaiting_support", {"type": "support"})
        await query.edit_message_text(
            f"📩 تماس با پشتیبانی\n\n{support_text}"
        )
        return

    # ─── ادمین ───
    if not is_admin(user_id):
        return

    if data == "admin_back":
        await query.edit_message_text(ADMIN_PANEL_TITLE, reply_markup=admin_keyboard())
        return

    if data == "admin_stats":
        users = await db.get_users_count()
        files = await db.get_all_files()
        channels = await db.get_all_channels()
        posts = await db.get_all_auto_posts()
        replies = await db.get_all_auto_replies()
        links = await db.get_all_onetime_links()
        orders = await db.get_all_book_orders()
        msgs = await db.get_all_support_msgs(1000)
        text = (
            f"📊 آمار ربات\n\n"
            f"👥 کاربران: {users}\n"
            f"📁 فایل‌ها: {len(files)}\n"
            f"📢 کانال‌ها: {len(channels)}\n"
            f"📮 پست‌های کانال: {len(posts)}\n"
            f"💬 جواب‌های آماده: {len(replies)}\n"
            f"🔗 لینک‌های یکبار مصرف: {len(links)}\n"
            f"🛒 سفارش‌ها: {len(orders)}\n"
            f"📩 پیام‌ها: {len(msgs)}"
        )
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    # ─── تنظیمات ───
    if data == "admin_settings":
        ap = await db.get_setting("auto_post_enabled", "1")
        ar = await db.get_setting("auto_reply_enabled", "1")
        rf = await db.get_setting("referral_enabled", "0")
        await query.edit_message_text(
            "⚙️ تنظیمات قابلیت‌ها:",
            reply_markup=settings_keyboard(ap, ar, rf)
        )
        return

    if data.startswith("toggle_"):
        km = {
            "toggle_auto_post": "auto_post_enabled",
            "toggle_auto_reply": "auto_reply_enabled",
            "toggle_referral": "referral_enabled",
        }
        key = km.get(data)
        if key:
            cur = await db.get_setting(key, "0")
            await db.set_setting(key, "0" if cur == "1" else "1")
        ap = await db.get_setting("auto_post_enabled", "1")
        ar = await db.get_setting("auto_reply_enabled", "1")
        rf = await db.get_setting("referral_enabled", "0")
        await query.edit_message_reply_markup(reply_markup=settings_keyboard(ap, ar, rf))
        return

    if data == "set_default_channel":
        await db.set_fsm(user_id, "awaiting_default_channel")
        await query.edit_message_text("آیدی کانال پیش‌فرض رو بفرست:")
        return

    if data == "set_ref_count":
        await db.set_fsm(user_id, "awaiting_ref_count")
        await query.edit_message_text("تعداد دعوت رو بفرست:")
        return

    # ─── فایل ───
    if data == "admin_add_file":
        await db.set_fsm(user_id, "awaiting_file")
        await query.edit_message_text("📎 فایل رو با کپشن بفرست:")
        return

    if data == "admin_edit_caption":
        files = await db.get_all_files()
        if not files:
            await query.edit_message_text("📭 فایلی نیست.", reply_markup=admin_keyboard())
            return
        kb = []
        for f in files[:20]:
            t = f[3][:25] if f[3] else "بدون کپشن"
            kb.append([InlineKeyboardButton(f"#{f[0]} — {t}", callback_data=f"editcap_{f[0]}")])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("editcap_"):
        fid = int(data.split("_")[1])
        await db.set_fsm(user_id, "awaiting_new_caption", {"file_id": fid})
        await query.edit_message_text("کپشن جدید رو بفرست:")
        return

    if data == "admin_delete_file":
        files = await db.get_all_files()
        if not files:
            await query.edit_message_text("📭 فایلی نیست.", reply_markup=admin_keyboard())
            return
        kb = []
        for f in files[:20]:
            t = f[3][:25] if f[3] else "بدون کپشن"
            kb.append([InlineKeyboardButton(f"🗑 #{f[0]} — {t}", callback_data=f"delfile_{f[0]}")])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
        await query.edit_message_text("کدوم حذف بشه؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("delfile_"):
        fid = int(data.split("_")[1])
        await db.delete_file(fid)
        await query.edit_message_text("✅ حذف شد.", reply_markup=admin_keyboard())
        return

    if data == "admin_list_files":
        files = await db.get_all_files()
        if not files:
            await query.edit_message_text("📭 فایلی نیست.", reply_markup=admin_keyboard())
            return
        text = "📋 فایل‌ها:\n\n"
        for f in files[:30]:
            t = f[3][:30] if f[3] else "بدون کپشن"
            text += f"#{f[0]} | {f[2]} | {t}\n"
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    # ─── کانال ───
    if data == "admin_add_channel":
        await db.set_fsm(user_id, "awaiting_channel")
        await query.edit_message_text("📢 آیدی کانال رو بفرست:")
        return

    if data == "admin_del_channel":
        channels = await db.get_all_channels()
        if not channels:
            await query.edit_message_text("📭 کانالی نیست.", reply_markup=admin_keyboard())
            return
        kb = [[InlineKeyboardButton(f"🗑 {c[2]}", callback_data=f"delch_{c[0]}")] for c in channels]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("delch_"):
        cid = int(data.split("_")[1])
        await db.delete_channel(cid)
        await query.edit_message_text("✅ حذف شد.", reply_markup=admin_keyboard())
        return

    if data == "admin_list_channels":
        channels = await db.get_all_channels()
        if not channels:
            await query.edit_message_text("📭 کانالی نیست.", reply_markup=admin_keyboard())
            return
        text = "📋 کانال‌ها:\n\n" + "\n".join(f"• {c[2]} — `{c[1]}`" for c in channels)
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    # ─── بنر ───
    if data == "admin_set_banner":
        await db.set_fsm(user_id, "awaiting_banner")
        await query.edit_message_text("🖼 بنر رو بفرست:")
        return

    if data == "admin_broadcast":
        count = await broadcast_banner(context)
        await query.edit_message_text(
            f"✅ ارسال شد به {count} کاربر." if count else "❌ بنری تنظیم نشده.",
            reply_markup=admin_keyboard()
        )
        return

    # ─── Auto-Post ───
    if data == "ap_menu":
        await query.edit_message_text(
            "📮 پست زمان‌بندی کانال\n\nنوع پست:",
            reply_markup=schedule_panel_keyboard()
        )
        return

    if data == "sch_list":
        posts = await db.get_all_auto_posts()
        if not posts:
            await query.edit_message_text("📭 خالیه.", reply_markup=schedule_panel_keyboard())
            return
        text = "📋 پست‌های زمان‌بندی:\n\n"
        for p in posts[:25]:
            sid, chat_id, fid, ftype, cap, run_at, sent = p
            s = "✅" if sent else "⏳"
            text += f"{s} #{sid} | {ftype} | {chat_id} | {run_at[:16]}\n"
        await query.edit_message_text(text, reply_markup=schedule_panel_keyboard())
        return

    if data == "sch_delete":
        posts = await db.get_all_auto_posts()
        if not posts:
            await query.edit_message_text("📭 خالیه.", reply_markup=schedule_panel_keyboard())
            return
        kb = [[InlineKeyboardButton(f"🗑 #{p[0]} | {p[5][:16]}", callback_data=f"schdel_{p[0]}")] for p in posts[:15]]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ap_menu")])
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("schdel_"):
        sid = int(data.split("_")[1])
        await db.delete_auto_post(sid)
        await query.edit_message_text("✅ حذف شد.", reply_markup=schedule_panel_keyboard())
        return

    if data.startswith("sch_"):
        ptype = data.replace("sch_", "")
        default_ch = await db.get_setting("default_channel", "")
        await db.set_fsm(user_id, "ap_step1", {"ptype": ptype, "default_ch": default_ch})
        if default_ch:
            await query.edit_message_text(
                f"✅ نوع: {ptype}\n\n"
                f"📢 کانال پیش‌فرض: `{default_ch}`\n\n"
                f"اگه می‌خوای همین باشه، بنویس: `ok`\n"
                f"یا آیدی کانال دیگه رو بفرست:"
            )
        else:
            await query.edit_message_text(
                f"✅ نوع: {ptype}\n\n🏠 آیدی کانال مقصد:"
            )
        return

    # ─── Auto-Reply ───
    if data == "ar_menu":
        ar_on = await db.get_setting("auto_reply_enabled", "1")
        status = "✅ فعال" if ar_on == "1" else "❌ غیرفعال"
        replies = await db.get_all_auto_replies()
        kb = [
            [InlineKeyboardButton("➕ افزودن جواب", callback_data="ar_add")],
            [InlineKeyboardButton("📋 لیست جواب‌ها", callback_data="ar_list")],
            [InlineKeyboardButton("🗑 حذف جواب", callback_data="ar_delete")],
            [InlineKeyboardButton(f"وضعیت: {status}", callback_data="toggle_auto_reply")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]
        await query.edit_message_text(
            f"💬 جواب‌های آماده گروه\n\nتعداد: {len(replies)}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data == "ar_add":
        await db.set_fsm(user_id, "ar_step1")
        await query.edit_message_text("🔑 کلمه کلیدی رو بفرست:")
        return

    if data == "ar_list":
        replies = await db.get_all_auto_replies()
        if not replies:
            await query.edit_message_text("📭 جوابی نیست.", reply_markup=admin_keyboard())
            return
        text = "📋 جواب‌های آماده:\n\n"
        for r in replies[:30]:
            text += f"#{r[0]} | 🔑 {r[1]}\n💬 {r[2][:50]}\n\n"
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    if data == "ar_delete":
        replies = await db.get_all_auto_replies()
        if not replies:
            await query.edit_message_text("📭 جوابی نیست.", reply_markup=admin_keyboard())
            return
        kb = [[InlineKeyboardButton(f"🗑 #{r[0]} | {r[1]}", callback_data=f"ardel_{r[0]}")] for r in replies[:15]]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ar_menu")])
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("ardel_"):
        rid = int(data.split("_")[1])
        await db.delete_auto_reply(rid)
        await query.edit_message_text("✅ حذف شد.", reply_markup=admin_keyboard())
        return

    # ─── لینک یکبار مصرف ───
    if data == "otl_menu":
        links = await db.get_all_onetime_links()
        kb = [
            [InlineKeyboardButton("➕ ساخت لینک جدید", callback_data="otl_new")],
            [InlineKeyboardButton("📋 لیست لینک‌ها", callback_data="otl_list")],
            [InlineKeyboardButton("🗑 حذف لینک", callback_data="otl_delete")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]
        await query.edit_message_text(
            f"🔗 لینک‌های یکبار مصرف\n\nتعداد: {len(links)}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data == "otl_new":
        files = await db.get_all_files()
        if not files:
            await query.edit_message_text("📭 فایلی نیست.", reply_markup=admin_keyboard())
            return
        kb = []
        for f in files[:20]:
            t = f[3][:25] if f[3] else "بدون کپشن"
            kb.append([InlineKeyboardButton(f"#{f[0]} — {t}", callback_data=f"otl_file_{f[0]}")])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="otl_menu")])
        await query.edit_message_text("کدوم فایل؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("otl_file_"):
        fid = int(data.split("_")[2])
        await db.set_fsm(user_id, "otl_step1", {"file_id_db": fid})
        await query.edit_message_text(
            "⏰ مدت اعتبار لینک (ساعت):\n\n"
            "مثال: `24` = ۲۴ ساعت\n"
            "`0` = بدون انقضا"
        )
        return

    if data == "otl_list":
        links = await db.get_all_onetime_links()
        if not links:
            await query.edit_message_text("📭 لینکی نیست.", reply_markup=admin_keyboard())
            return
        text = "🔗 لینک‌ها:\n\n"
        for l in links[:20]:
            lid, code, fid, used, exp, created = l
            s = "✅ استفاده شده" if used else "🟢 فعال"
            text += f"#{lid} | `{code}`\n   فایل: #{fid} | {s}\n\n"
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    if data == "otl_delete":
        links = await db.get_all_onetime_links()
        if not links:
            await query.edit_message_text("📭 لینکی نیست.", reply_markup=admin_keyboard())
            return
        kb = [[InlineKeyboardButton(f"🗑 #{l[0]} | {l[1]}", callback_data=f"otldel_{l[0]}")] for l in links[:15]]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="otl_menu")])
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("otldel_"):
        lid = int(data.split("_")[1])
        await db.delete_onetime_link(lid)
        await query.edit_message_text("✅ حذف شد.", reply_markup=admin_keyboard())
        return

    # ─── سفارش‌های کتاب ───
    if data == "orders_menu":
        orders = await db.get_all_book_orders()
        if not orders:
            await query.edit_message_text(
                "🛒 هیچ سفارشی نیست.",
                reply_markup=admin_keyboard()
            )
            return
        text = "🛒 سفارش‌های اخیر:\n\n"
        for o in orders[:20]:
            oid, uid, name, book, price, status, created = o
            s = {"pending": "⏳ در انتظار", "price_sent": "💵 قیمت ارسال شد", "paid": "✅ پرداخت شده"}.get(status, status)
            text += f"#{oid} | {book}\n  👤 {name} | {s}\n  💰 {price or 'تعیین نشده'}\n\n"
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    if data.startswith("order_price_"):
        oid = int(data.split("_")[2])
        order = await db.get_book_order(oid)
        if not order:
            await query.edit_message_text("❌ سفارش پیدا نشد.")
            return
        await db.set_fsm(user_id, "order_step_price", {"order_id": oid})
        await query.edit_message_text(
            f"💵 مبلغ کتاب «{order[4]}» رو بفرست (فقط عدد، تومان):"
        )
        return

    if data.startswith("order_view_"):
        oid = int(data.split("_")[2])
        order = await db.get_book_order(oid)
        if not order:
            await query.edit_message_text("❌ سفارش پیدا نشد.")
            return
        oid, uid, username, fname, book, price, status = order
        text = (
            f"🛒 سفارش #{oid}\n\n"
            f"📚 کتاب: {book}\n"
            f"👤 نام: {fname}\n"
            f"🆔 `{uid}`\n"
            f"📛 @{username or 'ندارد'}\n"
            f"💰 قیمت: {price or 'تعیین نشده'}\n"
            f"📊 وضعیت: {status}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")
        return

    # ─── پنل پیام به ادمین ───
    if data == "sup_menu":
        msgs = await db.get_all_support_msgs(30)
        support_text = await db.get_setting("support_text", CONTACT_ADMIN)
        donate_text = await db.get_setting("donate_text", "اگه دوست داشتی حمایت کن.")
        kb = [
            [InlineKeyboardButton("📋 آخرین پیام‌ها", callback_data="sup_list")],
            [InlineKeyboardButton("✏️ ویرایش متن پشتیبانی", callback_data="sup_edit_support")],
            [InlineKeyboardButton("✏️ ویرایش متن حمایت", callback_data="sup_edit_donate")],
            [InlineKeyboardButton("🗑 پاک کردن همه پیام‌ها", callback_data="sup_clear")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]
        await query.edit_message_text(
            f"📩 پنل پیام‌ها\n\n"
            f"📬 تعداد پیام‌ها: {len(msgs)}\n\n"
            f"متن فعلی پشتیبانی:\n{support_text[:60]}...\n\n"
            f"متن فعلی حمایت:\n{donate_text[:60]}...",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data == "sup_list":
        msgs = await db.get_all_support_msgs(20)
        if not msgs:
            await query.edit_message_text("📭 پیامی نیست.", reply_markup=admin_keyboard())
            return
        text = "📩 آخرین پیام‌ها:\n\n"
        for m in msgs[:10]:
            mid, uid, fname, mtype, txt, seen, created = m
            tag = "💰" if mtype == "donate" else "📩"
            text += f"{tag} #{mid} | {fname} | {created[:16]}\n{txt[:60]}\n\n"
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    if data == "sup_edit_support":
        await db.set_fsm(user_id, "sup_edit_support")
        await query.edit_message_text("✏️ متن جدید پشتیبانی رو بفرست:")
        return

    if data == "sup_edit_donate":
        await db.set_fsm(user_id, "sup_edit_donate")
        await query.edit_message_text("✏️ متن جدید حمایت مالی رو بفرست:")
        return

    if data == "sup_clear":
        msgs = await db.get_all_support_msgs(1000)
        for m in msgs:
            await db.delete_support_msg(m[0])
        await query.edit_message_text("✅ همه پیام‌ها پاک شدند.", reply_markup=admin_keyboard())
        return


# ============ هندلر پیام ============
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    if not msg:
        return

    state, data = await db.get_fsm(user.id)

    # ─── گروه: جواب خودکار ───
    if msg.chat.type in ("group", "supergroup"):
        ar_on = await db.get_setting("auto_reply_enabled", "1")
        if ar_on == "1" and msg.text:
            reply = await find_reply(msg.text)
            if reply:
                await msg.reply_text(reply)
        return

    # ─── چت خصوصی ───
    if not await is_user_joined(context, user.id):
        await send_join_prompt(update, context)
        return

    # ─── FSM ادمین ───
    if is_admin(user.id):

        # ─── ویرایش متن‌ها ───
        if state == "sup_edit_support":
            await db.set_setting("support_text", msg.text or "")
            await msg.reply_text("✅ متن پشتیبانی آپدیت شد.")
            await db.clear_fsm(user.id)
            return

        if state == "sup_edit_donate":
            await db.set_setting("donate_text", msg.text or "")
            await msg.reply_text("✅ متن حمایت آپدیت شد.")
            await db.clear_fsm(user.id)
            return

        # ─── سفارش: گرفتن قیمت ───
        if state == "order_step_price":
            oid = data.get("order_id")
            price = (msg.text or "").strip()
            await db.set_order_price(oid, price)
            await db.set_order_status(oid, "price_sent")
            order = await db.get_book_order(oid)
            if order:
                uid = order[1]
                book = order[4]
                try:
                    await context.bot.send_message(
                        uid,
                        f"💳 شماره کارت برای کتاب «{book}»:\n\n"
                        f"💰 مبلغ: {price} تومان\n\n"
                        f"📌 شماره کارت:\n`5892-1014-8785-8611`\n"
                        f"👤 به نام: شیرین نورزایی\n\n"
                        f"بعد از پرداخت، رسیدت رو همین‌جا بفرست.",
                        parse_mode="Markdown"
                    )
                    await msg.reply_text("✅ شماره کارت برای کاربر ارسال شد.")
                except Exception as e:
                    await msg.reply_text(f"❌ خطا در ارسال به کاربر: {e}")
            await db.clear_fsm(user.id)
            return

        # ─── فایل ───
        if state == "awaiting_file":
            ftype, file_id = None, None
            if msg.photo:
                ftype, file_id = "photo", msg.photo[-1].file_id
            elif msg.video:
                ftype, file_id = "video", msg.video.file_id
            elif msg.audio:
                ftype, file_id = "audio", msg.audio.file_id
            elif msg.voice:
                ftype, file_id = "voice", msg.voice.file_id
            elif msg.animation:
                ftype, file_id = "animation", msg.animation.file_id
            elif msg.document:
                ftype, file_id = "document", msg.document.file_id
            if file_id:
                fid = await db.add_file(file_id, ftype, msg.caption or "")
                await msg.reply_text(
                    f"✅ ذخیره شد. (ID: #{fid})\n"
                    f"کپشن: {msg.caption or 'بدون کپشن'}"
                )
            else:
                await msg.reply_text("❌ فایلی نبود.")
            await db.clear_fsm(user.id)
            return

        if state == "awaiting_new_caption":
            await db.update_caption(data.get("file_id"), msg.text or "")
            await msg.reply_text("✅ آپدیت شد.")
            await db.clear_fsm(user.id)
            return

        if state == "awaiting_channel":
            try:
                chat = await context.bot.get_chat(msg.text.strip())
                invite = f"https://t.me/{chat.username}" if chat.username else chat.invite_link
                await db.add_channel(str(chat.id), chat.title, invite)
                await msg.reply_text(f"✅ {chat.title} اضافه شد.")
            except Exception as e:
                await msg.reply_text(f"❌ {e}")
            await db.clear_fsm(user.id)
            return

        if state == "awaiting_banner":
            ftype, file_id = None, None
            if msg.photo:
                ftype, file_id = "photo", msg.photo[-1].file_id
            elif msg.video:
                ftype, file_id = "video", msg.video.file_id
            elif msg.animation:
                ftype, file_id = "animation", msg.animation.file_id
            elif msg.document:
                ftype, file_id = "document", msg.document.file_id
            if file_id:
                await db.set_banner(file_id, ftype, msg.caption or "")
                await msg.reply_text("✅ بنر تنظیم شد.")
            else:
                await msg.reply_text("❌ بنر نبود.")
            await db.clear_fsm(user.id)
            return

        if state == "awaiting_default_channel":
            await db.set_setting("default_channel", msg.text.strip())
            await msg.reply_text(f"✅ کانال پیش‌فرض: {msg.text.strip()}")
            await db.clear_fsm(user.id)
            return

        if state == "awaiting_ref_count":
            try:
                n = int(msg.text.strip())
                await db.set_setting("referral_count", str(n))
                await msg.reply_text(f"✅ تعداد دعوت: {n}")
            except Exception:
                await msg.reply_text("❌ عدد بفرست.")
            await db.clear_fsm(user.id)
            return

        # ─── Auto-Post ───
        if state == "ap_step1":
            txt = (msg.text or "").strip()
            if txt.lower() == "ok" and data.get("default_ch"):
                data["chat_id"] = data["default_ch"]
            else:
                data["chat_id"] = txt
            await db.set_fsm(user.id, "ap_step2", data)
            await msg.reply_text(f"✅ کانال: {data['chat_id']}\n\n📎 محتوا رو بفرست:")
            return

        if state == "ap_step2":
            ptype = data.get("ptype")
            file_id = None
            if ptype == "text":
                file_id = msg.text or ""
            elif ptype == "photo" and msg.photo:
                file_id = msg.photo[-1].file_id
            elif ptype == "video" and msg.video:
                file_id = msg.video.file_id
            elif ptype == "document" and msg.document:
                file_id = msg.document.file_id
            elif ptype == "audio" and msg.audio:
                file_id = msg.audio.file_id
            elif ptype == "voice" and msg.voice:
                file_id = msg.voice.file_id
            elif ptype == "animation" and msg.animation:
                file_id = msg.animation.file_id
            else:
                await msg.reply_text(f"❌ باید {ptype} بفرستی.")
                return
            data["file_id"] = file_id
            data["caption"] = msg.caption or (msg.text if ptype == "text" else "")
            await db.set_fsm(user.id, "ap_step3", data)
            await msg.reply_text(
                "✅ ثبت شد.\n\n⏰ زمان دقیق:\n"
                "📅 میلادی: `2026-10-01 20:30`\n"
                "📅 شمسی: `1404-07-15 20:30`"
            )
            return

        if state == "ap_step3":
            run_at = parse_datetime(msg.text.strip())
            if not run_at:
                await msg.reply_text("❌ فرمت اشتباه.\nدوباره: `YYYY-MM-DD HH:MM`")
                return
            await db.add_auto_post(data["chat_id"], data["file_id"],
                                    data.get("ptype"), data.get("caption"), run_at)
            await db.clear_fsm(user.id)
            await msg.reply_text(
                f"✅ پست زمان‌بندی شد!\n\n📅 {run_at[:16]}\n📢 {data['chat_id']}"
            )
            return

        # ─── Auto-Reply ───
        if state == "ar_step1":
            data["keyword"] = msg.text or ""
            await db.set_fsm(user.id, "ar_step2", data)
            await msg.reply_text("💬 جواب رو بفرست:")
            return

        if state == "ar_step2":
            data["reply"] = msg.text or ""
            await db.set_fsm(user.id, "ar_step3", data)
            await msg.reply_text(
                "🔍 حالت تطبیق:\n"
                "`exact` = دقیق\n"
                "`contain` = شامل\n\n"
                "بنویس: exact یا contain"
            )
            return

        if state == "ar_step3":
            txt = (msg.text or "").lower().strip()
            exact = 1 if txt == "exact" else 0
            await db.add_auto_reply(data["keyword"], data["reply"], exact)
            await db.clear_fsm(user.id)
            await msg.reply_text("✅ جواب اضافه شد.")
            return

        # ─── Onetime Link ───
        if state == "otl_step1":
            try:
                hours = int(msg.text.strip())
            except Exception:
                await msg.reply_text("❌ عدد بفرست.")
                return
            fid = data.get("file_id_db")
            code = await create_onetime_link(fid, hours)
            bot_info = await context.bot.get_me()
            link = await generate_bot_link(bot_info.username, code)
            await db.clear_fsm(user.id)
            expire_text = f"{hours} ساعت" if hours > 0 else "بدون انقضا"
            await msg.reply_text(
                f"✅ لینک ساخته شد!\n\n"
                f"📁 فایل: #{fid}\n"
                f"⏰ اعتبار: {expire_text}\n\n"
                f"🔗 `{link}`\n\n"
                f"(کپی کن و برای خریدار بفرست)"
            )
            return

    # ─── FSM کاربر: پیام به ادمین ───
    if state == "awaiting_support":
        mtype = data.get("type", "support")

        # ذخیره تو دیتابیس
        file_id_db = None
        file_type_db = None
        if msg.photo:
            file_id_db = msg.photo[-1].file_id
            file_type_db = "photo"
        elif msg.video:
            file_id_db = msg.video.file_id
            file_type_db = "video"
        elif msg.document:
            file_id_db = msg.document.file_id
            file_type_db = "document"

        await db.add_support_msg(
            user.id, user.username, user.first_name,
            mtype, msg.text or msg.caption or "",
            file_id_db, file_type_db
        )

        # ارسال به ادمین
        tag = "💰 حمایت مالی" if mtype == "donate" else "📩 پیام جدید"
        text = (
            f"{tag}\n\n"
            f"👤 {user.first_name}\n"
            f"🆔 `{user.id}`\n"
            f"📛 @{user.username or 'ندارد'}\n\n"
            f"💬 {msg.text or msg.caption or '(بدون متن)'}"
        )
        try:
            await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
            if msg.photo:
                await context.bot.send_photo(ADMIN_ID, msg.photo[-1].file_id)
            elif msg.video:
                await context.bot.send_video(ADMIN_ID, msg.video.file_id)
            elif msg.document:
                await context.bot.send_document(ADMIN_ID, msg.document.file_id)
        except Exception:
            pass

        await msg.reply_text(
            "✅ پیامت رسید دست ادمین.\nبه‌زودی جواب می‌گیری."
        )
        await db.clear_fsm(user.id)
        return

    # ─── فایل معمولی ───
    if msg.photo or msg.video or msg.document or msg.audio or msg.voice or msg.animation:
        await msg.reply_text(FILE_SENT)
        await send_banner(context, msg.chat_id)
        return

    await msg.reply_text(FILE_NOT_FOUND)


# ============ Post Init ============
async def post_init(app):
    asyncio.create_task(process_scheduled(app))
    asyncio.create_task(backup_loop(app))


# ============ اجرا ============
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN نیست!")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(db.init_db())
    loop.close()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    print("🚀 ربات روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
