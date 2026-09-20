import database as db


async def find_reply(text):
    if not text:
        return None
    text_lower = text.lower().strip()
    replies = await db.get_all_auto_replies()
    for rid, keyword, reply, exact in replies:
        kw = keyword.lower().strip()
        if exact == 1:
            if text_lower == kw:
                return reply
        else:
            if kw in text_lower:
                return reply
    return None
