from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
from texts import ADMIN_PANEL_TITLE


def admin_keyboard():
    """پنل ادمین شیشه‌ای — همه دکمه‌ها تو کیبورد"""
    return InlineKeyboardMarkup([
        # ─── فایل ───
        [InlineKeyboardButton("➕ افزودن فایل", callback_data="admin_add_file")],
        [InlineKeyboardButton("✏️ ویرایش کپشن", callback_data="admin_edit_caption")],
        [InlineKeyboardButton("🗑 حذف فایل", callback_data="admin_delete_file")],
        [InlineKeyboardButton("📋 مشاهده فایل‌ها", callback_data="admin_list_files")],

        # ─── کانال ───
        [InlineKeyboardButton("➕ افزودن کانال", callback_data="admin_add_channel")],
        [InlineKeyboardButton("🗑 حذف کانال", callback_data="admin_del_channel")],
        [InlineKeyboardButton("📋 مشاهده کانال‌ها", callback_data="admin_list_channels")],

        # ─── بنر ───
        [InlineKeyboardButton("🖼 تنظیم بنر پای فایل", callback_data="admin_set_banner")],
        [InlineKeyboardButton("📢 بنر فوری", callback_data="admin_broadcast")],

        # ─── لینک یکبار مصرف ───
        [InlineKeyboardButton("🔗 لینک یکبار مصرف", callback_data="otl_menu")],

        # ─── آمار ───
        [InlineKeyboardButton("📊 آمار ربات", callback_data="admin_stats")],
    ])


def is_admin(user_id):
    return user_id == ADMIN_ID


async def show_admin_panel(update, context):
    await update.message.reply_text(
        ADMIN_PANEL_TITLE,
        reply_markup=admin_keyboard()
    )
