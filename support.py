from config import ADMIN_ID


async def forward_to_admin(context, user, message):
    try:
        text = (
            f"📩 پیام جدید\n\n"
            f"👤 {user.first_name}\n"
            f"🆔 `{user.id}`\n"
            f"📛 @{user.username or 'ندارد'}\n\n"
            f"💬 {message.text or '(بدون متن)'}"
        )
        await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
        if message.photo:
            await context.bot.send_photo(ADMIN_ID, message.photo[-1].file_id)
        elif message.video:
            await context.bot.send_video(ADMIN_ID, message.video.file_id)
        elif message.document:
            await context.bot.send_document(ADMIN_ID, message.document.file_id)
        return True
    except Exception:
        return False
