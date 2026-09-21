import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

from config import BOT_TOKEN, ADMIN_ID
from gemini_chat import get_group_reply

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name}!\nربات روشنه ✅"
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # ─── فقط گروه ───
    if msg.chat.type not in ("group", "supergroup"):
        return

    text = msg.text or msg.caption or ""
    should_reply = False

    # ریپلای روی پیام ربات
    if msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id:
        should_reply = True
    # منشن
    elif text and f"@{context.bot.username}" in text:
        should_reply = True

    if not should_reply:
        return

    # پاک کردن منشن
    if f"@{context.bot.username}" in text:
        text = text.replace(f"@{context.bot.username}", "").strip()

    if not text:
        return

    await msg.chat.send_action("typing")
    reply = await get_group_reply(text, msg.chat_id)
    if reply:
        await msg.reply_text(reply)


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN نیست!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    print("🚀 ربات روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
