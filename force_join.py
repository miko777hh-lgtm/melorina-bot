from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.error import TelegramError
from texts import START_BEFORE_JOIN, BTN_JOINED, NOT_JOINED, BTN_CHECK
import database as db


async def is_user_joined(context, user_id):
    channels = await db.get_all_channels()
    if not channels:
        return True
    for ch_id, chat_id, title, invite in channels:
        try:
            member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in (ChatMember.LEFT, ChatMember.BANNED):
                return False
        except TelegramError:
            return False
    return True


async def send_join_prompt(update, context):
    channels = await db.get_all_channels()
    keyboard = []
    for ch_id, chat_id, title, invite in channels:
        url = invite if invite else f"https://t.me/{chat_id.lstrip('@')}"
        # اگه اسم کانال خالی بود → «عضویت»
        name = title.strip() if title and title.strip() else "عضویت"
        keyboard.append([InlineKeyboardButton(f"📢 {name}", url=url)])
    keyboard.append([InlineKeyboardButton(BTN_JOINED, callback_data="check_join")])
    await update.message.reply_text(
        START_BEFORE_JOIN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def check_join_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if await is_user_joined(context, user_id):
        await query.edit_message_text(
            "بالاخره پیدات شد.\nحالا می‌تونی فایل موردنظرت رو بگیری."
        )
        return True
    keyboard = [[InlineKeyboardButton(BTN_CHECK, callback_data="check_join")]]
    await query.edit_message_text(NOT_JOINED, reply_markup=InlineKeyboardMarkup(keyboard))
    return False
