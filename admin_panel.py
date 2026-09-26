from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID


def admin_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["📁 ژانرها", "📖 رمان‌ها"],
        ["📢 کانال‌ها"],
        ["📢 بنر فوری", "⏰ بنر زمان‌بندی"],
        ["📋 لیست بنرها"],
        ["🔗 لینک یکبار مصرف"],
        ["📩 پنل پیام‌ها"],
        ["📊 آمار ربات"],
    ], resize_keyboard=True)


def user_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["📖 رمان‌ها", "📩 تماس با پشتیبانی"],
    ], resize_keyboard=True)


def is_admin(user_id):
    return user_id == ADMIN_ID


async def show_admin_panel(update, context):
    await update.message.reply_text(
        "🎛 پنل ادمین\n\nاز کیبورد پایین صفحه استفاده کن 👇",
        reply_markup=admin_reply_keyboard()
         )
