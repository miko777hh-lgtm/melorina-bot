from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def settings_keyboard(auto_post, auto_reply, referral):
    def st(v):
        return "✅ فعال" if v == "1" else "❌ غیرفعال"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📮 پست خودکار کانال: {st(auto_post)}",
            callback_data="toggle_auto_post"
        )],
        [InlineKeyboardButton(
            f"💬 جواب خودکار گروه: {st(auto_reply)}",
            callback_data="toggle_auto_reply"
        )],
        [InlineKeyboardButton(
            f"🎁 دعوت: {st(referral)}",
            callback_data="toggle_referral"
        )],
        [InlineKeyboardButton("✏️ کانال پیش‌فرض", callback_data="set_default_channel")],
        [InlineKeyboardButton("✏️ تعداد دعوت", callback_data="set_ref_count")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
    ])
