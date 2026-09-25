import asyncio
import json
import database as db


def capture_message(msg):
    """ذخیره هر نوع پیام — پشتیبانی از همه چیز"""
    data = {
        "type": "text",
        "text": None,
        "entities": None,
        "file_id": None,
        "caption": None,
        "caption_entities": None,
    }

    if msg.text:
        data["type"] = "text"
        data["text"] = msg.text
        if msg.entities:
            data["entities"] = [e.to_dict() for e in msg.entities]
    elif msg.photo:
        data["type"] = "photo"
        data["file_id"] = msg.photo[-1].file_id
        data["caption"] = msg.caption
        if msg.caption_entities:
            data["caption_entities"] = [e.to_dict() for e in msg.caption_entities]
    elif msg.video:
        data["type"] = "video"
        data["file_id"] = msg.video.file_id
        data["caption"] = msg.caption
        if msg.caption_entities:
            data["caption_entities"] = [e.to_dict() for e in msg.caption_entities]
    elif msg.animation:
        data["type"] = "animation"
        data["file_id"] = msg.animation.file_id
        data["caption"] = msg.caption
        if msg.caption_entities:
            data["caption_entities"] = [e.to_dict() for e in msg.caption_entities]
    elif msg.document:
        data["type"] = "document"
        data["file_id"] = msg.document.file_id
        data["caption"] = msg.caption
        if msg.caption_entities:
            data["caption_entities"] = [e.to_dict() for e in msg.caption_entities]
    elif msg.audio:
        data["type"] = "audio"
        data["file_id"] = msg.audio.file_id
        data["caption"] = msg.caption
        if msg.caption_entities:
            data["caption_entities"] = [e.to_dict() for e in msg.caption_entities]
    elif msg.voice:
        data["type"] = "voice"
        data["file_id"] = msg.voice.file_id
        data["caption"] = msg.caption
        if msg.caption_entities:
            data["caption_entities"] = [e.to_dict() for e in msg.caption_entities]
    elif msg.sticker:
        data["type"] = "sticker"
        data["file_id"] = msg.sticker.file_id

    return json.dumps(data, ensure_ascii=False)


async def send_captured(context, chat_id, message_json):
    """ارسال پیام ذخیره شده — پشتیبانی از متن + لینک + نقل قول"""
    try:
        data = json.loads(message_json) if isinstance(message_json, str) else message_json
    except Exception:
        return

    t = data.get("type")
    file_id = data.get("file_id")
    caption = data.get("caption")
    text = data.get("text")

    try:
        if t == "text":
            await context.bot.send_message(
                chat_id, text,
                entities=data.get("entities"),
                disable_web_page_preview=False
            )
        elif t == "photo":
            await context.bot.send_photo(
                chat_id, file_id, caption=caption,
                caption_entities=data.get("caption_entities")
            )
        elif t == "video":
            await context.bot.send_video(
                chat_id, file_id, caption=caption,
                caption_entities=data.get("caption_entities")
            )
        elif t == "animation":
            await context.bot.send_animation(
                chat_id, file_id, caption=caption,
                caption_entities=data.get("caption_entities")
            )
        elif t == "document":
            await context.bot.send_document(
                chat_id, file_id, caption=caption,
                caption_entities=data.get("caption_entities")
            )
        elif t == "audio":
            await context.bot.send_audio(
                chat_id, file_id, caption=caption,
                caption_entities=data.get("caption_entities")
            )
        elif t == "voice":
            await context.bot.send_voice(
                chat_id, file_id, caption=caption,
                caption_entities=data.get("caption_entities")
            )
        elif t == "sticker":
            await context.bot.send_sticker(chat_id, file_id)
    except Exception as e:
        print(f"[BANNER SEND] {e}")


async def send_file_banner(context, chat_id):
    """ارسال بنر پای فایل"""
    banner = await db.get_file_banner()
    if not banner:
        return
    await send_captured(context, chat_id, banner)


async def broadcast_instant_banner(context):
    """ارسال بنر فوری به همه کاربران"""
    banner = await db.get_instant_banner()
    if not banner:
        return 0
    users = await db.get_all_users()
    count = 0
    for uid in users:
        try:
            await send_captured(context, uid, banner)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            continue
    return count


async def broadcast_scheduled_banner(context, message_json):
    """ارسال بنر زمان‌بندی به همه کاربران"""
    users = await db.get_all_users()
    count = 0
    for uid in users:
        try:
            await send_captured(context, uid, message_json)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            continue
    return count
