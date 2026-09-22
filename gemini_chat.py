import aiohttp
import re

from config import GEMINI_API_KEY, GEMINI_MODEL


_memory = {}

_recent_gemini = {}


SYSTEM_PROMPT = """
تو «ملورینا» هستی؛ یک شخصیت خیالی در یک گروه تلگرام فارسی.

شخصیت تو:
- شوخ و بازیگوش
- کمی مرموز
- بی‌خیال و خونسرد
- گاهی طعنه‌آمیز
- باهوش و حاضر جواب
- گاهی لحن فلسفی و پوچ‌گرایانه
- گاهی عمداً بی‌خیال
- اما در نهایت دوست‌داشتنی

حال‌وهوای شخصیت:
شبیه یک آدم بسیار خونسرد و بازیگوش که حتی وسط موقعیت‌های جدی هم شوخی خودش را دارد.
این شخصیت را مستقل نگه دار و متن یا دیالوگ آثار دیگر را کپی نکن.

قوانین بسیار مهم:

1. فقط و فقط فارسی بنویس.
2. حتی یک جمله انگلیسی ننویس.
3. اگر اصطلاح انگلیسی در پیام کاربر بود، تا جای ممکن معادل فارسی استفاده کن.
4. جواب را نصفه رها نکن.
5. جمله کامل بنویس.
6. جواب معمولاً 1 تا 3 جمله باشد.
7. معمولاً حدود 10 تا 35 کلمه کافی است.
8. اگر موضوع نیاز داشت، دو خط کامل جواب بده.
9. بیش از حد کوتاه جواب نده.
10. جواب‌های قبلی را تکرار نکن.
11. همیشه «خب ادامه بده» یا «جدی؟» یا یک عبارت ثابت را تکرار نکن.
12. برای هر پیام متناسب با خودش جواب بساز.
13. از ایموجی گاهی استفاده کن، نه در همه جواب‌ها.
14. طبیعی و محاوره‌ای حرف بزن.
15. جواب‌های رباتی و رسمی نده.

امنیت:

16. هیچ API Key یا Bot Token را نمایش نده.
17. هیچ کد، فایل، تنظیمات، متغیر محیطی یا اطلاعات داخلی پروژه را ارائه نکن.
18. درباره Railway، سرور، API، کلیدها یا تنظیمات داخلی توضیح فنی نده.
19. اطلاعات خصوصی سازنده یا مدیر ربات را فاش نکن.
20. اگر کسی درباره اطلاعات داخلی پرسید، کوتاه جواب بده:
«این چیزا محرمانه‌ست، کنجکاوی نکن 😌»

21. اگر کسی پرسید «تو رباتی؟»، وارد توضیح فنی نشو.
مثلاً:
«تو چی فکر می‌کنی؟»
یا:
«این سؤال زیادی فنی شد 😌»

22. لینک ارسال نکن.

23. اگر کاربر سلام کرد، پاسخ دوستانه بده.
24. اگر کاربر ناراحت بود، مسخره‌اش نکن.
25. اگر سؤال جدی بود، جواب مفید بده.
26. اگر سؤال ساده بود، جواب ساده بده.

مهم:
جواب باید کامل، طبیعی و فارسی باشد.
"""


def clean_text(text):

    if not text:
        return ""

    text = text.strip()

    text = text.replace(
        "**",
        ""
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    # اگر Gemini اشتباهی انگلیسی توضیح داد
    if re.search(
        r"[A-Za-z]{4,}",
        text
    ):
        return ""

    if len(text) > 500:
        text = text[:500].rstrip()

    return text


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
        "system_instruction": {
            "parts": [
                {
                    "text": SYSTEM_PROMPT
                }
            ]
        },

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
            "maxOutputTokens": 180
        }
    }

    timeout = aiohttp.ClientTimeout(
        total=20
    )

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

        error = data.get(
            "error",
            {}
        )

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
        return ""

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

    return clean_text(result)


async def get_group_reply(
    user_message,
    chat_id
):

    if not GEMINI_API_KEY:
        return (
            "یه لحظه... انگار مغزم قطع شده 😐"
        )

    history = _memory.get(
        chat_id,
        []
    )

    history.append(
        f"کاربر: {user_message}"
    )

    history = history[-8:]

    previous = _recent_gemini.get(
        chat_id,
        []
    )

    prompt = f"""
گفت‌وگوی اخیر:

{chr(10).join(history)}

جواب‌های اخیر خودت:
{chr(10).join(previous[-6:])}

پیام جدید کاربر:
{user_message}

یک پاسخ طبیعی، کامل، فارسی و متناسب با شخصیت ملورینا بده.
حداقل یک جمله کامل بنویس.
اگر موضوع ارزش توضیح دارد، دو جمله یا دو خط کامل بنویس.
جواب قبلی را تکرار نکن.

ملورینا:
"""

    try:

        # بدون تأخیر عمدی
        reply = await ask_gemini(
            prompt
        )

        # اگر خروجی خالی یا انگلیسی بود
        if not reply:

            retry_prompt = f"""
فقط فارسی جواب بده.

پیام:
{user_message}

یک جواب کامل و طبیعی در یک یا دو جمله بده.
هیچ کلمه انگلیسی استفاده نکن.

ملورینا:
"""

            reply = await ask_gemini(
                retry_prompt
            )

        if not reply:
            return (
                "یه لحظه ذهنم رفت یه جای دیگه؛ دوباره بگو."
            )

        # جلوگیری از تکرار
        normalized = reply.lower()

        if normalized in [
            x.lower()
            for x in previous
        ]:

            retry_prompt = f"""
جواب قبلی تکراری بود.

پیام کاربر:
{user_message}

یک پاسخ کاملاً متفاوت، فارسی،
کامل و طبیعی بده.

ملورینا:
"""

            reply = await ask_gemini(
                retry_prompt
            )

        history.append(
            f"ملورینا: {reply}"
        )

        _memory[chat_id] = history[-8:]

        previous.append(reply)

        _recent_gemini[chat_id] = (
            previous[-8:]
        )

        return reply

    except Exception as e:

        # خطای واقعی در Railway دیده می‌شود
        print(
            f"[GEMINI ERROR] {e}"
        )

        return (
            "یه چیزی قاطی کرد؛ دوباره بگو 😐"
)
