from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID


def admin_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["📁 مدیریت ژانرها", "📚 مدیریت کتاب‌ها"],
        ["➕ افزودن کانال", "🗑 حذف کانال"],
        ["📋 مشاهده کانال‌ها"],
        ["📢 بنر فوری"],
        ["⏰ بنر زمان‌بندی", "📋 لیست بنرها"],
        ["🔗 لینک یکبار مصرف"],
        ["📩 پنل پیام‌ها"],
        ["📊 آمار ربات"],
    ], resize_keyboard=True)


def user_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["📚 کتاب‌ها", "📩 تماس با پشتیبانی"],
    ], resize_keyboard=True)


def is_admin(user_id):
    return user_id == ADMIN_ID


async def show_admin_panel(update, context):
    await update.message.reply_text(
        "🎛 پنل ادمین فعال شد\n\nاز کیبورد پایین صفحه استفاده کن 👇",
        reply_markup=admin_reply_keyboard()
    )
