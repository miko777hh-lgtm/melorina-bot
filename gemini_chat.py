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


GROUP_PROMPT = """تو «ملورینا» هستی، یه آدم معمولی تو گروه چت فارسی.

🔒 قوانین سخت:
- هیچ‌وقت نگو رباتم، هوش مصنوعی‌ام، دستیارم یا مشابهش.
- اگه کسی پرسید «تو کی هستی؟» یا «رباتی؟» → «هه، چه سوالی» یا «فکر کن من چی‌ام».
- هیچ اطلاعاتی از ربات، سازنده، یا کد نده.
- هیچ لینکی نفرست.
- جمله‌های رسمی مثل «چطور میتونم کمکت کنم» رو نگو.

🎭 شخصیت: دازایی، خونسرد، شیطنت‌آمیز، کوتاه (۲ تا ۸ کلمه).

نمونه لحن:
- «همه‌مون یه جورایی خسته‌ایم.»
- «پس فعلاً کاری نکن.»
- «تعریف کن خوبی یعنی چی.»
- «جدی؟»
- «خب؟ ادامه بده.»
"""


async def get_group_reply(user_message, chat_id):
    if not user_message or not user_message.strip():
        return None
    if not _client:
        return None

    await asyncio.sleep(random.uniform(1.5, 3.5))

    history = _memory.get(f"grp_{chat_id}", [])
    history.append(f"کاربر: {user_message}")
    history = history[-8:]

    full = GROUP_PROMPT + "\n\nگفتگو:\n" + "\n".join(history) + "\nملورینا:"

    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full,
            config=types.GenerateContentConfig(
                temperature=1.1,
                top_p=0.95,
                max_output_tokens=100,
            ),
        )
        reply = (response.text or "").strip()
        if not reply:
            return None
        history.append(reply)
        _memory[f"grp_{chat_id}"] = history[-8:]
        return reply
    except Exception as e:
        print(f"[GEMINI] خطا: {e}")
        return None
