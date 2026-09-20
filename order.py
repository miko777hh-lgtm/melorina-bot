from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
from texts import ORDER_ADMIN_NEW
import database as db


async def notify_admin_new_order(context, user, book_name):
    """اطلاع دادن سفارش جدید به ادمین"""
    oid = await db.add_book_order(
        user.id, user.username, user.first_name, book_name
    )

    text = ORDER_ADMIN_NEW.format(
        name=user.first_name,
        uid=user.id,
        username=user.username or "ندارد",
        book=book_name,
        price="در انتظار تعیین"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"💵 ارسال قیمت به #{oid}",
            callback_data=f"order_price_{oid}"
        )],
        [InlineKeyboardButton(
            f"👁 جزئیات سفارش #{oid}",
            callback_data=f"order_view_{oid}"
        )],
    ])

    try:
        await context.bot.send_message(
            ADMIN_ID, text,
            parse_mode="Markdown",
            reply_markup=kb
        )
        return oid
    except Exception as e:
        print(f"[ORDER] notify error: {e}")
        return None
