import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

from replies import get_ready_reply
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"سلام {user.first_name}!\nربات روشنه ✅")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    if msg.chat.type not in ("group", "supergroup"):
        return

    text = msg.text or msg.caption or ""
    if not text:
        return

    try:
        reply = get_ready_reply(msg.chat_id, text)
    except Exception as e:
        logger.error(f"[AUTO-REPLY] خطا: {e}")
        return

    if reply:
        try:
            await msg.reply_text(reply)
            logger.info(f"[AUTO-REPLY] {reply[:30]}")
        except Exception as e:
            logger.error(f"[SEND] خطا: {e}")


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
