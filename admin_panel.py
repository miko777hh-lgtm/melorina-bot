from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID


def admin_reply_keyboard():
    """کیبورد پایین صفحه — برای ادمین"""
    return ReplyKeyboardMarkup([
        ["➕ افزودن فایل", "✏️ ویرایش کپشن"],
        ["🗑 حذف فایل", "📋 مشاهده فایل‌ها"],
        ["➕ افزودن کانال", "🗑 حذف کانال"],
        ["📋 مشاهده کانال‌ها"],
        ["🖼 تنظیم بنر", "📢 بنر فوری"],
        ["🔗 لینک یکبار مصرف"],
        ["⚙️ ویرایش متن پشتیبانی"],
        ["📊 آمار ربات"],
    ], resize_keyboard=True)


def user_reply_keyboard():
    """کیبورد پایین صفحه — برای کاربر عادی"""
    return ReplyKeyboardMarkup([
        ["📩 تماس با پشتیبانی"],
    ], resize_keyboard=True)


def is_admin(user_id):
    return user_id == ADMIN_ID


async def show_admin_panel(update, context):
    await update.message.reply_text(
        "🎛 پنل ادمین فعال شد\n\n"
        "از کیبورد پایین صفحه استفاده کن 👇",
        reply_markup=admin_reply_keyboard()
    )
