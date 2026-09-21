import random
import json
import database as db


async def find_multi_reply(text):
    """جستجوی جواب تو دیتابیس چندجوابی"""
    if not text:
        return None
    text_lower = text.lower().strip()

    mrs = await db.get_all_multi_replies()
    for mid, keyword, replies_json, exact in mrs:
        kw = keyword.lower().strip()
        match = False
        if exact == 1:
            match = (text_lower == kw)
        else:
            match = (kw in text_lower)

        if match:
            try:
                replies = json.loads(replies_json)
                if replies:
                    return random.choice(replies)
            except Exception:
                pass

    return None
