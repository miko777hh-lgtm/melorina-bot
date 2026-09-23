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
from replies import get_ready_reply
from force_join import is_user_joined, send_join_prompt, check_join_callback
from admin_panel import admin_keyboard, is_admin, show_admin_panel
from banner import send_banner, broadcast_banner
from scheduler import process_scheduled
from backup import backup_loop

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)


# پنل زمان‌بندی
def schedule_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 پست متنی", callback_data="sch_text")],
        [InlineKeyboardButton("🖼 پست عکس", callback_data="sch_photo")],
        [InlineKeyboardButton("🎬 پست ویدیو", callback_data="sch_video")],
        [InlineKeyboardButton("📄 پست فایل", callback_data="sch_document")],
        [InlineKeyboardButton("🎵 پست صوتی", callback_data="sch_audio")],
        [InlineKeyboardButton("🎞 گیف", callback_data="sch_animation")],
        [InlineKeyboardButton("🎙 ویس", callback_data="sch_voice")],
        [InlineKeyboardButton("📋 لیست پست‌ها", callback_data="sch_list")],
        [InlineKeyboardButton("🗑 حذف پست", callback_data="sch_delete")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
    ])


def parse_datetime(text):
    try:
        parts = text.strip().split()
        date_part = parts[0]
        time_part = parts[1] if len(parts) > 1 else "00:00"
        y, m, d = map(int, date_part.split("-"))
        hh, mm = map(int, time_part.split(":"))
        if y < 1500:
            from jalali import jalali_to_gregorian
            gy, gm, gd = jalali_to_gregorian(y, m, d)
            dt = datetime(gy, gm, gd, hh, mm, tzinfo=TZ)
        else:
            dt = datetime(y, m, d, hh, mm, tzinfo=TZ)
        return dt.isoformat()
    except Exception:
        return None


# ═══════════ استارت ═══════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username, user.first_name)

    if is_admin(user.id):
        await show_admin_panel(update, context)
        return

    if not await is_user_joined(context, user.id):
        await send_join_prompt(update, context)
        return

    await update.message.reply_text(
        WELCOME_AFTER_JOIN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 تماس با پشتیبانی", callback_data="contact_admin")],
        ])
    )


