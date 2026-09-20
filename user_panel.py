from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from texts import BTN_SUPPORT, BTN_BOOKS
from config import BOOKS_URL


def user_keyboard():
    buttons = []
    if BOOKS_URL:
        buttons.append([InlineKeyboardButton(BTN_BOOKS, url=BOOKS_URL)])
    buttons.append([InlineKeyboardButton("💰 حمایت مالی", callback_data="donate")])
    buttons.append([InlineKeyboardButton(BTN_SUPPORT, callback_data="contact_admin")])
    return InlineKeyboardMarkup(buttons)
