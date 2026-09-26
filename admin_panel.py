from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID


def admin_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["📁 ژانرها", "📖 رمان‌ها"],
        ["📚 کتاب‌ها", "📢 کانال‌ها"],
        ["🌐 فیلترشکن", "🎛 دکمه‌های سفارشی"],
        ["⚙️ تنظیمات", "👥 کاربران غیرفعال"],
        ["📢 بنر فوری", "⏰ بنر زمان‌بندی"],
        ["📋 لیست بنرها", "🔗 لینک یکبار مصرف"],
        ["📩 پنل پیام‌ها", "⭐ امتیازها"],
        ["📊 آمار ربات"],
    ], resize_keyboard=True)


def user_reply_keyboard():
    return ReplyKeyboardMarkup([
        ["📚 کتاب‌ها", "📖 رمان‌ها"],
        ["🌐 فیلترشکن", "🔍 جستجو"],
        ["⭐ امتیاز به ربات", "📩 تماس با پشتیبانی"],
    ], resize_keyboard=True)


def is_admin(user_id):
    return user_id == ADMIN_ID


async def show_admin_panel(update, context):
    await update.message.reply_text(
        "🎛 پنل ادمین\n\nاز کیبورد پایین استفاده کن 👇",
        reply_markup=admin_reply_keyboard()
    )