# ═══════════ کال‌بک ═══════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "check_join":
        await check_join_callback(update, context)
        return

    if data == "contact_admin":
        support_text = await db.get_setting("support_text", CONTACT_ADMIN)
        await db.set_fsm(user_id, "awaiting_support")
        await query.edit_message_text(f"📩 تماس با پشتیبانی\n\n{support_text}")
        return

    if not is_admin(user_id):
        return

    if data == "admin_back":
        await query.edit_message_text(ADMIN_PANEL_TITLE, reply_markup=admin_keyboard())
        return

    if data == "admin_stats":
        users = await db.get_users_count()
        files = await db.get_all_files()
        channels = await db.get_all_channels()
        scheduled = await db.get_all_scheduled()
        text = (
            f"📊 آمار ربات\n\n"
            f"👥 کاربران: {users}\n"
            f"📁 فایل‌ها: {len(files)}\n"
            f"📢 کانال‌ها: {len(channels)}\n"
            f"⏰ زمان‌بندی‌ها: {len(scheduled)}"
        )
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    if data == "admin_settings":
        ar = await db.get_setting("auto_reply_enabled", "1")
        ap = await db.get_setting("auto_post_enabled", "1")
        ar_t = "✅ فعال" if ar == "1" else "❌ غیرفعال"
        ap_t = "✅ فعال" if ap == "1" else "❌ غیرفعال"
        kb = [
            [InlineKeyboardButton(f"💬 جواب خودکار گروه: {ar_t}", callback_data="toggle_auto_reply")],
            [InlineKeyboardButton(f"📮 پست خودکار کانال: {ap_t}", callback_data="toggle_auto_post")],
            [InlineKeyboardButton("✏️ کانال پیش‌فرض", callback_data="set_default_channel")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]
        await query.edit_message_text(
            "⚙️ تنظیمات قابلیت‌ها:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data == "toggle_auto_reply":
        cur = await db.get_setting("auto_reply_enabled", "1")
        await db.set_setting("auto_reply_enabled", "0" if cur == "1" else "1")
        ar = await db.get_setting("auto_reply_enabled", "1")
        ap = await db.get_setting("auto_post_enabled", "1")
        ar_t = "✅ فعال" if ar == "1" else "❌ غیرفعال"
        ap_t = "✅ فعال" if ap == "1" else "❌ غیرفعال"
        kb = [
            [InlineKeyboardButton(f"💬 جواب خودکار گروه: {ar_t}", callback_data="toggle_auto_reply")],
            [InlineKeyboardButton(f"📮 پست خودکار کانال: {ap_t}", callback_data="toggle_auto_post")],
            [InlineKeyboardButton("✏️ کانال پیش‌فرض", callback_data="set_default_channel")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb))
        return

    if data == "toggle_auto_post":
        cur = await db.get_setting("auto_post_enabled", "1")
        await db.set_setting("auto_post_enabled", "0" if cur == "1" else "1")
        ar = await db.get_setting("auto_reply_enabled", "1")
        ap = await db.get_setting("auto_post_enabled", "1")
        ar_t = "✅ فعال" if ar == "1" else "❌ غیرفعال"
        ap_t = "✅ فعال" if ap == "1" else "❌ غیرفعال"
        kb = [
            [InlineKeyboardButton(f"💬 جواب خودکار گروه: {ar_t}", callback_data="toggle_auto_reply")],
            [InlineKeyboardButton(f"📮 پست خودکار کانال: {ap_t}", callback_data="toggle_auto_post")],
            [InlineKeyboardButton("✏️ کانال پیش‌فرض", callback_data="set_default_channel")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb))
        return

    if data == "set_default_channel":
        await db.set_fsm(user_id, "awaiting_default_channel")
        await query.edit_message_text("آیدی کانال پیش‌فرض رو بفرست:")
        return

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

    if data == "admin_add_channel":
        await db.set_fsm(user_id, "awaiting_channel")
        await query.edit_message_text("📢 آیدی کانال رو بفرست (مثال: @mychannel):")
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

    if data == "admin_set_banner":
        await db.set_fsm(user_id, "awaiting_banner")
        await query.edit_message_text("🖼 بنر رو بفرست (عکس/ویدیو/فایل + کپشن):")
        return

    if data == "admin_broadcast":
        count = await broadcast_banner(context)
        await query.edit_message_text(
            f"✅ ارسال شد به {count} کاربر." if count else "❌ بنری تنظیم نشده.",
            reply_markup=admin_keyboard()
        )
        return

    if data == "admin_schedule":
        await query.edit_message_text(
            "⏰ نوع پست:",
            reply_markup=schedule_panel_keyboard()
        )
        return

    if data == "sch_list":
        posts = await db.get_all_scheduled()
        if not posts:
            await query.edit_message_text("📭 خالیه.", reply_markup=schedule_panel_keyboard())
            return
        text = "📋 زمان‌بندی‌ها:\n\n"
        for p in posts[:25]:
            sid, chat_id, fid, ftype, cap, run_at, sent = p
            s = "✅" if sent else "⏳"
            text += f"{s} #{sid} | {ftype} | {run_at[:16]}\n"
        await query.edit_message_text(text, reply_markup=schedule_panel_keyboard())
        return

    if data == "sch_delete":
        posts = await db.get_all_scheduled()
        if not posts:
            await query.edit_message_text("📭 خالیه.", reply_markup=schedule_panel_keyboard())
            return
        kb = [[InlineKeyboardButton(f"🗑 #{p[0]} | {p[5][:16]}", callback_data=f"schdel_{p[0]}")] for p in posts[:15]]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_schedule")])
        await query.edit_message_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("schdel_"):
        sid = int(data.split("_")[1])
        await db.delete_scheduled(sid)
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
                f"اگه می‌خوای همین باشه، بنویس: `ok`"
            )
        else:
            await query.edit_message_text(
                f"✅ نوع: {ptype}\n\n🏠 آیدی کانال مقصد:"
            )
        return


# ═══════════ هندلر پیام ═══════════
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    if not msg:
        return

    state, data = await db.get_fsm(user.id)

    # ═══════════ گروه ═══════════
    if msg.chat.type in ("group", "supergroup"):
        ar_on = await db.get_setting("auto_reply_enabled", "1")
        if ar_on == "1" and msg.text:
            try:
                reply = get_ready_reply(msg.chat_id, msg.text)
                if reply:
                    await msg.reply_text(reply)
            except Exception as e:
                logger.error(f"[AUTO-REPLY] {e}")
        return

    # ═══════════ چت خصوصی ═══════════
    if not is_admin(user.id):
        if not await is_user_joined(context, user.id):
            await send_join_prompt(update, context)
            return

    # ═══════════ FSM ادمین ═══════════
    if is_admin(user.id):

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
                await msg.reply_text(f"✅ ذخیره شد. (ID: #{fid})\nکپشن: {msg.caption or 'بدون کپشن'}")
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
            await db.add_scheduled(data["chat_id"], data["file_id"],
                                    data.get("ptype"), data.get("caption"), run_at)
            await db.clear_fsm(user.id)
            await msg.reply_text(f"✅ زمان‌بندی شد!\n📅 {run_at[:16]}")
            return

    # ═══════════ FSM کاربر ═══════════
    if state == "awaiting_support":
        try:
            text = (
                f"📩 پیام جدید\n\n"
                f"👤 {user.first_name}\n"
                f"🆔 `{user.id}`\n"
                f"📛 @{user.username or 'ندارد'}\n\n"
                f"💬 {msg.text or '(بدون متن)'}"
            )
            await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
            await msg.reply_text("✅ پیامت رسید دست ادمین.")
        except Exception:
            await msg.reply_text(ERROR)
        await db.clear_fsm(user.id)
        return

    # ═══════════ فایل معمولی ═══════════
    if msg.photo or msg.video or msg.document or msg.audio or msg.voice or msg.animation:
        await msg.reply_text(FILE_SENT)
        await send_banner(context, msg.chat_id)
        return

    await msg.reply_text(FILE_NOT_FOUND)


# ═══════════ اجرا ═══════════
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN نیست!")
        return

    # ساخت دیتابیس
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(db.init_db())
    loop.close()

    # ساخت اپ
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    print("🚀 ربات روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
