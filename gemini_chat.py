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
    """جواب تو گروه با تشخیص خطا"""
    if not user_message or not user_message.strip():
        return None

    # ═══ تست ۱: کلید هست؟ ═══
    if not GEMINI_API_KEY:
        return "❌ خطا: GEMINI_API_KEY تو env نیست"

    # ═══ تست ۲: کلاینت ساخته شد؟ ═══
    if not _client:
        return "❌ خطا: کلاینت Gemini ساخته نشد — کلید رو چک کن"

    # ═══ تاخیر طبیعی ═══
    await asyncio.sleep(random.uniform(1.5, 3.5))

    history = _memory.get(f"grp_{chat_id}", [])
    history.append(f"کاربر: {user_message}")
    history = history[-8:]

    full = GROUP_PROMPT + "\n\nگفتگو:\n" + "\n".join(history) + "\nملورینا:"

    # ═══ تست ۳: درخواست به Gemini ═══
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
            return "❌ خطا: Gemini جواب خالی داد"
        history.append(reply)
        _memory[f"grp_{chat_id}"] = history[-8:]
        return reply
    except Exception as e:
        err = str(e)[:300]
        # ─── تشخیص نوع خطا ───
        if "location is not supported" in err.lower() or "user location" in err.lower():
            return "❌ خطا: کلید Gemini از IP ایران ساخته شده — باید با VPN کلید جدید بسازی"
        elif "api key not valid" in err.lower() or "invalid api key" in err.lower():
            return "❌ خطا: کلید Gemini اشتباهه — دوباره کپی کن"
        elif "model not found" in err.lower() or "not found" in err.lower():
            return f"❌ خطا: مدل `{GEMINI_MODEL}` پیدا نشد — مدل رو عوض کن"
        elif "quota" in err.lower() or "rate limit" in err.lower():
            return "❌ خطا: سهمیه Gemini تموم شده — بعداً امتحان کن"
        else:
            return f"❌ خطا:\n{err}"
