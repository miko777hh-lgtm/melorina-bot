import asyncio
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

import database as db
from config import BOT_TOKEN, ADMIN_ID
from texts import *
from replies import get_ready_reply
from force_join import is_user_joined, send_join_prompt, check_join_callback
from admin_panel import (
    admin_reply_keyboard, user_reply_keyboard,
    is_admin, show_admin_panel
)
from banner import send_banner, broadcast_banner, capture_banner
from onetime_link import create_onetime_link, use_onetime_link, generate_bot_link

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ═══════════ استارت ═══════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username, user.first_name)

    args = context.args

    # لینک یکبار مصرف
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

    # استارت معمولی
    if is_admin(user.id):
        await show_admin_panel(update, context)
        return

    if not await is_user_joined(context, user.id):
        await send_join_prompt(update, context)
        return

    await update.message.reply_text(
        WELCOME_AFTER_JOIN,
        reply_markup=user_reply_keyboard()
    )


# ═══════════ ارسال فایل ═══════════
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


# ═══════════ کال‌بک ═══════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "check_join":
        await check_join_callback(update, context)
        return

    if not is_admin(user_id):
        return

    if data.startswith("delfile_"):
        fid = int(data.split("_")[1])
        await db.delete_file(fid)
        await query.edit_message_text("✅ حذف شد.")
        return

    if data.startswith("editcap_"):
        fid = int(data.split("_")[1])
        await db.set_fsm(user_id, "awaiting_new_caption", {"file_id": fid})
        await query.edit_message_text("کپشن جدید رو بفرست:")
        return

    if data.startswith("delch_"):
        cid = int(data.split("_")[1])
        await db.delete_channel(cid)
        await query.edit_message_text("✅ حذف شد.")
        return

    if data == "otl_new":
        files = await db.get_all_files()
        if not files:
            await query.edit_message_text("📭 فایلی نیست.")
            return
        kb = []
        for f in files[:20]:
            t = f[3][:25] if f[3] else "بدون کپشن"
            kb.append([InlineKeyboardButton(f"#{f[0]} — {t}", callback_data=f"otl_file_{f[0]}")])
        await query.edit_message_text("کدوم فایل؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("otl_file_"):
        fid = int(data.split("_")[2])
        await db.set_fsm(user_id, "otl_step1", {"file_id_db": fid})
        await query.edit_message_text(
            "⏰ مدت اعتبار (ساعت):\n"
            "مثال: `24` = ۲۴ ساعت\n"
            "`0` = بدون انقضا"
        )
        return

    if data == "otl_list":
        links = await db.get_all_onetime_links()
        if not links:
            await query.edit_message_text("📭 لینکی نیست.")
            return
        text = "🔗 لینک‌ها:\n\n"
        for l in links[:20]:
            lid, code, fid, used, exp, created = l
            s = "✅ استفاده شده" if used else "🟢 فعال"
            text += f"#{lid} | `{code}` | فایل #{fid} | {s}\n"
        await query.edit_message_text(text)
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
        if msg.text:
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

    # ═══════════ کاربر: تماس با پشتیبانی ═══════════
    if msg.text == BTN_SUPPORT:
        await db.set_fsm(user.id, "awaiting_support")
        support_text = await db.get_setting("support_text", CONTACT_ADMIN)
        await msg.reply_text(f"📩 تماس با پشتیبانی\n\n{support_text}")
        return

    # ═══════════ FSM کاربر: پیام به ادمین ═══════════
    if state == "awaiting_support":
        try:
            await msg.forward(ADMIN_ID)
            await msg.reply_text("✅ پیامت رسید دست ادمین.")
        except Exception:
            await msg.reply_text(ERROR)
        await db.clear_fsm(user.id)
        return

    # ═══════════ FSM ادمین ═══════════
    if is_admin(user.id):

        # ─── افزودن فایل ───
        if msg.text == "➕ افزودن فایل":
            await db.set_fsm(user.id, "awaiting_file")
            await msg.reply_text("📎 فایل رو با کپشن بفرست:")
            return

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
                    f"✅ ذخیره شد. (#{fid})\nکپشن: {msg.caption or 'بدون کپشن'}"
                )
            else:
                await msg.reply_text("❌ فایلی نبود.")
            await db.clear_fsm(user.id)
            return

        # ─── ویرایش کپشن ───
        if msg.text == "✏️ ویرایش کپشن":
            files = await db.get_all_files()
            if not files:
                await msg.reply_text("📭 فایلی نیست.")
                return
            kb = []
            for f in files[:20]:
                t = f[3][:25] if f[3] else "بدون کپشن"
                kb.append([InlineKeyboardButton(f"#{f[0]} — {t}", callback_data=f"editcap_{f[0]}")])
            await msg.reply_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
            return

        if state == "awaiting_new_caption":
            await db.update_caption(data.get("file_id"), msg.text or "")
            await msg.reply_text("✅ آپدیت شد.")
            await db.clear_fsm(user.id)
            return

        # ─── حذف فایل ───
        if msg.text == "🗑 حذف فایل":
            files = await db.get_all_files()
            if not files:
                await msg.reply_text("📭 فایلی نیست.")
                return
            kb = []
            for f in files[:20]:
                t = f[3][:25] if f[3] else "بدون کپشن"
                kb.append([InlineKeyboardButton(f"🗑 #{f[0]} — {t}", callback_data=f"delfile_{f[0]}")])
            await msg.reply_text("کدوم حذف بشه؟", reply_markup=InlineKeyboardMarkup(kb))
            return

        # ─── مشاهده فایل‌ها ───
        if msg.text == "📋 مشاهده فایل‌ها":
            files = await db.get_all_files()
            if not files:
                await msg.reply_text("📭 فایلی نیست.")
                return
            text = "📋 فایل‌ها:\n\n"
            for f in files[:30]:
                t = f[3][:30] if f[3] else "بدون کپشن"
                text += f"#{f[0]} | {f[2]} | {t}\n"
            await msg.reply_text(text)
            return

        # ─── افزودن کانال ───
        if msg.text == "➕ افزودن کانال":
            await db.set_fsm(user.id, "awaiting_channel")
            await msg.reply_text("📢 آیدی کانال رو بفرست:\nمثال: @mychannel")
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

        # ─── حذف کانال ───
        if msg.text == "🗑 حذف کانال":
            channels = await db.get_all_channels()
            if not channels:
                await msg.reply_text("📭 کانالی نیست.")
                return
            kb = [[InlineKeyboardButton(f"🗑 {c[2]}", callback_data=f"delch_{c[0]}")] for c in channels]
            await msg.reply_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
            return

        # ─── مشاهده کانال‌ها ───
        if msg.text == "📋 مشاهده کانال‌ها":
            channels = await db.get_all_channels()
            if not channels:
                await msg.reply_text("📭 کانالی نیست.")
                return
            text = "📋 کانال‌ها:\n\n" + "\n".join(f"• {c[2]} — `{c[1]}`" for c in channels)
            await msg.reply_text(text)
            return

        # ─── تنظیم بنر ───
        if msg.text == "🖼 تنظیم بنر":
            await db.set_fsm(user.id, "awaiting_banner")
            await msg.reply_text(
                "🖼 بنر رو بفرست.\n\n"
                "می‌تونه هر چیزی باشه:\n"
                "• عکس / ویدیو / فایل / گیف / ویس\n"
                "• متن (حتی با لینک)\n"
                "• فوروارد\n"
                "• نقل قول\n\n"
                "همه چی پشتیبانی میشه ✅"
            )
            return

        if state == "awaiting_banner":
            json_data = capture_banner(msg)
            await db.set_banner(json_data)
            await msg.reply_text("✅ بنر تنظیم شد.")
            await db.clear_fsm(user.id)
            return

        # ─── بنر فوری ───
        if msg.text == "📢 بنر فوری":
            count = await broadcast_banner(context)
            if count == 0:
                await msg.reply_text("❌ بنری تنظیم نشده.")
            else:
                await msg.reply_text(f"✅ ارسال شد به {count} کاربر.")
            return

        # ─── لینک یکبار مصرف ───
        if msg.text == "🔗 لینک یکبار مصرف":
            links = await db.get_all_onetime_links()
            kb = [
                [InlineKeyboardButton("➕ ساخت لینک جدید", callback_data="otl_new")],
                [InlineKeyboardButton("📋 لیست لینک‌ها", callback_data="otl_list")],
            ]
            await msg.reply_text(
                f"🔗 لینک‌های یکبار مصرف\n\nتعداد: {len(links)}",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

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

        # ─── ویرایش متن پشتیبانی ───
        if msg.text == "⚙️ ویرایش متن پشتیبانی":
            await db.set_fsm(user.id, "awaiting_support_text")
            await msg.reply_text("✏️ متن جدید پشتیبانی رو بفرست:")
            return

        if state == "awaiting_support_text":
            await db.set_setting("support_text", msg.text or "")
            await msg.reply_text("✅ متن پشتیبانی آپدیت شد.")
            await db.clear_fsm(user.id)
            return

        # ─── آمار ───
        if msg.text == "📊 آمار ربات":
            users = await db.get_users_count()
            files = await db.get_all_files()
            channels = await db.get_all_channels()
            links = await db.get_all_onetime_links()
            text = (
                f"📊 آمار ربات\n\n"
                f"👥 کاربران: {users}\n"
                f"📁 فایل‌ها: {len(files)}\n"
                f"📢 کانال‌ها: {len(channels)}\n"
                f"🔗 لینک‌های یکبار مصرف: {len(links)}"
            )
            await msg.reply_text(text)
            return

    # ═══════════ فایل معمولی ═══════════
    if msg.photo or msg.video or msg.document or msg.audio or msg.voice or msg.animation:
        await msg.reply_text(FILE_SENT)
        await send_banner(context, msg.chat_id)
        return

    await msg.reply_text(FILE_NOT_FOUND)


# ═══════════ Post Init ═══════════
async def post_init(app):
    await db.init_db()


# ═══════════ اجرا ═══════════
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN نیست!")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    print("🚀 ربات روشن شد!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
