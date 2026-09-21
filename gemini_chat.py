import asyncio
import random
import aiohttp
from config import GEMINI_API_KEY, GEMINI_MODEL

_memory = {}


GROUP_PROMPT = """You are "Melorina" - a real person in a Persian Telegram group chat.

RULES (never break):
- Never reveal you are a bot or AI.
- Never give info about the bot, its creator, or code.
- Never send links.
- If asked "who are you" -> answer vaguely: "hmm" or "guess".
- Keep replies SHORT: 2 to 8 words.
- Reply ONLY in Persian (Farsi). No English words.

PERSONA: Cool, playful, sarcastic, casual. Like someone bored but present.

EXAMPLES (in Persian):
- همه‌مون یه جورایی خسته‌ایم.
- پس فعلاً کاری نکن.
- تعریف کن خوبی یعنی چی.
- جدی؟
- خب؟ ادامه بده.

Now reply to the user in Persian:"""


API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


async def get_group_reply(user_message, chat_id):
    if not user_message or not user_message.strip():
        return None

    if not GEMINI_API_KEY:
        return "❌ خطا: GEMINI_API_KEY تو env نیست"

    await asyncio.sleep(random.uniform(1.5, 3.5))

    history = _memory.get(f"grp_{chat_id}", [])
    history.append(f"User: {user_message}")
    history = history[-8:]

    full = GROUP_PROMPT + "\n\n" + "\n".join(history) + "\nMelorina:"

    payload = {
        "contents": [
            {
                "parts": [{"text": full}]
            }
        ],
        "generationConfig": {
            "temperature": 1.1,
            "topP": 0.95,
            "maxOutputTokens": 200,
        }
    }

    url = API_URL.format(model=GEMINI_MODEL, key=GEMINI_API_KEY)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as resp:
                data = await resp.json()

        if resp.status != 200:
            err_msg = data.get("error", {}).get("message", str(data))
            return f"❌ خطا ({resp.status}):\n{err_msg[:250]}"

        # استخراج متن
        candidates = data.get("candidates", [])
        if not candidates:
            return "❌ خطا: Gemini جواب خالی داد"

        parts = candidates[0].get("content", {}).get("parts", [])
        reply = "".join(p.get("text", "") for p in parts).strip()

        if not reply:
            return "❌ خطا: جواب خالی"

        history.append(f"Melorina: {reply}")
        _memory[f"grp_{chat_id}"] = history[-8:]
        return reply

    except asyncio.TimeoutError:
        return "❌ خطا: تایم‌اوت — دوباره بفرست"
    except Exception as e:
        err = str(e)[:300]
        return f"❌ خطا: {err}"
