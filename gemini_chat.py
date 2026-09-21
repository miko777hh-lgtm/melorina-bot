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


ADMIN_PROMPT = """تو یه دستیار حرفه‌ای برای ادمین (صاحب) ربات تلگرام هستی.

👤 کاربر: ادمین اصلی ربات (صاحبش)
🎯 وظیفه: کمک کامل و حرفه‌ای به ادمین

🔓 محدودیتی نداری:
- هر سوالی بپرسه، کامل جواب بده
- کد، ایده، تحلیل، همه رو بده
- فارسی محاوره‌ای
- اگه سوال فنی پرسید، کامل توضیح بده

📋 لحن: حرفه‌ای ولی خودمونی
"""


async def _ask(prompt, system_prompt, memory_key, memory_size=8, temp=1.1):
    if not _client:
        return None
    history = _memory.get(memory_key, [])
    history.append(f"کاربر: {prompt}")
    history = history[-memory_size:]
    full = system_prompt + "\n\nگفتگو:\n" + "\n".join(history) + "\nملورینا:"
    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full,
            config=types.GenerateContentConfig(
                temperature=temp,
                top_p=0.95,
                max_output_tokens=200,
            ),
        )
        reply = (response.text or "").strip()
        if not reply:
            return None
        history.append(reply)
        _memory[memory_key] = history[-memory_size:]
        return reply
    except Exception as e:
        print(f"[GEMINI] خطا: {e}")
        return None


async def get_group_reply(user_message, chat_id):
    if not user_message or not user_message.strip():
        return None
    await asyncio.sleep(random.uniform(1.5, 3.5))
    return await _ask(user_message, GROUP_PROMPT, f"grp_{chat_id}", 8, 1.1)


async def get_admin_reply(user_message, admin_id):
    if not user_message or not user_message.strip():
        return None
    return await _ask(user_message, ADMIN_PROMPT, f"adm_{admin_id}", 12, 0.9)
