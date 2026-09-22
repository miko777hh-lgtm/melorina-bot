import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN
from replies import get_ready_reply
from gemini_chat import get_group_reply


logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    level=logging.INFO,
)

logger = logging.getLogger(
    __name__
)


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(
        "ملورینا اینجاست 😌"
    )


async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message:
        return

    # فقط گروه
    if message.chat.type not in (
        "group",
        "supergroup",
    ):
        return

    # پیام خودش را نادیده بگیر
    if (
        message.from_user
        and message.from_user.id
        == context.bot.id
    ):
        return

    text = (
        message.text
        or message.caption
        or ""
    ).strip()

    if not text:
        return

    try:

        # =====================================
        # مرحله اول:
        # جواب آماده - فوری
        # =====================================

        ready_reply = get_ready_reply(
            text
        )

        if ready_reply:

            await message.reply_text(
                ready_reply
            )

            return

        # =====================================
        # مرحله دوم:
        # Gemini
        # =====================================

        await message.chat.send_action(
            action="typing"
        )

        reply = await get_group_reply(
            text,
            message.chat_id
        )

        if reply:

            await message.reply_text(
                reply
            )

    except Exception as e:

        logger.exception(
            "MESSAGE ERROR: %s",
            e
        )


def main():

    if not BOT_TOKEN:

        print(
            "❌ BOT_TOKEN تنظیم نشده!"
        )

        return

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        MessageHandler(
            filters.ALL
            & ~filters.COMMAND,
            message_handler
        )
    )

    print(
        "🚀 MELORINA روشن شد..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
