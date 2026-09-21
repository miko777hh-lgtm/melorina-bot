import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

from config import BOT_TOKEN, ADMIN_ID

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name}!\n"
        f"ربات روشنه ✅"
    )


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN نیست!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    print("🚀 ربات روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
