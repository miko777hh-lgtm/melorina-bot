import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
from banner import send_banner, broadcast_banner
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

    # ─── استارت معمولی ───
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

    # ═══════════ FSM ادمین: جواب به پشتیبانی ═══════════
    if is_admin(user.id) and state == "awaiting_reply_text":
        target = data.get("target")
        msg_id = data.get("msg_id")
        if target and msg.text:
            try:
                await context.bot.send_message(
                    target,
                    f"📩 پاسخ پشتیبانی:\n\n{msg.text}"
                )
                await msg.reply_text("✅ جواب فرستاده شد.")
                if msg_id:
                    await db.mark_support_seen(msg_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطا: {e}")
        await db.clear_fsm(user.id)
        return

    # ═══════════ کاربر: تماس با پشتیبانی ═══════════
    if msg.text == "📩 تماس با پشتیبانی":
        await db.set_fsm(user.id, "awaiting_support")
        await msg.reply_text(
            "📩 تماس با پشتیبانی\n\n"
            "پیامت رو بنویس و بفرست.\n"
            "مستقیم می‌رسه به ادمین 👇"
        )
        return

    if state == "awaiting_support":
        if msg.text:
            await db.add_support_msg(
                user.id, user.username, user.first_name, msg.text
            )
        try:
            await msg.forward(ADMIN_ID)
        except Exception:
            pass
        await msg.reply_text("✅ پیامت رسید به ادمین.\nبه‌زودی جواب می‌گیری.")
        await db.clear_fsm(user.id)
        return

    # ═══════════ FSM ادمین ═══════════
    if is_admin(user.id):

        # ─── جواب به پیام پشتیبانی ───
        if msg.text and msg.text.startswith("reply_"):
            try:
                msg_id = int(msg.text.replace("reply_", "").strip())
            except Exception:
                await msg.reply_text("❌ فرمت اشتباه. مثال: `reply_5`")
                return
            s_msg = await db.get_support_msg(msg_id)
            if not s_msg:
                await msg.reply_text("❌ پیام پیدا نشد.")
                return
            sid, uid, fname, txt = s_msg
            await db.set_fsm(user.id, "awaiting_reply_text", {"target": uid, "msg_id": msg_id})
            await msg.reply_text(
                f"✏️ جوابت به {fname} رو بنویس:\n\n"
                f"💬 پیامش: {txt[:50]}"
            )
            return

        # ─── پنل پیام‌ها ───
        if msg.text == "📩 پنل پیام‌ها":
            msgs = await db.get_all_support_msgs(30)
            if not msgs:
                await msg.reply_text("📭 پیامی نیست.")
                return
            text = f"📩 پیام‌های پشتیبانی ({len(msgs)})\n\n"
            for m in msgs[:15]:
                mid, uid, fname, txt, seen, created = m
                status = "✅" if seen else "🆕"
                text += f"{status} #{mid} | {fname}\n💬 {txt[:50]}\n\n"
            text += "برای جواب دادن، بنویس:\n`reply_شماره`\n\nمثال: `reply_5`"
            await msg.reply_text(text)
            return

        # ─── دکمه‌های کیبورد ادمین ───
        if msg.text == "➕ افزودن فایل":
            await db.set_fsm(user.id, "awaiting_file")
            await msg.reply_text("📎 فایل رو با کپشن بفرست:")
            return

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

        if msg.text == "🗑 حذف فایل":
            files = await db.get_all_files()
            if not files:
                await msg.reply_text("📭 فایلی نیست.")
                return
            kb = []
            for f in files[:20]:
                t = f[3][:25] if f[3] else "بدون کپشن"
                kb.append([InlineKeyboardButton(f"🗑 #{f[0]} — {t}", callback_data=f"delfile_{f[0]}")])
            await msg.reply_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
            return

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

        if msg.text == "➕ افزودن کانال":
            await db.set_fsm(user.id, "awaiting_channel")
            await msg.reply_text("📢 آیدی کانال رو بفرست:\nمثال: @mychannel")
            return

        if msg.text == "🗑 حذف کانال":
            channels = await db.get_all_channels()
            if not channels:
                await msg.reply_text("📭 کانالی نیست.")
                return
            kb = [[InlineKeyboardButton(f"🗑 {c[2]}", callback_data=f"delch_{c[0]}")] for c in channels]
            await msg.reply_text("کدوم؟", reply_markup=InlineKeyboardMarkup(kb))
            return

        if msg.text == "📋 مشاهده کانال‌ها":
            channels = await db.get_all_channels()
            if not channels:
                await msg.reply_text("📭 کانالی نیست.")
                return
            text = "📋 کانال‌ها:\n\n" + "\n".join(f"• {c[2]} — `{c[1]}`" for c in channels)
            await msg.reply_text(text)
            return

        if msg.text == "🖼 تنظیم بنر":
            await db.set_fsm(user.id, "awaiting_banner")
            await msg.reply_text("🖼 بنر رو بفرست (عکس/ویدیو/فایل + کپشن):")
            return

        if msg.text == "📢 بنر فوری":
            count = await broadcast_banner(context)
            await msg.reply_text(
                f"✅ ارسال شد به {count} کاربر." if count else "❌ بنری تنظیم نشده."
            )
            return

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

        if msg.text == "📊 آمار ربات":
            users = await db.get_users_count()
            files = await db.get_all_files()
            channels = await db.get_all_channels()
            links = await db.get_all_onetime_links()
            support_count = await db.get_support_count()
            text = (
                f"📊 آمار ربات\n\n"
                f"👥 کاربران: {users}\n"
                f"📁 فایل‌ها: {len(files)}\n"
                f"📢 کانال‌ها: {len(channels)}\n"
                f"🔗 لینک‌های یکبار مصرف: {len(links)}\n"
                f"📩 پیام‌ها: {support_count}"
            )
            await msg.reply_text(text)
            return

        # ─── FSM: افزودن فایل ───
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

        # ─── FSM: ویرایش کپشن ───
        if state == "awaiting_new_caption":
            await db.update_caption(data.get("file_id"), msg.text or "")
            await msg.reply_text("✅ آپدیت شد.")
            await db.clear_fsm(user.id)
            return

        # ─── FSM: افزودن کانال ───
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

        # ─── FSM: تنظیم بنر ───
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

        # ─── FSM: لینک یکبار مصرف ───
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

    print("🚀 ربات روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
