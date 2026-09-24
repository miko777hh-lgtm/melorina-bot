import secrets
import string
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import database as db

TZ = ZoneInfo("Asia/Tehran")


def generate_code(length=10):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def create_onetime_link(file_id_db, hours=24):
    code = generate_code()
    if hours > 0:
        expires = (datetime.now(TZ) + timedelta(hours=hours)).isoformat()
    else:
        expires = None
    await db.add_onetime_link(code, file_id_db, expires)
    return code


async def use_onetime_link(code):
    row = await db.get_onetime_link(code)
    if not row:
        return {"ok": False, "reason": "not_found"}

    link_id, file_id_db, used, expires_at = row

    if used == 1:
        return {"ok": False, "reason": "used"}

    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=TZ)
            if datetime.now(TZ) > exp:
                return {"ok": False, "reason": "expired"}
        except Exception:
            pass

    await db.mark_onetime_used(code)
    return {"ok": True, "file_id_db": file_id_db}


async def generate_bot_link(bot_username, code):
    return f"https://t.me/{bot_username}?start=otl_{code}"
