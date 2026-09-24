import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

import database as db
from config import BOT_TOKEN, ADMIN_ID
from replies import get_ready_reply
from force_join import is_user_joined, send_join_prompt, check_join_callback
from admin_panel import admin_keyboard, is_admin, show_admin_panel

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


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
        f"بالاخره پیدات شد، {user.first_name}.\nحالا هر چی می‌خوای بپرس."
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

    if not is_admin(user_id):
        return

    # ═══════════ پنل ادمین ═══════════
    if data == "admin_back":
        await query.edit_message_text(
            "🎛 پنل ادمین\n\nهمه گزینه‌ها در دسترسه:",
            reply_markup=admin_keyboard()
        )
        return

    if data == "admin_stats":
        users = await db.get_users_count()
        channels = await db.get_all_channels()
        text = (
            f"📊 آمار ربات\n\n"
            f"👥 کاربران: {users}\n"
            f"📢 کانال‌ها: {len(channels)}"
        )
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return

    # ─── کانال: افزودن ───
    if data == "admin_add_channel":
        await db.set_fsm(user_id, "awaiting_channel")
        await query.edit_message_text(
            "📢 آیدی کانال رو بفرست:\n\n"
            "مثال: `@mychannel` یا `-1001234567890`"
        )
        return

    # ─── کانال: حذف ───
    if data == "admin_del_channel":
        channels = await db.get_all_channels()
        if not channels:
            await query.edit_message_text("📭 کانالی نیست.", reply_markup=admin_keyboard())
            return
        kb = []
        for c in channels:
            kb.append([InlineKeyboardButton(f"🗑 {c[2]}", callback_data=f"delch_{c[0]}")])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
        await query.edit_message_text("کدوم حذف بشه؟", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("delch_"):
        cid = int(data.split("_")[1])
        await db.delete_channel(cid)
        await query.edit_message_text("✅ حذف شد.", reply_markup=admin_keyboard())
        return

    # ─── کانال: لیست ───
    if data == "admin_list_channels":
        channels = await db.get_all_channels()
        if not channels:
            await query.edit_message_text("📭 کانالی نیست.", reply_markup=admin_keyboard())
            return
        text = "📋 کانال‌ها:\n\n" + "\n".join(f"• {c[2]} — `{c[1]}`" for c in channels)
        await query.edit_message_text(text, reply_markup=admin_keyboard())
        return


# ═══════════ هندلر پیام ═══════════
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    if not msg:
        return

    state, data = await db.get_fsm(user.id)

    # ═══════════ گروه: جواب آماده ═══════════
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
    # اگه ادمین نیست → چک عضویت
    if not is_admin(user.id):
        if not await is_user_joined(context, user.id):
            await send_join_prompt(update, context)
            return

    # ═══════════ FSM ادمین: افزودن کانال ═══════════
    if is_admin(user.id) and state == "awaiting_channel":
        try:
            chat = await context.bot.get_chat(msg.text.strip())
            invite = f"https://t.me/{chat.username}" if chat.username else chat.invite_link
            await db.add_channel(str(chat.id), chat.title, invite)
            await msg.reply_text(f"✅ کانال اضافه شد:\n{chat.title}")
        except Exception as e:
            await msg.reply_text(f"❌ خطا: {e}")
        await db.clear_fsm(user.id)
        return


# ═══════════ Post Init ═══════════
async def post_init(app):
    # ساخت دیتابیس
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
