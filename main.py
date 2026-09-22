from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN
from replies import get_ready_reply


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    chat = update.effective_chat

    if not chat:
        return

    # فقط گروه و سوپرگروه
    if chat.type not in {
        "group",
        "supergroup",
    }:
        return

    # پیام خود ربات
    if (
        message.from_user
        and message.from_user.is_bot
    ):
        return

    text = message.text or ""

    if not text.strip():
        return

    chat_id = chat.id

    answer = get_ready_reply(
        chat_id,
        text
    )

    # اگر برای پیام جواب آماده نداریم،
    # هیچ جوابی نده.
    if answer is None:
        return

    try:
        await message.reply_text(
            answer,
            do_quote=True
        )

    except Exception as error:
        print(
            f"[TELEGRAM ERROR] {type(error).__name__}: {error}"
        )


def main():

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print(
        "Melorina is running..."
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
