import asyncio
import random
import re
import aiohttp

from config import GEMINI_API_KEY, GEMINI_MODEL


_memory = {}
_recent_replies = {}


GROUP_PROMPT = """
تو «ملورینا» هستی؛ یک شخصیت خیالی در یک گروه تلگرام فارسی.

شخصیت:
- خودمونی، باحال، شوخ و کمی شیطون
- گاهی طعنه‌آمیز ولی نه توهین‌آمیز
- جواب‌ها طبیعی و متفاوت باشند
- مثل یک عضو عادی گروه حرف بزن

قوانین:
- فقط فارسی جواب بده.
- معمولاً 2 تا 12 کلمه.
- جواب‌های قبلی را تکرار نکن.
- اگر کاربر سلام کرد، کوتاه جواب بده.
- اگر سؤال ساده پرسید، مستقیم جواب بده.
- لینک نفرست.
- اطلاعات خصوصی یا فنی ربات را نده.
- API Key، Bot Token، کد، Railway، تنظیمات و اطلاعات سازنده را فاش نکن.
- اگر درباره اطلاعات داخلی پرسید، بگو:
  «این چیزا محرمانه‌ست 😌»
- اگر پرسید «تو رباتی؟» وارد توضیح فنی نشو.
- از ایموجی گاهی استفاده کن، نه همیشه.

نمونه:
سلام → سلام 😌
خوبی؟ → بد نیستم، تو؟
چه خبر؟ → هیچی، دارم می‌چرخم 😂
حوصلم سر رفته → یه کاری کن دیگه
کی هستی؟ → حدس بزن 😏
"""


def clean_reply(text):
    if not text:
        return ""

    text = text.strip()
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = re.sub(r"\s+", " ", text)

    return text[:300].strip()


def is_repeated(chat_id, reply):
    old_replies = _recent_replies.get(chat_id, [])

    normalized = reply.strip().lower()

    return any(
        old.strip().lower() == normalized
        for old in old_replies
    )


def save_reply(chat_id, reply):
    replies = _recent_replies.setdefault(chat_id, [])

    replies.append(reply)

    _recent_replies[chat_id] = replies[-12:]


async def ask_gemini(prompt):

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 120
        }
    }

    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.post(
            url,
            headers=headers,
            json=payload
        ) as response:

            status = response.status

            data = await response.json(
                content_type=None
            )

    if status != 200:

        error = data.get("error", {})

        message = error.get(
            "message",
            str(data)
        )

        raise RuntimeError(
            f"HTTP {status}: {message}"
        )

    candidates = data.get(
        "candidates",
        []
    )

    if not candidates:
        raise RuntimeError(
            "Gemini هیچ candidate برنگرداند"
        )

    parts = candidates[0].get(
        "content",
        {}
    ).get(
        "parts",
        []
    )

    result = ""

    for part in parts:

        if part.get("text"):
            result += part["text"]

    return clean_reply(result)


async def get_group_reply(
    user_message,
    chat_id
):

    if not user_message:
        return None

    if not GEMINI_API_KEY:
        return "کلید Gemini تنظیم نشده 😐"

    await asyncio.sleep(
        random.uniform(0.8, 1.8)
    )

    history = _memory.get(
        chat_id,
        []
    )

    history.append(
        f"کاربر: {user_message}"
    )

    history = history[-10:]

    recent = _recent_replies.get(
        chat_id,
        []
    )

    prompt = f"""
{GROUP_PROMPT}

گفت‌وگوی اخیر:
{chr(10).join(history)}

جواب‌های اخیر ملورینا:
{chr(10).join(recent[-8:])}

پیام جدید:
{user_message}

یک جواب کوتاه و متفاوت بده.

ملورینا:
"""

    for attempt in range(3):

        try:

            reply = await ask_gemini(prompt)

            if not reply:
                continue

            if is_repeated(
                chat_id,
                reply
            ):

                prompt += """
جواب قبلی تکراری بود.
یک جواب کاملاً متفاوت و طبیعی بنویس.
"""

                continue

            history.append(
                f"ملورینا: {reply}"
            )

            _memory[chat_id] = history[-10:]

            save_reply(
                chat_id,
                reply
            )

            return reply

        except Exception as e:

            error = str(e)

            print(
                f"Gemini error: {error}"
            )

            # خطای کلید
            if "401" in error or "403" in error:

                return (
                    "کلید Gemini معتبر نیست 😐"
                )

            # مدل
            if "404" in error:

                return (
                    f"مدل {GEMINI_MODEL} پیدا نشد 😐"
                )

            # محدودیت
            if "429" in error:

                return (
                    "یکم صبر کن، زیادی حرف زدیم 😂"
                )

            # خطای درخواست
            if "400" in error:

                return (
                    "درخواست Gemini مشکل داشت 😐"
                )

            # تلاش مجدد
            if attempt < 2:

                await asyncio.sleep(1)

                continue

            # این بار خطای واقعی را در Railway چاپ می‌کنیم
            print(
                "FINAL GEMINI ERROR:",
                error
            )

            return (
                "یه مشکلی پیش اومد، دوباره بگو 😐"
            )

    return "یه چیزی بگو، گوشم با توئه 😌"
