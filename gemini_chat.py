import asyncio
import random
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL

_client = None
if GEMINI_API_KEY:
    try:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"[GEMINI] init: {e}")


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


async def get_group_reply(user_message, chat_id):
    if not user_message or not user_message.strip():
        return None

    if not GEMINI_API_KEY:
        return "❌ خطا: GEMINI_API_KEY تو env نیست"

    if not _client:
        return "❌ خطا: کلاینت Gemini ساخته نشد"

    await asyncio.sleep(random.uniform(1.5, 3.5))

    history = _memory.get(f"grp_{chat_id}", [])
    history.append(f"User: {user_message}")
    history = history[-8:]

    full = GROUP_PROMPT + "\n\n" + "\n".join(history) + "\nMelorina:"

    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full,
            config=types.GenerateContentConfig(
                temperature=1.1,
                top_p=0.95,
                max_output_tokens=200,
            ),
        )
        reply = (response.text or "").strip()
        if not reply:
            # ─── اگه خالی بود، از candidates بخون ───
            try:
                if response.candidates and len(response.candidates) > 0:
                    parts = response.candidates[0].content.parts
                    reply = "".join(p.text for p in parts if hasattr(p, "text")).strip()
            except Exception:
                pass
        if not reply:
            return "❌ خطا: Gemini جواب خالی داد — دوباره بفرست"
        history.append(f"Melorina: {reply}")
        _memory[f"grp_{chat_id}"] = history[-8:]
        return reply
    except Exception as e:
        err = str(e)[:300]
        if "location" in err.lower():
            return "❌ خطا: کلید از IP ایران — VPN لازمه"
        elif "api key" in err.lower() or "invalid" in err.lower():
            return "❌ خطا: کلید اشتباهه"
        elif "not found" in err.lower():
            return f"❌ خطا: مدل {GEMINI_MODEL} پیدا نشد"
        elif "quota" in err.lower() or "rate" in err.lower():
            return "❌ خطا: سهمیه تموم شده"
        elif "latin-1" in err.lower() or "encode" in err.lower():
            return "❌ خطا: مشکل انکودینگ"
        else:
            return f"❌ خطا:\n{err}"
