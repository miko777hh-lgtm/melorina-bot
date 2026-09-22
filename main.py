from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN
from replies import get_ready_reply
from gemini_chat import ask_gemini


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    # فقط گروه و سوپرگروه
    if update.effective_chat.type not in {
        "group",
        "supergroup",
    }:
        return

    # پیام خود ربات نادیده گرفته شود
    if message.from_user and message.from_user.is_bot:
        return

    text = message.text or message.caption or ""

    text = text.strip()

    if not text:
        return

    chat_id = update.effective_chat.id

    # -----------------------------------------------------
    # 1. اول فقط پیام‌های خیلی رایج
    # -----------------------------------------------------

    ready = get_ready_reply(
        chat_id,
        text
    )

    if ready:
        await message.reply_text(
            ready,
            do_quote=True
        )
        return

    # -----------------------------------------------------
    # 2. بقیه مستقیماً Gemini
    # -----------------------------------------------------

    answer = await ask_gemini(
        chat_id,
        text
    )

    if answer:
        await message.reply_text(
            answer,
            do_quote=True
        )
        return

    # -----------------------------------------------------
    # 3. Gemini موقتاً از دسترس خارج شد
    # اینجا ربات خودش جواب می‌دهد.
    # اما فقط یک جواب آماده مرتبط.
    # -----------------------------------------------------

    fallback = get_ready_reply(
        chat_id,
        text
    )

    if fallback:
        await message.reply_text(
            fallback,
            do_quote=True
        )
        return

    # اگر برای این پیام جواب آماده‌ای نداریم،
    # بهتر است اصلاً پیام مصنوعی و تکراری نفرستیم.
    # دفعه بعد که Gemini برگشت، پاسخ می‌دهد.


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        MessageHandler(
            (
                filters.TEXT
                | filters.CaptionRegex(".+")
            )
            & ~filters.COMMAND,
            handle_message
        )
    )

    print("Melorina is running...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
